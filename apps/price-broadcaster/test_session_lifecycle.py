"""
測試 broadcaster 的時段生命週期：進入啟用窗口時開始廣播、收盤時中斷連線並清空報價、
Pub/Sub 訂閱意外結束時自動重啟，以及每個時段都使用全新的訂閱連線。
"""
import asyncio
import sys
import threading
from pathlib import Path

import pytest

apps_path = Path(__file__).resolve().parents[1]
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(apps_path))
sys.path.insert(0, str(src_path))

import price_broadcaster
from price_broadcaster import PriceBroadcaster


class FakeWindow:
    """取代 ACTIVE_WINDOW：由測試控制現在是否在啟用窗口內"""

    def __init__(self) -> None:
        self.active = True

    def contains(self, dt: object = None) -> bool:
        return self.active


class FakeSubscriber:
    """subscribe() 阻塞到 close() 被呼叫（模擬串流訂閱），或依設定拋出例外"""

    instances: list["FakeSubscriber"] = []
    error: Exception | None = None

    def __init__(self, project_id: str, subscription_id: str, topic_id: str | None = None) -> None:
        self.started = threading.Event()
        self.closed = threading.Event()
        FakeSubscriber.instances.append(self)

    def subscribe(self, callback: object) -> None:
        self.started.set()
        if FakeSubscriber.error is not None:
            raise FakeSubscriber.error
        self.closed.wait(5)

    def close(self) -> None:
        self.closed.set()


class FakeWebSocket:
    def __init__(self, fail_on_close: bool = False) -> None:
        self.close_code: int | None = None
        self.fail_on_close = fail_on_close

    async def close(self, code: int) -> None:
        if self.fail_on_close:
            raise RuntimeError("already closed")
        self.close_code = code


@pytest.fixture(autouse=True)
def fakes(monkeypatch: pytest.MonkeyPatch) -> FakeWindow:
    FakeSubscriber.instances = []
    FakeSubscriber.error = None
    window = FakeWindow()
    monkeypatch.setattr(price_broadcaster, "PubSubSubscriber", FakeSubscriber)
    monkeypatch.setattr(price_broadcaster, "ACTIVE_WINDOW", window)
    return window


async def wait_for_subscriber(count: int = 1) -> None:
    for _ in range(300):
        if len(FakeSubscriber.instances) >= count and FakeSubscriber.instances[count - 1].started.is_set():
            return
        await asyncio.sleep(0.01)
    pytest.fail("等待訂閱啟動逾時")


def test_idle_outside_window_does_not_start_anything(fakes: FakeWindow) -> None:
    fakes.active = False
    broadcaster = PriceBroadcaster()

    asyncio.run(broadcaster.reconcile_session())

    assert broadcaster.session_running is False
    assert FakeSubscriber.instances == []


def test_session_starts_when_window_opens_and_ends_with_clean_state(fakes: FakeWindow) -> None:
    async def scenario() -> tuple[PriceBroadcaster, FakeWebSocket]:
        broadcaster = PriceBroadcaster()
        await broadcaster.reconcile_session()
        await wait_for_subscriber()
        assert broadcaster.session_running is True

        ws = FakeWebSocket()
        broadcaster.active_connections.add(ws)  # type: ignore[arg-type]
        broadcaster.latest_prices["MXFF6"] = {"price": 21800.0, "underlying_price": 21790.0, "volume": 3}
        broadcaster.second_volumes["MXFF6"] = 3

        fakes.active = False  # 收盤
        await broadcaster.reconcile_session()
        return broadcaster, ws

    broadcaster, ws = asyncio.run(scenario())

    assert broadcaster.session_running is False
    assert ws.close_code == price_broadcaster.WS_CLOSE_CODE_NOT_TRADING_HOURS
    assert broadcaster.active_connections == set()
    assert broadcaster.latest_prices == {}
    assert broadcaster.second_volumes == {}
    assert broadcaster.subscriber is None
    assert FakeSubscriber.instances[0].closed.is_set()


def test_subscription_that_dies_mid_session_is_restarted_on_next_round(fakes: FakeWindow) -> None:
    async def scenario() -> tuple[PriceBroadcaster, FakeWebSocket]:
        FakeSubscriber.error = RuntimeError("subscription lost")
        broadcaster = PriceBroadcaster()
        await broadcaster.reconcile_session()
        await wait_for_subscriber()
        await asyncio.wait({broadcaster.pubsub_task}, timeout=2)  # 等訂閱任務因錯誤結束

        ws = FakeWebSocket()
        broadcaster.active_connections.add(ws)  # type: ignore[arg-type]

        await broadcaster.reconcile_session()  # 偵測到訂閱已死：收尾
        assert broadcaster.session_running is False

        FakeSubscriber.error = None
        await broadcaster.reconcile_session()  # 下一輪重新啟動
        await wait_for_subscriber(count=2)
        assert broadcaster.session_running is True

        fakes.active = False
        await broadcaster.reconcile_session()
        return broadcaster, ws

    _, ws = asyncio.run(scenario())

    assert ws.close_code == price_broadcaster.WS_CLOSE_CODE_SERVICE_RESTART
    assert len(FakeSubscriber.instances) == 2
    assert FakeSubscriber.instances[0] is not FakeSubscriber.instances[1]


def test_each_session_uses_a_fresh_subscriber(fakes: FakeWindow) -> None:
    async def scenario() -> None:
        broadcaster = PriceBroadcaster()
        for round_number in (1, 2):
            fakes.active = True
            await broadcaster.reconcile_session()
            await wait_for_subscriber(count=round_number)
            fakes.active = False
            await broadcaster.reconcile_session()

    asyncio.run(scenario())

    assert len(FakeSubscriber.instances) == 2
    assert all(subscriber.closed.is_set() for subscriber in FakeSubscriber.instances)


def test_close_all_connections_continues_after_one_fails() -> None:
    async def scenario() -> tuple[FakeWebSocket, FakeWebSocket]:
        broadcaster = PriceBroadcaster()
        broken, healthy = FakeWebSocket(fail_on_close=True), FakeWebSocket()
        broadcaster.active_connections.update({broken, healthy})  # type: ignore[arg-type]
        await broadcaster.close_all_connections(code=4403)
        assert broadcaster.active_connections == set()
        return broken, healthy

    _, healthy = asyncio.run(scenario())

    assert healthy.close_code == 4403


def test_supervisor_polls_window_and_can_be_cancelled(
    fakes: FakeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(price_broadcaster, "IDLE_CHECK_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(price_broadcaster, "RUNNING_CHECK_INTERVAL_SECONDS", 0.01)
    fakes.active = False

    async def scenario() -> PriceBroadcaster:
        broadcaster = PriceBroadcaster()
        broadcaster.supervisor_task = asyncio.create_task(broadcaster.supervise_sessions())

        await asyncio.sleep(0.05)
        assert broadcaster.session_running is False  # 待機中

        fakes.active = True
        for _ in range(300):
            if broadcaster.session_running:
                break
            await asyncio.sleep(0.01)
        assert broadcaster.session_running is True  # 進入窗口後自動開始

        fakes.active = False
        for _ in range(300):
            if not broadcaster.session_running:
                break
            await asyncio.sleep(0.01)
        assert broadcaster.session_running is False  # 窗口結束後自動收尾

        await broadcaster.shutdown()
        assert broadcaster.supervisor_task.done()
        return broadcaster

    asyncio.run(scenario())


def test_shutdown_ends_running_session_and_closes_connections_with_going_away(fakes: FakeWindow) -> None:
    async def scenario() -> FakeWebSocket:
        broadcaster = PriceBroadcaster()
        await broadcaster.reconcile_session()
        await wait_for_subscriber()
        ws = FakeWebSocket()
        broadcaster.active_connections.add(ws)  # type: ignore[arg-type]

        await broadcaster.shutdown()
        assert broadcaster.session_running is False
        return ws

    ws = asyncio.run(scenario())

    assert ws.close_code == price_broadcaster.WS_CLOSE_CODE_GOING_AWAY
    assert FakeSubscriber.instances[0].closed.is_set()
