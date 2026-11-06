"""
測試 tick 看門狗、每分鐘心跳、發布層自癒（重建 Publisher）與 logout timeout。
"""
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

apps_path = Path(__file__).resolve().parents[1]
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(apps_path))
sys.path.insert(0, str(src_path))

import price_listener


class _FakeContract:
    code = "MXFF6"
    name = "小型臺指期近月"


class _FakeFutures:
    def __getitem__(self, code: str) -> _FakeContract:
        return _FakeContract()


class _FakeContracts:
    Futures = _FakeFutures()


class _FakeQuote:
    def __init__(self, unsubscribe_error: Exception | None = None) -> None:
        self.calls: list[str] = []
        self._unsubscribe_error = unsubscribe_error

    def subscribe(self, contract: object, quote_type: object = None, version: object = None) -> None:
        self.calls.append("subscribe")

    def unsubscribe(self, contract: object, quote_type: object = None, version: object = None) -> None:
        self.calls.append("unsubscribe")
        if self._unsubscribe_error is not None:
            raise self._unsubscribe_error


class _FakeApi:
    def __init__(self, unsubscribe_error: Exception | None = None) -> None:
        self.Contracts = _FakeContracts()
        self.quote = _FakeQuote(unsubscribe_error)


class _FakePublisher:
    def __init__(self, stats: dict[str, int] | None = None) -> None:
        self.stats = stats or {"published": 0, "failed": 0, "dropped": 0}
        self.closed = False

    def get_publish_stats(self) -> dict[str, int]:
        return dict(self.stats)

    def close(self) -> None:
        self.closed = True


class _Tick:
    def __init__(self, simtrade: bool) -> None:
        self.simtrade = simtrade


@pytest.fixture(autouse=True)
def reset_state():
    def _reset() -> None:
        price_listener.is_reconnecting = False
        price_listener.is_session_active = True
        price_listener.is_subscribed = True
        price_listener.is_stopping = False
        price_listener.last_reconnect_time = None
        price_listener.api_instance = None
        price_listener.pubsub_publisher = None
        price_listener.reconnect_thread = None
        price_listener.last_tick_time = time.monotonic()
        price_listener.watchdog_resubscribed = False
        price_listener._prev_publish_stats = {"published": 0, "failed": 0, "dropped": 0}

    _reset()
    yield
    _reset()


def _at(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    monkeypatch.setattr(price_listener, "now_taipei", lambda: moment)


def _stale_for(seconds: float) -> None:
    price_listener.last_tick_time = time.monotonic() - seconds


# 2026-07-27 為週一；2026-10-09 為國慶補假

# ---------- is_tick_stale ----------


def test_is_tick_stale_true_when_session_open_and_no_tick() -> None:
    assert price_listener.is_tick_stale(datetime(2026, 7, 27, 10, 30), 200) is True


def test_is_tick_stale_false_when_tick_is_recent() -> None:
    assert price_listener.is_tick_stale(datetime(2026, 7, 27, 10, 30), 30) is False


def test_is_tick_stale_false_during_pre_open_warmup() -> None:
    """開盤前（08:40）只有試撮，沒有正式 tick 是正常的"""
    assert price_listener.is_tick_stale(datetime(2026, 7, 27, 8, 40), 999) is False


def test_is_tick_stale_false_right_after_open() -> None:
    """剛開盤（08:46）還不滿門檻時間，第一筆 tick 可能還沒到，不能誤判"""
    assert price_listener.is_tick_stale(datetime(2026, 7, 27, 8, 46), 999) is False


def test_is_tick_stale_true_once_open_longer_than_threshold() -> None:
    assert price_listener.is_tick_stale(datetime(2026, 7, 27, 8, 48), 999) is True


def test_is_tick_stale_false_between_day_and_night_session() -> None:
    assert price_listener.is_tick_stale(datetime(2026, 7, 27, 14, 30), 999) is False


def test_is_tick_stale_true_during_night_session() -> None:
    assert price_listener.is_tick_stale(datetime(2026, 7, 27, 15, 30), 999) is True


def test_is_tick_stale_false_on_public_holiday() -> None:
    assert price_listener.is_tick_stale(datetime(2026, 10, 9, 10, 30), 999) is False


# ---------- quote_callback 更新最後 tick 時間 ----------


def test_quote_callback_updates_last_tick_time_for_real_tick() -> None:
    _stale_for(500)
    before = price_listener.last_tick_time

    price_listener.quote_callback(_Tick(simtrade=False))  # type: ignore[arg-type]

    assert price_listener.last_tick_time > before


def test_quote_callback_does_not_update_last_tick_time_for_simtrade() -> None:
    _stale_for(500)
    before = price_listener.last_tick_time

    price_listener.quote_callback(_Tick(simtrade=True))  # type: ignore[arg-type]

    assert price_listener.last_tick_time == before


# ---------- 訂閱基準 ----------


def test_subscribe_contracts_success_resets_tick_baseline() -> None:
    _stale_for(500)

    assert price_listener.subscribe_contracts(_FakeApi()) is True  # type: ignore[arg-type]

    assert time.monotonic() - price_listener.last_tick_time < 5


def test_subscribe_contracts_failure_keeps_tick_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    class _NoContractFutures:
        def __getitem__(self, code: str) -> None:
            return None

    api = _FakeApi()
    api.Contracts.Futures = _NoContractFutures()  # type: ignore[assignment]
    monkeypatch.setattr(price_listener.time, "sleep", lambda _: None)
    _stale_for(500)

    assert price_listener.subscribe_contracts(api, max_attempts=1) is False  # type: ignore[arg-type]

    assert time.monotonic() - price_listener.last_tick_time >= 500


# ---------- resubscribe_contracts ----------


def test_resubscribe_unsubscribes_then_subscribes() -> None:
    api = _FakeApi()

    assert price_listener.resubscribe_contracts(api) is True  # type: ignore[arg-type]

    assert api.quote.calls == ["unsubscribe", "subscribe"]


def test_resubscribe_still_subscribes_when_unsubscribe_fails() -> None:
    api = _FakeApi(unsubscribe_error=RuntimeError("not subscribed"))

    assert price_listener.resubscribe_contracts(api) is True  # type: ignore[arg-type]

    assert api.quote.calls == ["unsubscribe", "subscribe"]


# ---------- check_tick_watchdog ----------


def test_watchdog_does_nothing_when_ticks_are_flowing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(price_listener, "resubscribe_contracts", lambda api: pytest.fail("有 tick 不該重新訂閱"))
    monkeypatch.setattr(price_listener, "reconnect", lambda: pytest.fail("有 tick 不該重連"))

    price_listener.check_tick_watchdog(datetime(2026, 7, 27, 10, 30))

    assert price_listener.watchdog_resubscribed is False


def test_watchdog_first_resubscribes_then_escalates_to_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _FakeApi()
    price_listener.api_instance = api  # type: ignore[assignment]
    actions: list[str] = []
    monkeypatch.setattr(price_listener, "resubscribe_contracts", lambda a: actions.append("resubscribe") or True)
    monkeypatch.setattr(price_listener, "reconnect", lambda: actions.append("reconnect"))
    now = datetime(2026, 7, 27, 10, 30)

    _stale_for(200)
    price_listener.check_tick_watchdog(now)
    assert actions == ["resubscribe"]
    assert price_listener.watchdog_resubscribed is True

    # 重新訂閱後仍然沒有 tick
    _stale_for(200)
    price_listener.check_tick_watchdog(now)
    assert actions == ["resubscribe", "reconnect"]
    assert price_listener.watchdog_resubscribed is False


def test_watchdog_resets_when_tick_arrives_after_resubscribe(monkeypatch: pytest.MonkeyPatch) -> None:
    price_listener.watchdog_resubscribed = True
    monkeypatch.setattr(price_listener, "reconnect", lambda: pytest.fail("已恢復不該重連"))

    price_listener.check_tick_watchdog(datetime(2026, 7, 27, 10, 30))

    assert price_listener.watchdog_resubscribed is False


def test_check_and_reconnect_runs_watchdog_when_session_looks_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    """旗標都正常（已登入、已訂閱）但沒有 tick：check_and_reconnect 要交給看門狗處理"""
    price_listener.api_instance = _FakeApi()  # type: ignore[assignment]
    _at(monkeypatch, datetime(2026, 7, 27, 10, 30))
    _stale_for(200)
    resubscribed: list[object] = []
    monkeypatch.setattr(price_listener, "resubscribe_contracts", lambda a: resubscribed.append(a) or True)

    price_listener.check_and_reconnect()

    assert len(resubscribed) == 1


def test_check_and_reconnect_does_not_trigger_watchdog_during_warmup(monkeypatch: pytest.MonkeyPatch) -> None:
    price_listener.api_instance = _FakeApi()  # type: ignore[assignment]
    _at(monkeypatch, datetime(2026, 7, 27, 8, 41))
    _stale_for(999)
    monkeypatch.setattr(price_listener, "resubscribe_contracts", lambda a: pytest.fail("預熱期不該觸發看門狗"))

    price_listener.check_and_reconnect()


# ---------- 心跳與統計差值 ----------


def test_take_publish_stats_delta_returns_difference_since_last_call() -> None:
    publisher = _FakePublisher({"published": 100, "failed": 2, "dropped": 1})
    price_listener.pubsub_publisher = publisher  # type: ignore[assignment]

    assert price_listener.take_publish_stats_delta() == {"published": 100, "failed": 2, "dropped": 1}

    publisher.stats = {"published": 130, "failed": 2, "dropped": 4}
    assert price_listener.take_publish_stats_delta() == {"published": 30, "failed": 0, "dropped": 3}


def test_take_publish_stats_delta_returns_none_without_publisher() -> None:
    assert price_listener.take_publish_stats_delta() is None


def test_format_heartbeat_includes_tick_total_and_age() -> None:
    message = price_listener.format_heartbeat({"published": 50, "failed": 3, "dropped": 2}, 12.4)

    assert "55 筆" in message
    assert "成功 50" in message
    assert "失敗 3" in message
    assert "丟棄 2" in message
    assert "12 秒" in message


# ---------- 發布層自癒 ----------


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        ({"published": 0, "failed": 5, "dropped": 0}, True),
        ({"published": 0, "failed": 0, "dropped": 7}, True),
        ({"published": 0, "failed": 0, "dropped": 0}, False),  # 單純沒有 tick，不是 publisher 的問題
        ({"published": 10, "failed": 5, "dropped": 0}, False),  # 還有成功的，不重建
    ],
)
def test_should_rebuild_publisher(delta: dict[str, int], expected: bool) -> None:
    assert price_listener.should_rebuild_publisher(delta) is expected


def test_rebuild_publisher_swaps_instance_and_closes_old(monkeypatch: pytest.MonkeyPatch) -> None:
    old, new = _FakePublisher(), _FakePublisher()
    price_listener.pubsub_publisher = old  # type: ignore[assignment]
    price_listener._prev_publish_stats = {"published": 9, "failed": 9, "dropped": 9}
    monkeypatch.setattr(price_listener, "create_publisher", lambda: new)

    assert price_listener.rebuild_publisher() is True

    assert price_listener.pubsub_publisher is new
    assert old.closed is True
    assert new.closed is False
    assert price_listener._prev_publish_stats == {"published": 0, "failed": 0, "dropped": 0}


def test_rebuild_publisher_keeps_old_when_creation_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    old = _FakePublisher()
    price_listener.pubsub_publisher = old  # type: ignore[assignment]

    def failing_create() -> object:
        raise RuntimeError("permission denied")

    monkeypatch.setattr(price_listener, "create_publisher", failing_create)

    assert price_listener.rebuild_publisher() is False

    assert price_listener.pubsub_publisher is old
    assert old.closed is False


def test_run_health_checks_rebuilds_publisher_when_nothing_published(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    price_listener.pubsub_publisher = _FakePublisher({"published": 0, "failed": 8, "dropped": 0})  # type: ignore[assignment]
    rebuilt: list[bool] = []
    monkeypatch.setattr(price_listener, "rebuild_publisher", lambda: rebuilt.append(True) or True)
    monkeypatch.setattr(price_listener, "check_and_reconnect", lambda: None)

    price_listener.run_health_checks()

    assert rebuilt == [True]
    assert "心跳" in capsys.readouterr().out


def test_run_health_checks_does_not_rebuild_when_publishing_normally(monkeypatch: pytest.MonkeyPatch) -> None:
    price_listener.pubsub_publisher = _FakePublisher({"published": 120, "failed": 0, "dropped": 0})  # type: ignore[assignment]
    monkeypatch.setattr(price_listener, "rebuild_publisher", lambda: pytest.fail("正常發布不該重建"))
    monkeypatch.setattr(price_listener, "check_and_reconnect", lambda: None)

    price_listener.run_health_checks()


def test_run_health_checks_still_checks_connection_when_heartbeat_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_stats() -> object:
        raise RuntimeError("stats broken")

    checked: list[bool] = []
    monkeypatch.setattr(price_listener, "take_publish_stats_delta", broken_stats)
    monkeypatch.setattr(price_listener, "check_and_reconnect", lambda: checked.append(True))

    price_listener.run_health_checks()

    assert checked == [True]


def test_run_listener_session_runs_health_checks_every_60_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    class _InstantEvent:
        def wait(self, timeout: float | None = None) -> bool:
            return False

        def is_set(self) -> bool:
            return False

    api = _FakeApi()
    api.set_event_callback = lambda callback: None  # type: ignore[attr-defined]
    api.logout = lambda: None  # type: ignore[attr-defined]
    api.usage = lambda: (_ for _ in ()).throw(RuntimeError("n/a"))  # type: ignore[attr-defined]
    api.quote.set_on_tick_fop_v1_callback = lambda callback: None  # type: ignore[attr-defined]
    monkeypatch.setattr(price_listener, "stop_event", _InstantEvent())
    monkeypatch.setattr(price_listener, "init_pubsub", lambda: setattr(price_listener, "pubsub_publisher", _FakePublisher()))
    monkeypatch.setattr(price_listener, "get_shioaji_client", lambda: api)
    runs: list[bool] = []
    monkeypatch.setattr(price_listener, "run_health_checks", lambda: runs.append(True))
    decisions = iter([True] * 120 + [False])  # 120 秒

    price_listener.run_listener_session(lambda: next(decisions))

    assert len(runs) == 2


# ---------- logout timeout ----------


def test_call_with_timeout_returns_true_on_success() -> None:
    assert price_listener.call_with_timeout(lambda: None, 1.0, "測試") is True


def test_call_with_timeout_returns_false_when_function_raises(capsys: pytest.CaptureFixture[str]) -> None:
    def boom() -> None:
        raise RuntimeError("boom")

    assert price_listener.call_with_timeout(boom, 1.0, "測試") is False
    assert "boom" in capsys.readouterr().out


def test_call_with_timeout_gives_up_when_function_hangs() -> None:
    release = threading.Event()
    started = time.monotonic()

    try:
        assert price_listener.call_with_timeout(release.wait, 0.1, "測試") is False
        assert time.monotonic() - started < 2
    finally:
        release.set()


def test_safe_logout_does_not_hang_when_logout_hangs(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()
    monkeypatch.setattr(price_listener, "LOGOUT_TIMEOUT_SECONDS", 0.1)

    class _HangingApi:
        def logout(self) -> None:
            release.wait()

    try:
        assert price_listener.safe_logout(_HangingApi()) is False  # type: ignore[arg-type]
    finally:
        release.set()


def test_stop_listener_session_completes_even_if_logout_hangs(monkeypatch: pytest.MonkeyPatch) -> None:
    """logout 卡住時收尾流程仍要走完（釋放 publisher、重置狀態），時段迴圈才能回到待機"""
    release = threading.Event()
    publisher = _FakePublisher()
    monkeypatch.setattr(price_listener, "LOGOUT_TIMEOUT_SECONDS", 0.1)

    class _HangingApi:
        def usage(self) -> object:
            raise RuntimeError("n/a")

        def logout(self) -> None:
            release.wait()

    price_listener.api_instance = _HangingApi()  # type: ignore[assignment]
    price_listener.pubsub_publisher = publisher  # type: ignore[assignment]

    try:
        price_listener.stop_listener_session()
    finally:
        release.set()

    assert publisher.closed is True
    assert price_listener.api_instance is None
    assert price_listener.pubsub_publisher is None
