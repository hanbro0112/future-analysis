"""
測試 Pub/Sub 訂閱者的重試判斷、重試次數計算與 close() 乾淨結束的行為
"""
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import CancelledError
from pathlib import Path

import pytest
from google.api_core import exceptions as gexc

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pubsub import client
from pubsub.client import PubSubSubscriber, is_retryable_error

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
