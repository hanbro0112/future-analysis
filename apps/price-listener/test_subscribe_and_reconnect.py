"""
測試合約訂閱重試機制，以及 check_and_reconnect / reconnect 在
「已登入但合約訂閱失敗」情境下是否能正確自我修復。

背景：實際上線後曾發生容器在開盤前冷啟動、合約清單尚未下載完成，
導致 subscribe_contracts 失敗；而舊版邏輯只在乎 is_session_active，
訂閱失敗不會被追蹤，即使進入交易時段也永遠不會重試。
"""
import sys
from pathlib import Path
from datetime import datetime

import pytest

apps_path = Path(__file__).resolve().parents[1]
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(apps_path))
sys.path.insert(0, str(src_path))

import price_listener


class _FakeContract:
    def __init__(self, code: str, name: str = "小型臺指期近月") -> None:
        self.code = code
        self.name = name


class _FakeFutures:
    """模擬 api.Contracts.Futures[code]，可設定前幾次查詢刻意失敗（模擬合約清單尚未下載完成）"""

    def __init__(self, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.call_count = 0

    def __getitem__(self, code: str) -> _FakeContract:
        self.call_count += 1
        if self.call_count <= self.fail_times:
            raise Exception(f"Contract not found: {code}")
        return _FakeContract(code)


class _FakeContracts:
    def __init__(self, futures: _FakeFutures) -> None:
        self.Futures = futures


class _FakeQuote:
    def __init__(self, raise_on_subscribe: bool = False) -> None:
        self.subscribed_codes: list[str] = []
        self.raise_on_subscribe = raise_on_subscribe

    def subscribe(self, contract: _FakeContract, quote_type: object = None, version: object = None) -> None:
        if self.raise_on_subscribe:
            raise Exception("subscribe failed")
        self.subscribed_codes.append(contract.code)

    def set_on_tick_fop_v1_callback(self, callback: object) -> None:
        pass


class _FakeApi:
    def __init__(self, futures: _FakeFutures, quote: _FakeQuote) -> None:
        self.Contracts = _FakeContracts(futures)
        self.quote = quote

    def set_event_callback(self, callback: object) -> None:
        pass

    def logout(self) -> None:
        pass


@pytest.fixture(autouse=True)
def reset_state():
    """每個測試前後重置模組全域狀態，避免測試互相污染"""
    def _reset() -> None:
        price_listener.is_reconnecting = False
        price_listener.is_session_active = True
        price_listener.is_subscribed = False
        price_listener.last_reconnect_time = None
        price_listener.api_instance = None

    _reset()
    yield
    _reset()


def test_subscribe_contracts_succeeds_on_first_try() -> None:
    """合約查詢與訂閱皆一次成功時，回傳 True"""
    api = _FakeApi(_FakeFutures(fail_times=0), _FakeQuote())

    result = price_listener.subscribe_contracts(api, max_attempts=3, retry_delay=0)

    assert result is True
    assert api.quote.subscribed_codes == price_listener.target_symbols


def test_subscribe_contracts_retries_until_contract_found() -> None:
    """合約清單還沒下載完成時查詢會失敗，重試後找到合約應回傳 True"""
    api = _FakeApi(_FakeFutures(fail_times=2), _FakeQuote())

    result = price_listener.subscribe_contracts(api, max_attempts=3, retry_delay=0)

    assert result is True
    assert api.Contracts.Futures.call_count == 3
    assert api.quote.subscribed_codes == price_listener.target_symbols


def test_subscribe_contracts_gives_up_after_max_attempts() -> None:
    """超過重試次數仍找不到合約時，回傳 False 且不會呼叫 subscribe"""
    api = _FakeApi(_FakeFutures(fail_times=99), _FakeQuote())

    result = price_listener.subscribe_contracts(api, max_attempts=3, retry_delay=0)

    assert result is False
    assert api.quote.subscribed_codes == []


def test_subscribe_contracts_false_when_subscribe_call_fails() -> None:
    """合約查詢成功但 api.quote.subscribe 呼叫失敗時，回傳 False"""
    api = _FakeApi(_FakeFutures(fail_times=0), _FakeQuote(raise_on_subscribe=True))

    result = price_listener.subscribe_contracts(api, max_attempts=3, retry_delay=0)

    assert result is False


def test_check_and_reconnect_retries_subscribe_when_session_active_but_not_subscribed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    重現線上實際情況：登入成功（is_session_active=True）但合約訂閱失敗
    （is_subscribed=False），交易時段內應重新呼叫 subscribe_contracts，
    而不是被舊邏輯的 `if is_session_active: return` 擋下來、永遠不重試。
    """
    price_listener.is_session_active = True
    price_listener.is_subscribed = False
    price_listener.api_instance = _FakeApi(_FakeFutures(fail_times=0), _FakeQuote())

    monkeypatch.setattr(price_listener, "now_taipei", lambda: datetime(2026, 7, 27, 10, 30))
    called = {"reconnect": False}
    monkeypatch.setattr(price_listener, "reconnect", lambda: called.__setitem__("reconnect", True))

    price_listener.check_and_reconnect()

    assert price_listener.is_subscribed is True
    assert called["reconnect"] is False  # 只需重新訂閱，不需要整個重新登入


def test_check_and_reconnect_skips_subscribe_retry_outside_trading_hours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非交易時段即使尚未訂閱成功，也不應該重試"""
    price_listener.is_session_active = True
    price_listener.is_subscribed = False
    fake_api = _FakeApi(_FakeFutures(fail_times=0), _FakeQuote())
    price_listener.api_instance = fake_api

    monkeypatch.setattr(price_listener, "now_taipei", lambda: datetime(2026, 7, 27, 7, 0))

    price_listener.check_and_reconnect()

    assert price_listener.is_subscribed is False
    assert fake_api.quote.subscribed_codes == []


def test_check_and_reconnect_respects_cooldown_between_subscribe_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """距離上次重試未滿 30 秒時，不應該再次重試訂閱"""
    price_listener.is_session_active = True
    price_listener.is_subscribed = False
    fake_api = _FakeApi(_FakeFutures(fail_times=0), _FakeQuote())
    price_listener.api_instance = fake_api

    now = datetime(2026, 7, 27, 10, 30, 20)
    price_listener.last_reconnect_time = datetime(2026, 7, 27, 10, 30, 0)
    monkeypatch.setattr(price_listener, "now_taipei", lambda: now)

    price_listener.check_and_reconnect()

    assert price_listener.is_subscribed is False
    assert fake_api.quote.subscribed_codes == []


def test_reconnect_retries_when_subscribe_fails_after_relogin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    重新登入成功但合約訂閱又失敗時，不應該視為重連成功，
    要沿用既有的重試/退避機制繼續嘗試，直到訂閱也成功為止。
    """
    price_listener.is_reconnecting = True
    price_listener.is_session_active = False

    fake_api = _FakeApi(_FakeFutures(fail_times=0), _FakeQuote())
    monkeypatch.setattr(price_listener, "get_shioaji_client", lambda: fake_api)
    monkeypatch.setattr(price_listener.time, "sleep", lambda _seconds: None)

    subscribe_results = iter([False, False, True])
    monkeypatch.setattr(
        price_listener,
        "subscribe_contracts",
        lambda api: next(subscribe_results),
    )

    result = price_listener.reconnect()

    assert result is True
    assert price_listener.is_subscribed is True
    assert price_listener.is_session_active is True
    assert price_listener.is_reconnecting is False
