"""
測試市場情緒指標中，改良自 Choppiness Index 計算的波動率 (volatility)

重點：波動率必須只反映價格本身來回折返的程度，不能因為視窗內 tick 數量變多
（取樣更密集）就跟著墊高。
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


def _feed_ticks(prices: list[float]) -> float:
    """依序餵入一串價格，回傳最後一筆的 volatility"""
    analyzer = LongShortAnalyzer()
    base_time = datetime(2026, 8, 24, 9, 0, 0)

    result = None
    for i, price in enumerate(prices):
        tick = make_tick(base_time + timedelta(seconds=i), price=price)
        result = analyzer.analyze(tick)

    assert result is not None
    return result.sentiment_indicator.volatility


def test_monotonic_trend_has_zero_volatility():
    """單向盤整（每筆都朝同一方向，路徑總長 = 價格範圍）：volatility 應為 0"""
    prices = [21800 + i for i in range(10)]
    assert _feed_ticks(prices) == 0


def test_oscillating_price_has_max_volatility():
    """在頭尾兩個極值間每筆都反轉：路徑總長遠大於價格範圍，volatility 應為 100"""
    prices = [21800 + (5 if i % 2 == 0 else -5) for i in range(10)]
    assert _feed_ticks(prices) == 100


def test_volatility_unaffected_by_tick_count_when_oscillating():
    """
    同樣型態的來回震盪，tick 數從 10 筆增加到 40 筆，volatility 必須維持不變（都是 100），
    不能因為取樣更密集就往上墊高——這是這次改版要修正的核心問題
    """
    prices_10 = [21800 + (5 if i % 2 == 0 else -5) for i in range(10)]
    prices_40 = [21800 + (5 if i % 2 == 0 else -5) for i in range(40)]

    assert _feed_ticks(prices_10) == 100
    assert _feed_ticks(prices_40) == 100


def test_volatility_unaffected_by_tick_count_when_trending():
    """同樣是單向走勢，tick 數從 10 筆增加到 40 筆，volatility 應維持在 0"""
    prices_10 = [21800 + i for i in range(10)]
    prices_40 = [21800 + i for i in range(40)]

    assert _feed_ticks(prices_10) == 0
    assert _feed_ticks(prices_40) == 0


def test_flat_price_has_zero_volatility():
    """視窗內價格完全沒變動（價格範圍為 0）：volatility 應為 0，不會除以零"""
    prices = [21800] * 5
    assert _feed_ticks(prices) == 0


def test_too_few_ticks_defaults_to_zero_volatility():
    """視窗內少於 3 筆 tick（不足以構成有意義的路徑）：volatility 應為 0"""
    assert _feed_ticks([21800]) == 0
    assert _feed_ticks([21800, 21805]) == 0
