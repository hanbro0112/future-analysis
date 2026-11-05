"""
測試分鐘聚合器的秒級報價明細功能（原 price-broadcaster 的每分鐘報價統計，
移入 price-analyzer 後統一由分鐘聚合器負責）

秒級明細以 tick 自己的時間戳歸屬到對應的秒；finalize 的時機仍由 wall clock 的分鐘交界決定。
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from price_analyzer.minute_aggregator import MinuteAggregator
from price_analyzer.strategy import TickData

UTC = ZoneInfo("UTC")
TAIPEI_TZ = ZoneInfo("Asia/Taipei")

NOW_PATH = "price_analyzer.minute_aggregator.now_taipei"


def make_tick(dt: datetime, price: float, underlying: float, volume: int, code: str = "MXFF6") -> TickData:
    return TickData(
        code=code,
        datetime=dt,
        open=Decimal(str(price)),
        underlying_price=Decimal(str(underlying)),
        bid_side_total_vol=1000,
        ask_side_total_vol=1000,
        avg_price=Decimal(str(price)),
        close=Decimal(str(price)),
        high=Decimal(str(price)),
        low=Decimal(str(price)),
        amount=Decimal(str(price * volume)),
        total_amount=Decimal("0"),
        volume=volume,
        total_volume=100,
        tick_type=1,
        chg_type=2,
        price_chg=Decimal("0"),
        pct_chg=Decimal("0"),
        simtrade=False,
    )


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


def test_forward_fills_missing_seconds(monkeypatch):
    """
    缺秒應只前向填充 price 欄位；有實際 tick 的秒數應保留完整報價資訊
    （2026-07-27 為週一，09:00 屬於日盤交易時段）
    """
    completed = []
    aggregator = MinuteAggregator(on_second_data_complete=completed.append)
    base = datetime(2026, 7, 27, 9, 0, 0)
    clock = {"now": base}
    monkeypatch.setattr(NOW_PATH, lambda: clock["now"])

    aggregator.add_tick(make_tick(base, price=100.0, underlying=99.0, volume=5))
    aggregator.add_tick(make_tick(base + timedelta(seconds=3), price=105.0, underlying=99.5, volume=2))

    # 進入下一分鐘，觸發上一分鐘的秒級明細 finalize
    clock["now"] = base + timedelta(minutes=1)
    aggregator.finalize_seconds_if_needed()

    assert len(completed) == 1
    bar = completed[0]
    assert bar.code == "MXFF6"
    assert bar.date == "20260727"
    assert bar.time == "0900"
    assert bar.prices["00"] == {"price": 100.0, "underlying_price": 99.0, "volume": 5}
    assert bar.prices["01"] == {"price": 100.0}  # 缺秒，只補 price
    assert bar.prices["02"] == {"price": 100.0}
    assert bar.prices["03"] == {"price": 105.0, "underlying_price": 99.5, "volume": 2}
    assert bar.prices["59"] == {"price": 105.0}  # 沿用最後已知價格


def test_second_is_attributed_by_tick_time_not_wall_clock(monkeypatch):
    """處理落後時，tick 仍歸屬到它自己的秒，不會被記到處理當下的秒"""
    completed = []
    aggregator = MinuteAggregator(on_second_data_complete=completed.append)
    base = datetime(2026, 7, 27, 9, 0, 0)
    clock = {"now": base + timedelta(seconds=40)}  # tick 時間是 :10，但實際處理時已經 :40
    monkeypatch.setattr(NOW_PATH, lambda: clock["now"])

    aggregator.add_tick(make_tick(base + timedelta(seconds=10), price=100.0, underlying=99.0, volume=3))

    clock["now"] = base + timedelta(minutes=1)
    aggregator.finalize_seconds_if_needed()

    bar = completed[0]
    assert "00" not in bar.prices  # :10 之前沒有任何價格可以填
    assert bar.prices["10"] == {"price": 100.0, "underlying_price": 99.0, "volume": 3}
    assert bar.prices["40"] == {"price": 100.0}  # 處理當下的 :40 只是前向填充


def test_same_second_accumulates_volume_and_keeps_latest_price(monkeypatch):
    """同一秒多筆 tick：成交量累加，價格取時間最晚的一筆（即使它先到達）"""
    completed = []
    aggregator = MinuteAggregator(on_second_data_complete=completed.append)
    base = datetime(2026, 7, 27, 9, 0, 0)
    clock = {"now": base}
    monkeypatch.setattr(NOW_PATH, lambda: clock["now"])

    aggregator.add_tick(make_tick(base + timedelta(milliseconds=800), price=102.0, underlying=99.2, volume=4))
    aggregator.add_tick(make_tick(base + timedelta(milliseconds=100), price=101.0, underlying=99.1, volume=1))
    aggregator.add_tick(make_tick(base + timedelta(milliseconds=500), price=103.0, underlying=99.3, volume=2))

    clock["now"] = base + timedelta(minutes=1)
    aggregator.finalize_seconds_if_needed()

    # 時間最晚的是 800ms 那筆（價格 102），成交量 4 + 1 + 2
    assert completed[0].prices["00"] == {"price": 102.0, "underlying_price": 99.2, "volume": 7}


def test_seconds_not_finalized_before_wall_clock_minute_changes(monkeypatch):
    """finalize 時機由 wall clock 決定：分鐘還沒過完不寫出，過了才寫出"""
    completed = []
    aggregator = MinuteAggregator(on_second_data_complete=completed.append)
    base = datetime(2026, 7, 27, 9, 0, 0)
    clock = {"now": base + timedelta(seconds=30)}
    monkeypatch.setattr(NOW_PATH, lambda: clock["now"])
    aggregator.add_tick(make_tick(base + timedelta(seconds=5), price=100.0, underlying=99.0, volume=1))

    aggregator.finalize_seconds_if_needed()
    assert completed == []

    clock["now"] = base + timedelta(minutes=1)
    aggregator.finalize_seconds_if_needed()
    assert len(completed) == 1

    aggregator.finalize_seconds_if_needed()  # 重複呼叫不會再寫一次
    assert len(completed) == 1


def test_second_zero_missing_uses_previous_minute_last_price(monkeypatch):
    """本分鐘第 0 秒缺失時，應使用上一分鐘最後價格前向填充"""
    completed = []
    aggregator = MinuteAggregator(on_second_data_complete=completed.append)
    base = datetime(2026, 7, 27, 9, 0, 0)
    clock = {"now": base}
    monkeypatch.setattr(NOW_PATH, lambda: clock["now"])

    # 第一分鐘只有第 59 秒有資料
    aggregator.add_tick(make_tick(base + timedelta(seconds=59), price=200.0, underlying=198.0, volume=3))
    clock["now"] = base + timedelta(minutes=1)
    aggregator.finalize_seconds_if_needed()

    # 第二分鐘第 0 秒沒有 tick，直接從第 1 秒開始有資料
    aggregator.add_tick(make_tick(base + timedelta(minutes=1, seconds=1), price=201.0, underlying=198.5, volume=1))
    clock["now"] = base + timedelta(minutes=2)
    aggregator.finalize_seconds_if_needed()

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
    monkeypatch.setattr(NOW_PATH, lambda: clock["now"])

    aggregator.add_tick(make_tick(base, price=100.0, underlying=99.0, volume=1))
    clock["now"] = base + timedelta(minutes=1)
    aggregator.finalize_seconds_if_needed()

    assert completed == []


def test_flush_all_finalizes_pending_second_data(monkeypatch):
    """程式關閉時 flush_all() 應一併完成尚未寫出的秒級明細，避免遺失最後一分鐘的資料"""
    completed = []
    aggregator = MinuteAggregator(on_second_data_complete=completed.append)
    base = datetime(2026, 7, 27, 9, 0, 0)
    monkeypatch.setattr(NOW_PATH, lambda: base)

    aggregator.add_tick(make_tick(base, price=100.0, underlying=99.0, volume=1))

    aggregator.flush_all()

    assert len(completed) == 1
    assert completed[0].time == "0900"


def test_after_hours_second_bar_uses_previous_date_after_midnight(monkeypatch):
    """夜盤跨日（00:00-05:59）的秒級明細，文件日期與分鐘 OHLC 一樣使用前一天"""
    completed = []
    aggregator = MinuteAggregator(on_second_data_complete=completed.append)
    base = datetime(2026, 7, 28, 1, 30, 0)  # 週二凌晨，屬於週一夜盤
    monkeypatch.setattr(NOW_PATH, lambda: base)

    aggregator.add_tick(make_tick(base, price=100.0, underlying=99.0, volume=1))
    aggregator.flush_all()

    assert completed[0].date == "20260727"
    assert completed[0].time == "0130"
