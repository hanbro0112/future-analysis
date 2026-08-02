"""
測試分鐘聚合器的秒級報價明細功能（原 price-broadcaster 的每分鐘報價統計，
移入 price-analyzer 後統一由分鐘聚合器負責）
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from price_analyzer.minute_aggregator import MinuteAggregator

UTC = ZoneInfo("UTC")
TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def test_is_in_trading_hours_uses_taipei_time_not_utc():
    """UTC 08:30（= 台北 16:30，屬於夜盤時段）應判定為交易時段"""
    aggregator = MinuteAggregator()

    dt_utc = datetime(2026, 7, 27, 8, 30, tzinfo=UTC)
    dt_taipei = dt_utc.astimezone(TAIPEI_TZ)

    assert aggregator._is_in_trading_hours(dt_taipei) is True


def test_is_in_trading_hours_rejects_actual_non_trading_time():
    """台北時間 07:00（盤前休市）應判定為非交易時段"""
    aggregator = MinuteAggregator()

    dt_taipei = datetime(2026, 7, 27, 7, 0, tzinfo=TAIPEI_TZ)

    assert aggregator._is_in_trading_hours(dt_taipei) is False


def test_sample_current_second_forward_fills_missing_seconds(monkeypatch):
    """
    缺秒應只前向填充 price 欄位；有實際資料的秒數應保留完整報價資訊
    （2026-07-27 為週一，09:00 屬於日盤交易時段）
    """
    completed = []
    aggregator = MinuteAggregator(on_second_data_complete=completed.append)

    base = datetime(2026, 7, 27, 9, 0, 0)
    clock = {"now": base}
    monkeypatch.setattr("price_analyzer.minute_aggregator.now_taipei", lambda: clock["now"])

    # 第 0 秒有 tick
    aggregator.record_tick_price("MXFF6", price=100.0, underlying_price=99.0, volume=5)
    aggregator.sample_current_second()

    # 第 1 秒沒有新 tick 到達，取樣時沿用上一筆快照
    clock["now"] = base + timedelta(seconds=1)
    aggregator.sample_current_second()

    # 跳過第 2 秒的取樣（模擬該秒完全沒被取樣到），直接進到第 3 秒
    clock["now"] = base + timedelta(seconds=3)
    aggregator.record_tick_price("MXFF6", price=105.0, underlying_price=99.5, volume=2)
    aggregator.sample_current_second()

    # 進入下一分鐘，觸發上一分鐘 finalize
    clock["now"] = base + timedelta(minutes=1)
    aggregator.sample_current_second()

    assert len(completed) == 1
    bar = completed[0]
    assert bar.code == "MXFF6"
    assert bar.date == "20260727"
    assert bar.time == "0900"
    assert bar.prices["00"] == {"price": 100.0, "underlying_price": 99.0, "volume": 5}
    assert bar.prices["01"] == {"price": 100.0, "underlying_price": 99.0, "volume": 5}
    assert bar.prices["02"] == {"price": 100.0}  # 缺秒，只補 price
    assert bar.prices["03"] == {"price": 105.0, "underlying_price": 99.5, "volume": 2}
    assert bar.prices["59"] == {"price": 105.0}  # 沿用最後已知價格


def test_second_zero_missing_uses_previous_minute_last_price(monkeypatch):
    """本分鐘第 0 秒缺失時，應使用上一分鐘最後價格前向填充"""
    completed = []
    aggregator = MinuteAggregator(on_second_data_complete=completed.append)

    base = datetime(2026, 7, 27, 9, 0, 0)
    clock = {"now": base}
    monkeypatch.setattr("price_analyzer.minute_aggregator.now_taipei", lambda: clock["now"])

    # 第一分鐘只有第 59 秒有資料
    clock["now"] = base + timedelta(seconds=59)
    aggregator.record_tick_price("MXFF6", price=200.0, underlying_price=198.0, volume=3)
    aggregator.sample_current_second()

    # 進入第二分鐘，第 0 秒沒有 tick，直接從第 1 秒開始有資料
    clock["now"] = base + timedelta(minutes=1, seconds=1)
    aggregator.record_tick_price("MXFF6", price=201.0, underlying_price=198.5, volume=1)
    aggregator.sample_current_second()

    # 進入第三分鐘，觸發第二分鐘 finalize
    clock["now"] = base + timedelta(minutes=2)
    aggregator.sample_current_second()

    assert len(completed) == 2
    second_bar = completed[1]
    assert second_bar.time == "0901"
    assert second_bar.prices["00"] == {"price": 200.0}  # 沿用上一分鐘最後價格
    assert second_bar.prices["01"] == {"price": 201.0, "underlying_price": 198.5, "volume": 1}


def test_non_trading_hours_second_bar_not_emitted(monkeypatch):
    """非交易時段（盤前休市）的秒級資料不應觸發回呼寫入"""
    completed = []
    aggregator = MinuteAggregator(on_second_data_complete=completed.append)

    base = datetime(2026, 7, 27, 7, 0, 0)  # 07:00 盤前休市
    clock = {"now": base}
    monkeypatch.setattr("price_analyzer.minute_aggregator.now_taipei", lambda: clock["now"])

    aggregator.record_tick_price("MXFF6", price=100.0, underlying_price=99.0, volume=1)
    aggregator.sample_current_second()

    clock["now"] = base + timedelta(minutes=1)
    aggregator.sample_current_second()

    assert completed == []


def test_flush_all_finalizes_pending_second_data(monkeypatch):
    """程式關閉時 flush_all() 應一併完成尚未寫出的秒級明細，避免遺失最後一分鐘的資料"""
    completed = []
    aggregator = MinuteAggregator(on_second_data_complete=completed.append)

    base = datetime(2026, 7, 27, 9, 0, 0)
    monkeypatch.setattr("price_analyzer.minute_aggregator.now_taipei", lambda: base)

    aggregator.record_tick_price("MXFF6", price=100.0, underlying_price=99.0, volume=1)
    aggregator.sample_current_second()

    aggregator.flush_all()

    assert len(completed) == 1
    assert completed[0].time == "0900"
