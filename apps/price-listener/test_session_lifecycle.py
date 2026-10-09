"""
測試 listener 的時段生命週期：啟用窗口判斷、斷線事件處理、收尾與重連中止、
以及每個時段建立全新連線 / 結束時完整釋放的行為。
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

import price_listener


class _InstantEvent:
    """取代 stop_event：wait 不真的等待，讓迴圈測試瞬間跑完"""

    def __init__(self) -> None:
        self._set = False

    def wait(self, timeout: float | None = None) -> bool:
        return self._set

    def is_set(self) -> bool:
        return self._set

    def set(self) -> None:
        self._set = True


class _FakeContract:
    code = "MXFF6"
    name = "小型臺指期近月"


class _FakeFutures:
    def __getitem__(self, code: str) -> _FakeContract:
        return _FakeContract()


class _FakeContracts:
    Futures = _FakeFutures()


class _FakeQuote:
    def __init__(self) -> None:
        self.subscribed = 0

    def subscribe(self, contract: object, quote_type: object = None, version: object = None) -> None:
        self.subscribed += 1

    def set_on_tick_fop_v1_callback(self, callback: object) -> None:
        pass


class _SessionApi:
    """模擬登入後的 Shioaji 連線"""

    def __init__(self) -> None:
        self.Contracts = _FakeContracts()
        self.quote = _FakeQuote()
        self.logged_out = False
        self.event_callback: object = None

    def set_event_callback(self, callback: object) -> None:
        self.event_callback = callback

    def usage(self) -> object:
        raise RuntimeError("usage unavailable")

    def logout(self) -> None:
        self.logged_out = True


class _FakePublisher:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def reset_state(monkeypatch: pytest.MonkeyPatch):
    """每個測試前後重置模組全域狀態，避免測試互相污染"""
    monkeypatch.setattr(price_listener, "stop_event", _InstantEvent())

    def _reset() -> None:
        price_listener.is_reconnecting = False
        price_listener.is_session_active = True
        price_listener.is_subscribed = False
        price_listener.is_stopping = False
        price_listener.last_reconnect_time = None
        price_listener.api_instance = None
        price_listener.pubsub_publisher = None
        price_listener.reconnect_thread = None

    _reset()
    yield
    _reset()


def _at(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    monkeypatch.setattr(price_listener, "now_taipei", lambda: moment)


# 2026-07-27 為週一


def test_check_and_reconnect_works_during_pre_open_warmup(monkeypatch: pytest.MonkeyPatch) -> None:
    """開盤前 5 分鐘（08:40）就要能修復訂閱，不用等到 08:45 才開始檢查"""
    price_listener.is_session_active = True
    price_listener.is_subscribed = False
    price_listener.api_instance = _SessionApi()
    _at(monkeypatch, datetime(2026, 7, 27, 8, 40))

    price_listener.check_and_reconnect()

    assert price_listener.is_subscribed is True


def test_check_and_reconnect_skips_before_warmup_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    price_listener.is_session_active = True
    price_listener.is_subscribed = False
    price_listener.api_instance = _SessionApi()
    _at(monkeypatch, datetime(2026, 7, 27, 8, 39))

    price_listener.check_and_reconnect()

    assert price_listener.is_subscribed is False


def test_check_and_reconnect_skips_on_public_holiday(monkeypatch: pytest.MonkeyPatch) -> None:
    """2026-10-09 為國慶補假，即使時間落在日盤也不該啟用"""
    price_listener.is_session_active = False
    price_listener.api_instance = _SessionApi()
    _at(monkeypatch, datetime(2026, 10, 9, 10, 30))
    monkeypatch.setattr(price_listener, "reconnect", lambda: pytest.fail("假日不應重連"))

    price_listener.check_and_reconnect()

    assert price_listener.is_reconnecting is False


def test_check_and_reconnect_skips_while_stopping(monkeypatch: pytest.MonkeyPatch) -> None:
    price_listener.is_session_active = False
    price_listener.is_stopping = True
    _at(monkeypatch, datetime(2026, 7, 27, 10, 30))
    monkeypatch.setattr(price_listener, "reconnect", lambda: pytest.fail("收尾中不應重連"))

    price_listener.check_and_reconnect()


def test_session_down_in_window_starts_reconnect_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    reconnected = threading.Event()
    _at(monkeypatch, datetime(2026, 7, 27, 10, 30))
    monkeypatch.setattr(price_listener, "reconnect", reconnected.set)

    price_listener.on_session_down(0, 1, "link broken", "Session down")
    assert price_listener.reconnect_thread is not None
    price_listener.reconnect_thread.join(timeout=2)

    assert reconnected.is_set()
    assert price_listener.is_session_active is False


def test_session_down_outside_window_does_not_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    _at(monkeypatch, datetime(2026, 7, 27, 7, 0))
    monkeypatch.setattr(price_listener, "reconnect", lambda: pytest.fail("非啟用時段不應重連"))

    price_listener.on_session_down(0, 1, "link broken", "Session down")

    assert price_listener.is_session_active is False
    assert price_listener.is_reconnecting is False


def test_session_down_is_ignored_while_reconnecting(monkeypatch: pytest.MonkeyPatch) -> None:
    """重連時我們自己登出舊連線觸發的斷線事件，不應把剛恢復的連線標記成斷線"""
    price_listener.is_reconnecting = True
    price_listener.is_session_active = True
    _at(monkeypatch, datetime(2026, 7, 27, 10, 30))

    price_listener.on_session_down(0, 1, "logout", "Session down")

    assert price_listener.is_session_active is True


def test_session_down_is_ignored_while_stopping(monkeypatch: pytest.MonkeyPatch) -> None:
    price_listener.is_stopping = True
    price_listener.is_session_active = True
    _at(monkeypatch, datetime(2026, 7, 27, 10, 30))

    price_listener.on_session_down(0, 1, "logout", "Session down")

    assert price_listener.is_session_active is True


def test_non_session_down_events_do_not_change_state(monkeypatch: pytest.MonkeyPatch) -> None:
    price_listener.is_session_active = True
    _at(monkeypatch, datetime(2026, 7, 27, 10, 30))

    price_listener.on_session_down(0, 12, "subscription ok", "Subscription OK")

    assert price_listener.is_session_active is True


def test_event_callback_ignores_events_from_replaced_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """舊連線被新連線取代後才送到的事件（例如登出事件）必須被忽略"""
    old_api, new_api = object(), object()
    price_listener.api_instance = new_api  # type: ignore[assignment]
    received: list[tuple] = []
    monkeypatch.setattr(price_listener, "on_event_universal", lambda *args, **kwargs: received.append(args))

    price_listener.make_event_callback(old_api)(0, 1, "x", "Session down")  # type: ignore[arg-type]
    assert received == []

    price_listener.make_event_callback(new_api)(0, 1, "x", "Session down")  # type: ignore[arg-type]
    assert len(received) == 1


def test_reconnect_gives_up_when_session_is_stopping(monkeypatch: pytest.MonkeyPatch) -> None:
    price_listener.is_reconnecting = True
    price_listener.is_stopping = True
    monkeypatch.setattr(price_listener, "get_shioaji_client", lambda: pytest.fail("收尾中不應重新登入"))

    result = price_listener.reconnect()

    assert result is False
    assert price_listener.is_reconnecting is False


def test_check_usage_does_not_raise_when_usage_query_fails(capsys: pytest.CaptureFixture[str]) -> None:
    """api.usage() 失敗時不能再拋 UnboundLocalError（會讓收尾流程中斷、沒有登出）"""

    class _BrokenApi:
        def usage(self) -> object:
            raise RuntimeError("boom")

    price_listener.check_usage(_BrokenApi())  # type: ignore[arg-type]

    assert "取得 API 使用量失敗" in capsys.readouterr().out


def test_get_shioaji_client_logs_out_when_activate_ca_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """登入成功但憑證啟用失敗時要登出，否則時段迴圈每分鐘重試會佔滿連線數"""
    created: list["_HalfLoggedInApi"] = []

    class _HalfLoggedInApi:
        def __init__(self, simulation: bool = False) -> None:
            self.logged_out = False
            created.append(self)

        def login(self, api_key: str, secret_key: str) -> None:
            pass

        def activate_ca(self, ca_path: str, ca_passwd: str) -> None:
            raise RuntimeError("bad ca")

        def logout(self) -> None:
            self.logged_out = True

    monkeypatch.setattr(price_listener.sj, "Shioaji", _HalfLoggedInApi)

    with pytest.raises(RuntimeError, match="bad ca"):
        price_listener.get_shioaji_client()

    assert created[0].logged_out is True


def test_run_session_connects_subscribes_and_fully_releases_on_close(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _SessionApi()
    publisher = _FakePublisher()
    monkeypatch.setattr(price_listener, "init_pubsub", lambda: setattr(price_listener, "pubsub_publisher", publisher))
    monkeypatch.setattr(price_listener, "get_shioaji_client", lambda: api)
    decisions = iter([True, True, False])  # 跑兩圈後窗口結束

    price_listener.run_listener_session(lambda: next(decisions))

    assert api.quote.subscribed == 1
    assert api.event_callback is not None
    assert api.logged_out is True
    assert publisher.closed is True
    assert price_listener.api_instance is None
    assert price_listener.pubsub_publisher is None
    assert price_listener.is_session_active is False
    assert price_listener.is_subscribed is False


def test_run_session_releases_resources_when_startup_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    publisher = _FakePublisher()
    monkeypatch.setattr(price_listener, "init_pubsub", lambda: setattr(price_listener, "pubsub_publisher", publisher))

    def failing_login() -> object:
        raise RuntimeError("login failed")

    monkeypatch.setattr(price_listener, "get_shioaji_client", failing_login)

    with pytest.raises(RuntimeError, match="login failed"):
        price_listener.run_listener_session(lambda: True)

    assert publisher.closed is True
    assert price_listener.pubsub_publisher is None


def test_second_session_starts_from_clean_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """上一個時段留下的旗標（收尾中、重連中）不能影響下一個時段"""
    first_api, second_api = _SessionApi(), _SessionApi()
    apis = iter([first_api, second_api])
    monkeypatch.setattr(price_listener, "init_pubsub", lambda: setattr(price_listener, "pubsub_publisher", _FakePublisher()))
    monkeypatch.setattr(price_listener, "get_shioaji_client", lambda: next(apis))

    price_listener.run_listener_session(lambda: False)
    assert price_listener.is_stopping is True  # 第一個時段收尾後的狀態

    price_listener.run_listener_session(lambda: False)

    assert first_api.logged_out is True
    assert second_api.logged_out is True
    assert second_api.quote.subscribed == 1


def test_quote_callback_ignores_ticks_after_publisher_released() -> None:
    class _Tick:
        simtrade = False

    price_listener.pubsub_publisher = None

    price_listener.quote_callback(_Tick())  # type: ignore[arg-type]
