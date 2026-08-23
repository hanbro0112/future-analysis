"""
測試市場情緒指標中，以路徑效率比 (Path Efficiency Ratio) 計算的波動率 (volatility)
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal

src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from price_analyzer.strategy import TickData, LongShortAnalyzer


def make_tick(dt: datetime, price: float) -> TickData:
    """建立最小可用的測試 tick 資料"""
    return TickData(
        code="MXFF6",
        datetime=dt,
        open=Decimal(str(price)),
        underlying_price=Decimal(str(price - 10)),
        bid_side_total_vol=1000,
        ask_side_total_vol=1000,
        avg_price=Decimal(str(price)),
        close=Decimal(str(price)),
        high=Decimal(str(price + 5)),
        low=Decimal(str(price - 5)),
        amount=Decimal(str(price)),
        total_amount=Decimal(str(price * 100)),
        volume=10,
        total_volume=1000,
        tick_type=1,
        chg_type=2,
        price_chg=Decimal("0"),
        pct_chg=Decimal("0"),
        simtrade=False,
    )


def test_monotonic_trend_has_low_volatility():
    """單向盤整（每筆都朝同一方向）：PER 應接近 1，volatility 應接近 0"""
    analyzer = LongShortAnalyzer()
    base_time = datetime(2026, 8, 24, 9, 0, 0)

    result = None
    for i in range(10):
        tick = make_tick(base_time + timedelta(seconds=i * 5), price=21800 + i)
        result = analyzer.analyze(tick)

    assert result is not None
    assert result.sentiment_indicator.volatility < 5.0


def test_oscillating_price_has_high_volatility():
    """來回震盪（漲跌交替、淨位移趨近於 0）：PER 應接近 0，volatility 應接近 100"""
    analyzer = LongShortAnalyzer()
    base_time = datetime(2026, 8, 24, 9, 0, 0)

    result = None
    for i in range(10):
        price = 21800 + (5 if i % 2 == 0 else -5)
        tick = make_tick(base_time + timedelta(seconds=i * 5), price=price)
        result = analyzer.analyze(tick)

    assert result is not None
    assert result.sentiment_indicator.volatility > 80.0


def test_single_tick_defaults_to_zero_volatility():
    """視窗內只有一筆 tick（不足以構成路徑）時，volatility 應為 0（PER 視為 1.0）"""
    analyzer = LongShortAnalyzer()
    tick = make_tick(datetime(2026, 8, 24, 9, 0, 0), price=21800)

    result = analyzer.analyze(tick)

    assert result is not None
    assert result.sentiment_indicator.volatility == 0.0
