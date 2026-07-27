"""
測試分鐘聚合器的逾時自動 flush 機制是否正確以台北時間為準（而非容器預設的 UTC）
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal

src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from price_analyzer.strategy import TickData
from price_analyzer.minute_aggregator import MinuteAggregator


def make_tick(dt: datetime) -> TickData:
    """建立最小可用的測試 tick 資料"""
    return TickData(
        code="MXFF6",
        datetime=dt,
        open=Decimal("21800"),
        underlying_price=Decimal("21790"),
        bid_side_total_vol=1000,
        ask_side_total_vol=1000,
        avg_price=Decimal("21800"),
        close=Decimal("21800"),
        high=Decimal("21805"),
        low=Decimal("21795"),
        amount=Decimal("21800"),
        total_amount=Decimal("2180000"),
        volume=10,
        total_volume=1000,
        tick_type=1,
        chg_type=2,
        price_chg=Decimal("0"),
        pct_chg=Decimal("0"),
        simtrade=False,
    )


def test_should_flush_uses_taipei_time_not_utc(monkeypatch):
    """last_minute（台北時間）與「現在」的差距若超過門檻，should_flush 應回傳 True"""
    aggregator = MinuteAggregator()
    tick_time = datetime(2026, 7, 27, 16, 30, 0)
    aggregator.add_tick(make_tick(tick_time))

    monkeypatch.setattr(
        "price_analyzer.minute_aggregator.now_taipei",
        lambda: tick_time + timedelta(minutes=2),
    )

    assert aggregator.should_flush(delay_minutes=1.5) is True


def test_should_flush_false_when_within_threshold(monkeypatch):
    """last_minute 與「現在」的差距若未超過門檻，should_flush 應回傳 False"""
    aggregator = MinuteAggregator()
    tick_time = datetime(2026, 7, 27, 16, 30, 0)
    aggregator.add_tick(make_tick(tick_time))

    monkeypatch.setattr(
        "price_analyzer.minute_aggregator.now_taipei",
        lambda: tick_time + timedelta(seconds=30),
    )

    assert aggregator.should_flush(delay_minutes=1.5) is False


def test_auto_flush_if_needed_finalizes_stale_bar(monkeypatch):
    """超過門檻時，auto_flush_if_needed 應完成該分鐘的 bar 並觸發回調"""
    completed = []
    aggregator = MinuteAggregator(on_minute_complete=completed.append)
    tick_time = datetime(2026, 7, 27, 16, 30, 0)
    aggregator.add_tick(make_tick(tick_time))

    monkeypatch.setattr(
        "price_analyzer.minute_aggregator.now_taipei",
        lambda: tick_time + timedelta(minutes=2),
    )

    bars = aggregator.auto_flush_if_needed(delay_minutes=1.5)

    assert len(bars) == 1
    assert len(completed) == 1
    assert bars[0].time == "1630"
