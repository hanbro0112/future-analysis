"""
測試 Pub/Sub 訂閱者的重試判斷、重試次數計算與 close() 乾淨結束的行為
"""
import json
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import CancelledError
from pathlib import Path

import pytest
from google.api_core import exceptions as gexc
from google.cloud.pubsub_v1.publisher.exceptions import FlowControlLimitError
from google.cloud.pubsub_v1.types import LimitExceededBehavior

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pubsub import client
from pubsub.client import (
    PUBLISH_FAILURE_LOG_EVERY,
    PubSubPublisher,
    PubSubSubscriber,
    build_async_publisher_settings,
    is_retryable_error,
)

Script = Callable[["FakeStreamingFuture"], None]


class FakeStreamingFuture:
    """模擬 StreamingPullFuture：result() 依腳本拋出例外或阻塞到被 cancel"""

    def __init__(self, script: Script) -> None:
        self._script = script
        self.cancelled = threading.Event()

    def result(self, timeout: float | None = None) -> None:
        self._script(self)

    def cancel(self) -> bool:
        self.cancelled.set()
        return True


def fail_with(error: BaseException) -> Script:
    def script(future: FakeStreamingFuture) -> None:
        raise error

    return script


def block_until_cancelled(error: BaseException | None = None) -> Script:
    def script(future: FakeStreamingFuture) -> None:
        future.cancelled.wait(5)
        raise error if error is not None else CancelledError()

    return script


class FakeBackend:
    """依序提供每次建立串流時的腳本；腳本用完後之後的串流都會一直阻塞到被取消"""

    def __init__(self, scripts: list[Script]) -> None:
        self._scripts = list(scripts)
        self.futures: list[FakeStreamingFuture] = []

    def next_future(self) -> FakeStreamingFuture:
        script = self._scripts.pop(0) if self._scripts else block_until_cancelled()
        future = FakeStreamingFuture(script)
        self.futures.append(future)
        return future


def install_fake_client(monkeypatch: pytest.MonkeyPatch, scripts: list[Script]) -> FakeBackend:
    backend = FakeBackend(scripts)

    class FakeSubscriberClient:
        def subscription_path(self, project_id: str, subscription_id: str) -> str:
            return f"projects/{project_id}/subscriptions/{subscription_id}"

        def get_subscription(self, request: dict) -> object:
            return object()

        def subscribe(self, path: str, callback: Callable, flow_control: object) -> FakeStreamingFuture:
            return backend.next_future()

        def close(self) -> None:
            pass

    monkeypatch.setattr(client.pubsub_v1, "SubscriberClient", FakeSubscriberClient)
    return backend


def run_subscribe_in_thread(
    subscriber: PubSubSubscriber, **kwargs: int
) -> tuple[threading.Thread, dict[str, BaseException | None]]:
    outcome: dict[str, BaseException | None] = {"error": None}

    def target() -> None:
        try:
            subscriber.subscribe(callback=lambda data: None, retry_delay=0, **kwargs)
        except BaseException as e:
            outcome["error"] = e

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread, outcome


def wait_until(condition: Callable[[], bool], timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail("等待條件成立逾時")
        time.sleep(0.01)


def make_subscriber() -> PubSubSubscriber:
    return PubSubSubscriber(project_id="p", subscription_id="s", topic_id="t")


@pytest.mark.parametrize(
    "error",
    [
        gexc.ServiceUnavailable("The service is currently unavailable."),
        gexc.DeadlineExceeded("Deadline Exceeded"),  # 字串為 "504 Deadline Exceeded"，不含 DEADLINE_EXCEEDED
        gexc.InternalServerError("internal"),
        gexc.Aborted("aborted"),
        gexc.ResourceExhausted("quota"),
        gexc.Unknown("Stream removed"),
        Exception("StatusCode.UNAVAILABLE: connection reset"),
        Exception("RST_STREAM received"),
    ],
)
def test_transient_errors_are_retryable(error: BaseException) -> None:
    assert is_retryable_error(error) is True


@pytest.mark.parametrize(
    "error",
    [
        gexc.PermissionDenied("denied"),
        gexc.NotFound("subscription not found"),
        gexc.Unauthenticated("bad credentials"),
        ValueError("bug"),
    ],
)
def test_permanent_errors_are_not_retryable(error: BaseException) -> None:
    assert is_retryable_error(error) is False


def test_subscribe_retries_transient_error_then_returns_cleanly_on_close(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = install_fake_client(monkeypatch, [fail_with(gexc.ServiceUnavailable("down"))])
    subscriber = make_subscriber()

    thread, outcome = run_subscribe_in_thread(subscriber)
    wait_until(lambda: len(backend.futures) == 2)  # 第一條串流失敗後重建了第二條
    subscriber.close()
    thread.join(timeout=3)

    assert not thread.is_alive()
    assert outcome["error"] is None


def test_subscribe_raises_immediately_on_permanent_error(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = install_fake_client(monkeypatch, [fail_with(gexc.PermissionDenied("denied"))])
    subscriber = make_subscriber()

    thread, outcome = run_subscribe_in_thread(subscriber)
    thread.join(timeout=3)

    assert isinstance(outcome["error"], gexc.PermissionDenied)
    assert len(backend.futures) == 1


def test_subscribe_gives_up_after_max_consecutive_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_retries 要真的生效：連續失敗超過次數後把例外拋出，交給上層重啟"""
    backend = install_fake_client(monkeypatch, [fail_with(gexc.ServiceUnavailable("down"))] * 10)
    subscriber = make_subscriber()

    thread, outcome = run_subscribe_in_thread(subscriber, max_retries=2)
    thread.join(timeout=3)

    assert isinstance(outcome["error"], gexc.ServiceUnavailable)
    assert len(backend.futures) == 3  # 第 1 次 + 2 次重試


def test_healthy_stream_resets_consecutive_failure_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """串流穩定運作後才失敗不算連續失敗，因此不會累積到 max_retries"""
    monkeypatch.setattr(client, "HEALTHY_STREAM_SECONDS", 0.0)
    backend = install_fake_client(monkeypatch, [fail_with(gexc.ServiceUnavailable("down"))] * 4)
    subscriber = make_subscriber()

    thread, outcome = run_subscribe_in_thread(subscriber, max_retries=1)
    wait_until(lambda: len(backend.futures) == 5)  # 4 次失敗後第 5 條串流持續阻塞
    subscriber.close()
    thread.join(timeout=3)

    assert outcome["error"] is None


def test_close_unblocks_subscribe_without_error(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = install_fake_client(monkeypatch, [block_until_cancelled()])
    subscriber = make_subscriber()

    thread, outcome = run_subscribe_in_thread(subscriber)
    wait_until(lambda: len(backend.futures) == 1)
    subscriber.close()
    thread.join(timeout=3)

    assert not thread.is_alive()
    assert outcome["error"] is None


def test_error_raised_by_closing_connection_is_not_treated_as_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """close() 關閉連線可能讓串流以其他例外結束，這屬於預期行為，不應拋出或重試"""
    backend = install_fake_client(monkeypatch, [block_until_cancelled(RuntimeError("channel closed"))])
    subscriber = make_subscriber()

    thread, outcome = run_subscribe_in_thread(subscriber)
    wait_until(lambda: len(backend.futures) == 1)
    subscriber.close()
    thread.join(timeout=3)

    assert outcome["error"] is None
    assert len(backend.futures) == 1


def test_close_can_be_called_repeatedly(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """時段結束時監看執行緒與 finally 都可能呼叫 close()，第二次必須是無害的 no-op"""
    install_fake_client(monkeypatch, [])
    subscriber = make_subscriber()

    subscriber.close()
    capsys.readouterr()
    subscriber.close()

    assert capsys.readouterr().out == ""


def test_subscribe_returns_immediately_when_already_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = install_fake_client(monkeypatch, [])
    subscriber = make_subscriber()
    subscriber.close()

    thread, outcome = run_subscribe_in_thread(subscriber)
    thread.join(timeout=3)

    assert outcome["error"] is None
    assert backend.futures == []


# ========== 非同步發布 ==========


class FakePublishFuture:
    """模擬發布 future：add_done_callback 立即以指定結果呼叫（或之後手動 complete）"""

    def __init__(self, error: BaseException | None = None, auto_complete: bool = True) -> None:
        self._error = error
        self._auto_complete = auto_complete
        self._callbacks: list[Callable[["FakePublishFuture"], None]] = []

    def result(self, timeout: float | None = None) -> str:
        if self._error is not None:
            raise self._error
        return "message-id"

    def add_done_callback(self, fn: Callable[["FakePublishFuture"], None]) -> None:
        if self._auto_complete:
            fn(self)
        else:
            self._callbacks.append(fn)

    def complete(self) -> None:
        for fn in self._callbacks:
            fn(self)


class FakePublisherClient:
    def __init__(self, futures: list[FakePublishFuture] | None = None, publish_error: BaseException | None = None) -> None:
        self._futures = list(futures or [])
        self._publish_error = publish_error
        self.published: list[tuple[str, bytes, dict]] = []
        self.stopped = False

    def topic_path(self, project_id: str, topic_id: str) -> str:
        return f"projects/{project_id}/topics/{topic_id}"

    def publish(self, topic_path: str, data: bytes, **attributes: str) -> FakePublishFuture:
        if self._publish_error is not None:
            raise self._publish_error
        self.published.append((topic_path, data, attributes))
        return self._futures.pop(0) if self._futures else FakePublishFuture()

    def stop(self) -> None:
        self.stopped = True


def make_publisher(monkeypatch: pytest.MonkeyPatch, fake: FakePublisherClient) -> PubSubPublisher:
    monkeypatch.setattr(client, "get_publisher_client", lambda *args, **kwargs: fake)
    return PubSubPublisher(project_id="p", async_mode=True)


def test_publish_message_async_returns_without_waiting_for_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """未完成的 future 不會卡住呼叫端：回調只需要交出訊息，不能等 result()"""
    pending = FakePublishFuture(auto_complete=False)
    fake = FakePublisherClient([pending])
    publisher = make_publisher(monkeypatch, fake)

    assert publisher.publish_message_async("t", {"code": "MXFF6"}, source="x") is True

    topic_path, payload, attributes = fake.published[0]
    assert topic_path == "projects/p/topics/t"
    assert json.loads(payload) == {"code": "MXFF6"}
    assert attributes == {"source": "x"}
    assert publisher.get_publish_stats() == {"published": 0, "failed": 0, "dropped": 0}

    pending.complete()
    assert publisher.get_publish_stats()["published"] == 1


def test_publish_message_async_counts_server_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakePublisherClient([FakePublishFuture(error=gexc.ServiceUnavailable("down"))])
    publisher = make_publisher(monkeypatch, fake)

    assert publisher.publish_message_async("t", {"a": 1}) is True

    assert publisher.get_publish_stats() == {"published": 0, "failed": 1, "dropped": 0}


def test_publish_message_async_drops_when_flow_control_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    """flow control 超限時不拋出也不阻塞，只記為丟棄"""
    fake = FakePublisherClient(publish_error=FlowControlLimitError("too many"))
    publisher = make_publisher(monkeypatch, fake)

    assert publisher.publish_message_async("t", {"a": 1}) is False

    assert publisher.get_publish_stats() == {"published": 0, "failed": 0, "dropped": 1}


def test_publish_message_async_drops_after_publisher_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    """收尾後 Shioaji 可能還有殘留回調，publisher 已停止時不能拋出例外"""
    fake = FakePublisherClient(publish_error=RuntimeError("Cannot publish on a stopped publisher."))
    publisher = make_publisher(monkeypatch, fake)

    assert publisher.publish_message_async("t", {"a": 1}) is False
    assert publisher.get_publish_stats()["dropped"] == 1


def test_publish_failure_logs_are_throttled(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakePublisherClient(publish_error=FlowControlLimitError("too many"))
    publisher = make_publisher(monkeypatch, fake)

    for _ in range(PUBLISH_FAILURE_LOG_EVERY):
        publisher.publish_message_async("t", {"a": 1})

    log_lines = [line for line in capsys.readouterr().out.splitlines() if "被丟棄" in line]
    assert len(log_lines) == 2  # 第 1 次與第 N 次


def test_close_stops_client_and_reports_failures(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakePublisherClient(publish_error=RuntimeError("stopped"))
    publisher = make_publisher(monkeypatch, fake)
    publisher.publish_message_async("t", {"a": 1})
    capsys.readouterr()

    publisher.close()

    assert fake.stopped is True
    assert "丟棄 1" in capsys.readouterr().out


def test_async_publisher_settings_do_not_block_caller() -> None:
    """超限時要拋出例外而不是阻塞，且單批最多 10ms 延遲"""
    batch_settings, publisher_options = build_async_publisher_settings()

    assert batch_settings.max_latency <= 0.01
    assert publisher_options.flow_control.limit_exceeded_behavior == LimitExceededBehavior.ERROR


# ========== 失敗訊息一律 ack ==========


class FakeMessage:
    def __init__(self, data: bytes, ack_error: BaseException | None = None) -> None:
        self.data = data
        self.message_id = "m1"
        self.acked = 0
        self.nacked = 0
        self._ack_error = ack_error

    def ack(self) -> None:
        self.acked += 1
        if self._ack_error is not None:
            raise self._ack_error

    def nack(self) -> None:
        self.nacked += 1


def capture_message_callback(
    monkeypatch: pytest.MonkeyPatch, user_callback: Callable[[dict], None]
) -> Callable[[FakeMessage], None]:
    """訂閱時攔下 subscribe() 內部建立的 message_callback"""
    captured: dict[str, Callable[[FakeMessage], None]] = {}

    class FakeSubscriberClient:
        def subscription_path(self, project_id: str, subscription_id: str) -> str:
            return f"projects/{project_id}/subscriptions/{subscription_id}"

        def get_subscription(self, request: dict) -> object:
            return object()

        def subscribe(self, path: str, callback: Callable, flow_control: object) -> FakeStreamingFuture:
            captured["callback"] = callback
            return FakeStreamingFuture(block_until_cancelled())

        def close(self) -> None:
            pass

    monkeypatch.setattr(client.pubsub_v1, "SubscriberClient", FakeSubscriberClient)
    subscriber = make_subscriber()
    thread = threading.Thread(target=lambda: subscriber.subscribe(callback=user_callback, retry_delay=0), daemon=True)
    thread.start()
    wait_until(lambda: "callback" in captured)
    subscriber.close()
    thread.join(timeout=3)
    return captured["callback"]


def test_message_is_acked_after_successful_processing(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[dict] = []
    message_callback = capture_message_callback(monkeypatch, received.append)
    message = FakeMessage(b'{"code": "MXFF6"}')

    message_callback(message)

    assert received == [{"code": "MXFF6"}]
    assert (message.acked, message.nacked) == (1, 0)


def test_invalid_json_is_acked_not_nacked(monkeypatch: pytest.MonkeyPatch) -> None:
    message_callback = capture_message_callback(monkeypatch, lambda data: None)
    message = FakeMessage(b"not json")

    message_callback(message)

    assert (message.acked, message.nacked) == (1, 0)


def test_callback_exception_is_acked_not_nacked(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_callback(data: dict) -> None:
        raise ValueError("bug")

    message_callback = capture_message_callback(monkeypatch, failing_callback)
    message = FakeMessage(b'{"code": "MXFF6"}')

    message_callback(message)

    assert (message.acked, message.nacked) == (1, 0)


def test_ack_error_in_failure_path_does_not_raise(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    message_callback = capture_message_callback(monkeypatch, lambda data: None)
    message = FakeMessage(b"not json", ack_error=RuntimeError("ack failed"))

    message_callback(message)  # 不可拋出，否則 Pub/Sub 的 callback 執行緒會噴例外

    assert "ack 時發生錯誤" in capsys.readouterr().out
