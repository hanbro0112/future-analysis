"""
測試增量滑動視窗：結果必須與「每筆 tick 重新掃描整個視窗」的舊算法完全一致

舊算法（TimeWindowStats.add_tick 逐筆重放、反向掃描連續內外盤、逐筆計算 Choppiness）
在這裡保留成測試用的對照組（oracle），用隨機 tick 序列逐筆比對。
"""
import math
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "src"))

from price_analyzer.strategy import LongShortAnalyzer, SlidingWindow, TickData, TimeWindowStats

BASE_TIME = datetime(2026, 8, 24, 9, 0, 0)


def make_tick(dt: datetime, price: int = 21800, volume: int = 10, tick_type: int = 1, amount: Decimal | None = None) -> TickData:
    return TickData(
        code="MXFF6",
        datetime=dt,
        open=Decimal(price),
        underlying_price=Decimal(price - 10),
        bid_side_total_vol=1000,
        ask_side_total_vol=1000,
        avg_price=Decimal(price),
        close=Decimal(price),
        high=Decimal(price),
        low=Decimal(price),
        amount=amount if amount is not None else Decimal(price * volume),
        total_amount=Decimal(price * 100),
        volume=volume,
        total_volume=1000,
        tick_type=tick_type,
        chg_type=2,
        price_chg=Decimal("0"),
        pct_chg=Decimal("0"),
        simtrade=False,
    )


def random_ticks(seed: int, count: int, max_gap_seconds: int = 40) -> list[TickData]:
    """產生時間遞增（允許同一時間多筆）的隨機 tick，涵蓋 tick_type 0 / 1 / 2 與價格不變的情況"""
    rng = random.Random(seed)
    ticks: list[TickData] = []
    current = BASE_TIME
    price = 21800
    for _ in range(count):
        current += timedelta(seconds=rng.randint(0, max_gap_seconds))
        price += rng.choice([-2, -1, 0, 0, 1, 2])
        ticks.append(
            make_tick(
                current,
                price=price,
                volume=rng.randint(1, 20),
                tick_type=rng.choice([0, 0, 1, 2]),
                amount=Decimal(rng.randint(100, 5000)),
            )
        )
    return ticks


class OracleWindow:
    """舊算法：保留視窗內所有 tick，每次從頭重放計算"""

    def __init__(self, minutes: int) -> None:
        self.minutes = minutes
        self.ticks: list[TickData] = []

    def add(self, tick: TickData) -> None:
        self.ticks.append(tick)
        cutoff = tick.datetime - timedelta(minutes=self.minutes)
        while self.ticks and self.ticks[0].datetime < cutoff:
            self.ticks.pop(0)

    def stats(self) -> TimeWindowStats:
        stats = TimeWindowStats(duration_minutes=self.minutes)
        for tick in self.ticks:
            stats.add_tick(tick)
        return stats

    def continuous_direction(self) -> int:
        if len(self.ticks) < 2:
            return 0
        direction = 0
        for tick in reversed(self.ticks):
            if tick.tick_type == 1:
                if direction >= 0:
                    direction += 1
                else:
                    break
            elif tick.tick_type == 2:
                if direction <= 0:
                    direction -= 1
                else:
                    break
        return direction

    def choppiness_index(self) -> float:
        closes = [float(tick.close) for tick in self.ticks]
        steps = len(closes) - 1
        if steps < 2:
            return 0.0
        path_length = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
        price_range = max(closes) - min(closes)
        if price_range == 0 or path_length == 0:
            return 0.0
        ci = 100 * math.log10(path_length / price_range) / math.log10(steps)
        return max(0.0, min(ci, 100.0))


def assert_same_stats(actual: TimeWindowStats, expected: TimeWindowStats) -> None:
    assert actual.duration_minutes == expected.duration_minutes
    assert actual.tick_count == expected.tick_count
    assert actual.total_volume == expected.total_volume
    assert actual.buy_volume == expected.buy_volume
    assert actual.sell_volume == expected.sell_volume
    assert actual.buy_amount == expected.buy_amount
    assert actual.sell_amount == expected.sell_amount
    assert actual.open_price == expected.open_price
    assert actual.close_price == expected.close_price
    assert actual.high_price == expected.high_price
    assert actual.low_price == expected.low_price


@pytest.mark.parametrize("minutes", [1, 5, 30])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_sliding_window_matches_full_rescan(minutes: int, seed: int) -> None:
    """每一筆 tick 加入後，統計、連續方向、波動率都與重新掃描整個視窗的結果一致"""
    window = SlidingWindow(minutes)
    oracle = OracleWindow(minutes)

    for tick in random_ticks(seed, count=1500):
        window.add(tick)
        window.expire(tick.datetime)
        oracle.add(tick)

        assert len(window) == len(oracle.ticks)
        assert_same_stats(window.snapshot(), oracle.stats())
        assert window.continuous_direction() == oracle.continuous_direction()
        assert window.choppiness_index() == pytest.approx(oracle.choppiness_index(), abs=1e-9)


def test_window_expiring_everything_but_latest_tick() -> None:
    """隔了很久才來一筆：舊資料全部過期，新的第一筆要用「視窗第一筆」的規則重新判定"""
    window = SlidingWindow(1)
    oracle = OracleWindow(1)
    ticks = random_ticks(7, count=50, max_gap_seconds=5)
    ticks.append(make_tick(ticks[-1].datetime + timedelta(hours=1), price=22000, tick_type=0, volume=9))

    for tick in ticks:
        window.add(tick)
        window.expire(tick.datetime)
        oracle.add(tick)

    assert len(window) == 1
    assert_same_stats(window.snapshot(), oracle.stats())
    # tick_type 0 且沒有前一筆 -> 均分（9 口分成 4 / 5）
    assert (window.snapshot().buy_volume, window.snapshot().sell_volume) == (4, 5)


def test_head_reclassified_when_previous_tick_expires() -> None:
    """tick_type 0 的 tick 原本依前一筆價格推測為外盤；前一筆過期後它成為第一筆，改為均分"""
    window = SlidingWindow(1)
    first = make_tick(BASE_TIME, price=100, tick_type=1, volume=3)
    second = make_tick(BASE_TIME + timedelta(seconds=30), price=105, tick_type=0, volume=10)

    for tick in (first, second):
        window.add(tick)
        window.expire(tick.datetime)
    assert window.snapshot().buy_volume == 3 + 10  # 105 > 100，推測為外盤

    third = make_tick(BASE_TIME + timedelta(seconds=70), price=105, tick_type=1, volume=1)
    window.add(third)
    window.expire(third.datetime)  # first 過期，second 成為第一筆

    stats = window.snapshot()
    assert stats.tick_count == 2
    assert (stats.buy_volume, stats.sell_volume) == (5 + 1, 5)


def test_empty_window_snapshot_and_defaults() -> None:
    window = SlidingWindow(5)

    stats = window.snapshot()

    assert stats.tick_count == 0
    assert stats.open_price is None and stats.close_price is None
    assert stats.high_price is None and stats.low_price is None
    assert window.continuous_direction() == 0
    assert window.choppiness_index() == 0.0


def test_snapshot_is_independent_from_later_ticks() -> None:
    """snapshot 回傳獨立物件，之後加入的 tick 不會改到已經取得的統計"""
    window = SlidingWindow(5)
    window.add(make_tick(BASE_TIME, volume=5))
    snapshot = window.snapshot()

    window.add(make_tick(BASE_TIME + timedelta(seconds=1), volume=7))

    assert snapshot.total_volume == 5
    assert window.snapshot().total_volume == 12


# ========== LongShortAnalyzer ==========


def test_analyzer_skips_late_ticks_and_returns_previous_result() -> None:
    """時間早於已處理最新 tick 的遲到 tick 不納入分析，回傳上一次的結果"""
    analyzer = LongShortAnalyzer()
    latest = analyzer.analyze(make_tick(BASE_TIME + timedelta(seconds=10), volume=5))
    assert latest is not None

    result = analyzer.analyze(make_tick(BASE_TIME, volume=99))

    assert result is latest
    assert analyzer.today_tick_count == 1
    assert analyzer.today_total_volume == 5
    assert analyzer.add_tick(make_tick(BASE_TIME, volume=99)) is False


def test_analyzer_accepts_ticks_with_same_timestamp() -> None:
    analyzer = LongShortAnalyzer()

    assert analyzer.add_tick(make_tick(BASE_TIME)) is True
    assert analyzer.add_tick(make_tick(BASE_TIME)) is True
    assert analyzer.today_tick_count == 2


def test_volume_indicator_matches_full_day_average() -> None:
    """今日平均量只用累計值計算，結果要等於「對整天 tick 求和除以時間跨度」的舊算法"""
    analyzer = LongShortAnalyzer()
    ticks = random_ticks(11, count=300)

    for tick in ticks:
        analyzer.add_tick(tick)
        seen = [t for t in ticks if t.datetime <= tick.datetime][: analyzer.today_tick_count]
        indicator = analyzer._calculate_volume_indicator(current_volume=40)

        if len(seen) < 2:
            expected_avg = 40
        else:
            span = max((seen[-1].datetime - seen[0].datetime).total_seconds() / 60, 1)
            expected_avg = sum(t.volume for t in seen) / span
        assert indicator.avg_volume_today == pytest.approx(expected_avg)


def test_analyzer_does_not_keep_every_tick_of_the_day() -> None:
    """當天資料只保留累計值，不再保存每筆 tick（避免記憶體隨成交量成長）"""
    analyzer = LongShortAnalyzer()
    for tick in random_ticks(5, count=2000, max_gap_seconds=2):
        analyzer.analyze(tick)

    assert not hasattr(analyzer, "today_ticks")
    assert analyzer.today_tick_count == 2000
    assert len(analyzer._window_30min) < 2000


def test_analyzer_resets_today_totals_on_new_date() -> None:
    analyzer = LongShortAnalyzer()
    analyzer.analyze(make_tick(datetime(2026, 8, 24, 23, 59, 0), volume=8))

    analyzer.analyze(make_tick(datetime(2026, 8, 25, 0, 1, 0), volume=3))

    assert analyzer.today_tick_count == 1
    assert analyzer.today_total_volume == 3
