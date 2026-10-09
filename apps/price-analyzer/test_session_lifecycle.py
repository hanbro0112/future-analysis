"""
測試 analyzer 的時段生命週期：窗口結束時關閉訂閱並 flush 剩餘資料、
失敗時一樣完成收尾、每個時段使用全新連線，以及交易時段判斷含國定假日。
"""
import sys
import threading
from datetime import datetime
from pathlib import Path

import pytest

apps_path = Path(__file__).resolve().parents[1]
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(apps_path))
sys.path.insert(0, str(src_path))

import price_analyzer
from price_analyzer.minute_aggregator import MinuteAggregator

TICK_MESSAGE = {
    "code": "MXFF6",
    "datetime": "2026-07-27T10:30:15",
    "open": "21800",
    "underlying_price": "21790",
    "bid_side_total_vol": 1000,
    "ask_side_total_vol": 1000,
    "avg_price": "21800",
    "close": "21805",
    "high": "21805",
    "low": "21800",
    "amount": "21805",
    "total_amount": "2180500",
    "volume": 2,
    "total_volume": 100,
    "tick_type": 1,
    "chg_type": 2,
    "price_chg": "5",
    "pct_chg": "0.02",
    "simtrade": False,
}


class FakeFirestoreWriter:
    instances: list["FakeFirestoreWriter"] = []

    def __init__(self, project_id: str) -> None:
        self.documents: list[tuple[str, str]] = []
        self.closed = False
        FakeFirestoreWriter.instances.append(self)

    def write_document(self, collection: str, data: dict, document_id: str) -> None:
        self.documents.append((collection, document_id))

    def close(self) -> None:
        self.closed = True


class FakePublisher:
    def __init__(self, project_id: str) -> None:
        self.closed = False

    def ensure_topic_exists(self, topic_id: str) -> str:
        return topic_id

    def close(self) -> None:
        self.closed = True


class FakeSubscriber:
    """subscribe() 先投遞預設訊息，再阻塞到 close() 被呼叫（模擬串流訂閱）"""

    instances: list["FakeSubscriber"] = []
    messages: list[dict] = []
    error: Exception | None = None

    def __init__(self, project_id: str, subscription_id: str, topic_id: str | None = None) -> None:
        self.started = threading.Event()
        self.closed = threading.Event()
        FakeSubscriber.instances.append(self)

    def subscribe(self, callback) -> None:
        for message in FakeSubscriber.messages:
            callback(message)
        self.started.set()
        if FakeSubscriber.error is not None:
            raise FakeSubscriber.error
        self.closed.wait(10)

    def close(self) -> None:
        self.closed.set()


@pytest.fixture(autouse=True)
def fake_cloud_clients(monkeypatch: pytest.MonkeyPatch):
    FakeFirestoreWriter.instances = []
    FakeSubscriber.instances = []
    FakeSubscriber.messages = [TICK_MESSAGE]
    FakeSubscriber.error = None
    monkeypatch.setattr(price_analyzer, "FirestoreWriter", FakeFirestoreWriter)
    monkeypatch.setattr(price_analyzer, "PubSubPublisher", FakePublisher)
    monkeypatch.setattr(price_analyzer, "PubSubSubscriber", FakeSubscriber)


def run_session_in_thread(should_continue) -> tuple[threading.Thread, dict[str, BaseException | None]]:
    outcome: dict[str, BaseException | None] = {"error": None}

    def target() -> None:
        try:
            price_analyzer.run_analyzer_session(should_continue)
        except BaseException as e:
            outcome["error"] = e

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread, outcome


def _wait_for_subscriber(count: int = 1, timeout: float = 3.0) -> None:
    """等第 count 個 FakeSubscriber 建立並已投遞完預設訊息"""
    ticker = threading.Event()
    for _ in range(int(timeout / 0.01)):
        if len(FakeSubscriber.instances) >= count and FakeSubscriber.instances[count - 1].started.is_set():
            return
        ticker.wait(0.01)
    pytest.fail("等待訂閱啟動逾時")


def test_session_flushes_pending_minute_and_releases_everything_when_window_closes() -> None:
    state = {"active": True}
    thread, outcome = run_session_in_thread(lambda: state["active"])

    _wait_for_subscriber()
    state["active"] = False  # 模擬收盤後窗口結束
    thread.join(timeout=5)

    writer = FakeFirestoreWriter.instances[0]
    subscriber = FakeSubscriber.instances[0]
    assert not thread.is_alive()
    assert outcome["error"] is None
    assert ("market/MXF/20260727", "1030") in writer.documents  # 未滿一分鐘的資料在收尾時被寫出
    assert subscriber.closed.is_set()
    assert writer.closed is True


def test_failed_subscription_still_flushes_and_releases_then_raises() -> None:
    FakeSubscriber.error = RuntimeError("subscription lost")

    thread, outcome = run_session_in_thread(lambda: True)
    thread.join(timeout=5)

    writer = FakeFirestoreWriter.instances[0]
    assert isinstance(outcome["error"], RuntimeError)
    assert ("market/MXF/20260727", "1030") in writer.documents
    assert FakeSubscriber.instances[0].closed.is_set()
    assert writer.closed is True


def test_each_session_uses_fresh_connections_and_state() -> None:
    first_state = {"active": True}
    first, _ = run_session_in_thread(lambda: first_state["active"])
    _wait_for_subscriber(count=1)
    first_state["active"] = False
    first.join(timeout=5)

    second_state = {"active": True}
    second, _ = run_session_in_thread(lambda: second_state["active"])
    _wait_for_subscriber(count=2)
    second_state["active"] = False
    second.join(timeout=5)

    assert len(FakeFirestoreWriter.instances) == 2
    assert len(FakeSubscriber.instances) == 2
    assert FakeFirestoreWriter.instances[0] is not FakeFirestoreWriter.instances[1]
    assert FakeSubscriber.instances[0] is not FakeSubscriber.instances[1]


def test_stop_flush_timer_cancels_timer_and_clears_reference() -> None:
    fired = threading.Event()
    timer = threading.Timer(60, fired.set)
    timer.daemon = True
    timer.start()
    timer_ref = {"timer": timer}

    price_analyzer.stop_flush_timer(threading.Lock(), timer_ref)

    assert timer_ref["timer"] is None
    assert not timer.is_alive()
    assert not fired.is_set()


def test_stop_flush_timer_is_safe_when_no_timer() -> None:
    price_analyzer.stop_flush_timer(threading.Lock(), {"timer": None})


@pytest.mark.parametrize(
    ("dt", "expected"),
    [
        (datetime(2026, 7, 27, 10, 30), True),
        (datetime(2026, 10, 9, 10, 30), False),  # 國慶補假
        (datetime(2026, 8, 3, 2, 0), False),  # 週日沒有夜盤，週一凌晨不開
        (datetime(2026, 7, 28, 5, 0), True),  # 週一夜盤的最後一分鐘
    ],
)
def test_aggregator_trading_hours_follow_shared_calendar(dt: datetime, expected: bool) -> None:
    assert MinuteAggregator()._is_in_trading_hours(dt) is expected
