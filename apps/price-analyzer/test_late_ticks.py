"""
測試聚合器對遲到（亂序）tick 的處理：

- 分鐘 / 秒級明細的 finalize 時機不變
- 遲到的 tick 更新保留在記憶體的舊 bar，並標記為 dirty
- dirty bar 定期補寫（只補寫已經過保留時間的），收盤時全部補寫
"""
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import price_analyzer
from price_analyzer.minute_aggregator import MinuteAggregator, MinuteBar, SecondBar
from price_analyzer.strategy import TickData

NOW_PATH = "price_analyzer.minute_aggregator.now_taipei"
BASE = datetime(2026, 7, 27, 9, 0, 0)  # 週一日盤


def make_tick(
    dt: datetime,
    price: float = 100.0,
    volume: int = 1,
    tick_type: int = 1,
    code: str = "MXFF6",
    bid: int = 1000,
) -> TickData:
    return TickData(
        code=code,
        datetime=dt,
        open=Decimal(str(price)),
        underlying_price=Decimal(str(price - 1)),
        bid_side_total_vol=bid,
        ask_side_total_vol=1000,
        avg_price=Decimal(str(price)),
        close=Decimal(str(price)),
        high=Decimal(str(price)),
        low=Decimal(str(price)),
        amount=Decimal(str(price * volume)),
        total_amount=Decimal("0"),
        volume=volume,
        total_volume=100,
        tick_type=tick_type,
        chg_type=2,
        price_chg=Decimal("0"),
        pct_chg=Decimal("0"),
        simtrade=False,
    )


class Recorder:
    """收集聚合器四種回調的輸出"""

    def __init__(self) -> None:
        self.minutes: list[MinuteBar] = []
        self.seconds: list[SecondBar] = []
        self.minute_updates: list[MinuteBar] = []
        self.second_updates: list[SecondBar] = []

    def make_aggregator(self, **kwargs: float) -> MinuteAggregator:
        return MinuteAggregator(
            on_minute_complete=self.minutes.append,
            on_second_data_complete=self.seconds.append,
            on_minute_update=self.minute_updates.append,
            on_second_data_update=self.second_updates.append,
            **kwargs,
        )


def test_out_of_order_ticks_within_a_minute_keep_correct_open_and_close() -> None:
    """同一分鐘內亂序到達：open 取時間最早、close 取時間最晚，與到達順序無關"""
    recorder = Recorder()
    aggregator = recorder.make_aggregator()

    aggregator.add_tick(make_tick(BASE + timedelta(seconds=30), price=105, volume=2, bid=1030))
    aggregator.add_tick(make_tick(BASE + timedelta(seconds=10), price=100, volume=3, bid=1010))
    aggregator.add_tick(make_tick(BASE + timedelta(seconds=50), price=98, volume=5, bid=1050))
    aggregator.add_tick(make_tick(BASE + timedelta(seconds=20), price=110, volume=1, bid=1020))
    aggregator.flush_all()

    bar = recorder.minutes[0]
    assert (bar.open, bar.close) == (Decimal("100"), Decimal("98"))
    assert (bar.high, bar.low) == (Decimal("110"), Decimal("98"))
    assert bar.volume == 11
    assert bar.tick_count == 4
    assert bar.bid_total_vol == 1050  # 取時間最晚那筆的委買量


def test_minute_is_finalized_once_when_next_minute_starts() -> None:
    """finalize 時機不變：第一筆下一分鐘的 tick 到達時，完成上一分鐘"""
    recorder = Recorder()
    aggregator = recorder.make_aggregator()

    aggregator.add_tick(make_tick(BASE + timedelta(seconds=5)))
    assert recorder.minutes == []

    completed = aggregator.add_tick(make_tick(BASE + timedelta(minutes=1, seconds=1)))

    assert [bar.time for bar in recorder.minutes] == ["0900"]
    assert completed is recorder.minutes[0]


def test_late_tick_updates_finalized_bar_without_refinalizing() -> None:
    """已完成的分鐘收到遲到 tick：更新保留的 bar、標記 dirty，不會再觸發 on_minute_complete"""
    recorder = Recorder()
    aggregator = recorder.make_aggregator()
    aggregator.add_tick(make_tick(BASE + timedelta(seconds=10), price=100, volume=1))
    aggregator.add_tick(make_tick(BASE + timedelta(minutes=1, seconds=1), price=101))
    assert len(recorder.minutes) == 1

    aggregator.add_tick(make_tick(BASE + timedelta(seconds=40), price=120, volume=4))

    assert len(recorder.minutes) == 1  # 沒有重複 finalize
    assert aggregator.late_updated_count == 1
    state = aggregator.minute_states[("MXFF6", BASE)]
    assert state.minute_dirty is True
    assert (state.high, state.close, state.volume) == (Decimal("120"), Decimal("120"), 5)


def test_late_tick_with_earlier_time_than_open_changes_open() -> None:
    recorder = Recorder()
    aggregator = recorder.make_aggregator()
    aggregator.add_tick(make_tick(BASE + timedelta(seconds=30), price=100))
    aggregator.add_tick(make_tick(BASE + timedelta(minutes=1), price=101))

    aggregator.add_tick(make_tick(BASE + timedelta(seconds=5), price=90))  # 遲到且比 open 更早

    state = aggregator.minute_states[("MXFF6", BASE)]
    assert (state.open, state.low, state.close) == (Decimal("90"), Decimal("90"), Decimal("100"))


def test_dirty_bars_are_rewritten_only_after_hold_time(monkeypatch) -> None:
    """定期補寫只處理分鐘結束後已過 5 分鐘的 dirty bar，最近幾分鐘先不寫"""
    recorder = Recorder()
    aggregator = recorder.make_aggregator()
    clock = {"now": BASE + timedelta(minutes=2)}
    monkeypatch.setattr(NOW_PATH, lambda: clock["now"])
    aggregator.add_tick(make_tick(BASE + timedelta(seconds=10), price=100, volume=1))
    aggregator.add_tick(make_tick(BASE + timedelta(minutes=1, seconds=1), price=101))
    aggregator.add_tick(make_tick(BASE + timedelta(seconds=40), price=120, volume=4))  # 遲到

    # 09:00 這一分鐘在 09:01 結束，要到 09:06 才會被補寫
    clock["now"] = BASE + timedelta(minutes=5, seconds=59)
    assert aggregator.flush_dirty_if_needed() == 0
    assert recorder.minute_updates == []

    clock["now"] = BASE + timedelta(minutes=7)
    assert aggregator.flush_dirty_if_needed() >= 1

    assert len(recorder.minute_updates) == 1
    updated = recorder.minute_updates[0]
    assert (updated.time, updated.high, updated.volume) == ("0900", Decimal("120"), 5)


def test_dirty_bar_is_rewritten_once_and_cleared(monkeypatch) -> None:
    recorder = Recorder()
    aggregator = recorder.make_aggregator(dirty_flush_interval_seconds=0)
    monkeypatch.setattr(NOW_PATH, lambda: BASE + timedelta(minutes=30))
    aggregator.add_tick(make_tick(BASE + timedelta(seconds=10)))
    aggregator.add_tick(make_tick(BASE + timedelta(minutes=1)))
    aggregator.add_tick(make_tick(BASE + timedelta(seconds=40)))  # 遲到

    aggregator.flush_dirty_if_needed()
    aggregator.flush_dirty_if_needed()

    assert len(recorder.minute_updates) == 1
    assert aggregator.minute_states[("MXFF6", BASE)].minute_dirty is False


def test_dirty_flush_respects_interval(monkeypatch) -> None:
    """補寫間隔內重複呼叫不會重複掃描；間隔過後遲到 tick 再次更新的 bar 會再補寫一次"""
    recorder = Recorder()
    aggregator = recorder.make_aggregator(dirty_flush_interval_seconds=60, dirty_hold_minutes=0)
    clock = {"now": BASE + timedelta(minutes=10)}
    monkeypatch.setattr(NOW_PATH, lambda: clock["now"])
    aggregator.add_tick(make_tick(BASE + timedelta(seconds=10)))
    aggregator.add_tick(make_tick(BASE + timedelta(minutes=1)))

    aggregator.add_tick(make_tick(BASE + timedelta(seconds=20)))  # 遲到 #1
    aggregator.flush_dirty_if_needed()
    assert len(recorder.minute_updates) == 1

    aggregator.add_tick(make_tick(BASE + timedelta(seconds=30)))  # 遲到 #2
    clock["now"] += timedelta(seconds=30)
    aggregator.flush_dirty_if_needed()  # 距離上次不到 60 秒
    assert len(recorder.minute_updates) == 1

    clock["now"] += timedelta(seconds=31)
    aggregator.flush_dirty_if_needed()
    assert len(recorder.minute_updates) == 2
    assert recorder.minute_updates[-1].tick_count == 3  # 原本 1 筆 + 2 筆遲到


def test_flush_all_rewrites_every_dirty_bar_regardless_of_hold(monkeypatch) -> None:
    """收盤（flush_all）時不受保留時間限制，全部 dirty bar 一次補寫"""
    recorder = Recorder()
    aggregator = recorder.make_aggregator()
    monkeypatch.setattr(NOW_PATH, lambda: BASE + timedelta(minutes=3))
    aggregator.add_tick(make_tick(BASE + timedelta(seconds=10)))
    aggregator.add_tick(make_tick(BASE + timedelta(minutes=1, seconds=10)))
    aggregator.add_tick(make_tick(BASE + timedelta(minutes=2, seconds=10)))
    aggregator.add_tick(make_tick(BASE + timedelta(seconds=40), price=120))  # 09:00 遲到
    aggregator.add_tick(make_tick(BASE + timedelta(minutes=1, seconds=40), price=130))  # 09:01 遲到

    aggregator.flush_all()

    assert [bar.time for bar in recorder.minute_updates] == ["0900", "0901"]
    assert [bar.time for bar in recorder.minutes] == ["0900", "0901", "0902"]  # 補寫的不重複算 complete


def test_late_tick_updates_finalized_second_data(monkeypatch) -> None:
    """秒級明細也能被遲到 tick 補進正確的那一秒，補寫時重新前向填充"""
    recorder = Recorder()
    aggregator = recorder.make_aggregator(dirty_hold_minutes=0)
    clock = {"now": BASE}
    monkeypatch.setattr(NOW_PATH, lambda: clock["now"])
    aggregator.add_tick(make_tick(BASE + timedelta(seconds=10), price=100, volume=2))

    clock["now"] = BASE + timedelta(minutes=1)
    aggregator.finalize_seconds_if_needed()
    assert recorder.seconds[0].prices["20"] == {"price": 100.0}  # 原本是前向填充

    aggregator.add_tick(make_tick(BASE + timedelta(seconds=20), price=105, volume=3))  # 遲到
    clock["now"] = BASE + timedelta(minutes=10)
    aggregator.flush_dirty_if_needed()

    assert len(recorder.second_updates) == 1
    prices = recorder.second_updates[0].prices
    assert prices["10"] == {"price": 100.0, "underlying_price": 99.0, "volume": 2}
    assert prices["20"] == {"price": 105.0, "underlying_price": 104.0, "volume": 3}
    assert prices["21"] == {"price": 105.0}  # 之後的秒改成沿用新的價格
    assert "09" not in prices  # 第一筆 tick（:10）之前沒有價格可填


def test_rewrite_keeps_carry_price_from_first_write(monkeypatch) -> None:
    """補寫時第 0 秒的前向填充沿用第一次寫出時的上一分鐘價格"""
    recorder = Recorder()
    aggregator = recorder.make_aggregator(dirty_hold_minutes=0)
    clock = {"now": BASE}
    monkeypatch.setattr(NOW_PATH, lambda: clock["now"])
    aggregator.add_tick(make_tick(BASE + timedelta(seconds=59), price=200))
    clock["now"] = BASE + timedelta(minutes=1)
    aggregator.finalize_seconds_if_needed()

    aggregator.add_tick(make_tick(BASE + timedelta(minutes=1, seconds=5), price=201))
    clock["now"] = BASE + timedelta(minutes=2)
    aggregator.finalize_seconds_if_needed()
    assert recorder.seconds[1].prices["00"] == {"price": 200.0}

    aggregator.add_tick(make_tick(BASE + timedelta(minutes=1, seconds=30), price=202))  # 09:01 遲到
    clock["now"] = BASE + timedelta(minutes=10)
    aggregator.flush_dirty_if_needed()

    assert recorder.second_updates[-1].prices["00"] == {"price": 200.0}


def test_late_tick_without_retained_bar_is_discarded() -> None:
    """記憶體中沒有對應 bar 的遲到 tick（例如服務重啟）不建立新 bar，避免覆蓋已完整的文件"""
    recorder = Recorder()
    aggregator = recorder.make_aggregator()
    aggregator.add_tick(make_tick(BASE + timedelta(minutes=5)))

    result = aggregator.add_tick(make_tick(BASE + timedelta(minutes=1)))

    assert result is None
    assert aggregator.late_discarded_count == 1
    assert ("MXFF6", BASE + timedelta(minutes=1)) not in aggregator.minute_states
    aggregator.flush_all()
    assert [bar.time for bar in recorder.minutes] == ["0905"]


def test_all_session_bars_are_retained_for_late_ticks() -> None:
    """保留整個時段：很久以前的分鐘收到遲到 tick 也能更新"""
    recorder = Recorder()
    aggregator = recorder.make_aggregator()
    for minute in range(0, 120, 10):
        aggregator.add_tick(make_tick(BASE + timedelta(minutes=minute, seconds=1)))

    aggregator.add_tick(make_tick(BASE + timedelta(seconds=30), price=150))  # 2 小時前的分鐘

    assert aggregator.late_discarded_count == 0
    assert aggregator.minute_states[("MXFF6", BASE)].high == Decimal("150")


def test_run_maintenance_finalizes_flushes_and_rewrites(monkeypatch) -> None:
    """定時器每秒呼叫 run_maintenance：秒級 finalize、逾時保險 flush、補寫 dirty 一次處理"""
    recorder = Recorder()
    aggregator = recorder.make_aggregator(dirty_hold_minutes=0)
    clock = {"now": BASE + timedelta(seconds=30)}
    monkeypatch.setattr(NOW_PATH, lambda: clock["now"])
    aggregator.add_tick(make_tick(BASE + timedelta(seconds=10)))

    clock["now"] = BASE + timedelta(minutes=3)  # 超過 1.5 分鐘沒有新 tick
    aggregator.run_maintenance(delay_minutes=1.5)

    assert [bar.time for bar in recorder.minutes] == ["0900"]
    assert [bar.time for bar in recorder.seconds] == ["0900"]

    aggregator.add_tick(make_tick(BASE + timedelta(seconds=40), price=120))  # 自動 flush 後才到的遲到 tick
    clock["now"] = BASE + timedelta(minutes=5)
    aggregator.run_maintenance(delay_minutes=1.5)

    assert [bar.high for bar in recorder.minute_updates] == [Decimal("120")]
    assert len(recorder.second_updates) == 1


# ========== Firestore 補寫回調 ==========


class FakeWriter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def write_document(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def test_on_minute_update_merges_without_analysis_or_created_at() -> None:
    writer = FakeWriter()
    bar = MinuteBar(
        code="MXFF6", timestamp=BASE, date="2026-07-27", time="0900", market_type="regular",
        open=Decimal("100"), high=Decimal("120"), low=Decimal("100"), close=Decimal("120"), volume=5,
    )

    price_analyzer.on_minute_update(bar, writer)

    call = writer.calls[0]
    assert call["collection"] == "market/MXF/20260727"
    assert call["document_id"] == "0900"
    assert call["merge"] is True
    assert call["set_created_at"] is False
    assert "analysis" not in call["data"]
    assert call["data"]["high"] == 120.0


def test_on_second_data_update_merges_without_resetting_created_at() -> None:
    writer = FakeWriter()
    bar = SecondBar(code="MXFF6", date="20260727", time="0900", prices={"00": {"price": 100.0}})

    price_analyzer.on_second_data_update(bar, writer)

    call = writer.calls[0]
    assert call["collection"] == "market/MXF/20260727_tick"
    assert call["document_id"] == "0900"
    assert (call["merge"], call["set_created_at"]) == (True, False)
    assert call["data"] == {"00": {"price": 100.0}}
