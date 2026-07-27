"""
測試交易時段判斷是否正確以台北時間為準（而非容器預設的 UTC）
"""
import sys
from pathlib import Path
from datetime import datetime

apps_path = Path(__file__).resolve().parents[1]
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(apps_path))
sys.path.insert(0, str(src_path))

from price_listener import is_trading_hours


def test_is_trading_hours_true_during_day_session():
    """台北時間週一 10:30（日盤中）應判定為交易時段"""
    dt = datetime(2026, 7, 27, 10, 30)  # 2026-07-27 為週一

    assert is_trading_hours(dt) is True


def test_is_trading_hours_true_during_night_session():
    """台北時間週一 16:30（夜盤中）應判定為交易時段"""
    dt = datetime(2026, 7, 27, 16, 30)

    assert is_trading_hours(dt) is True


def test_is_trading_hours_false_before_market_open():
    """台北時間週一 07:00（盤前休市）應判定為非交易時段"""
    dt = datetime(2026, 7, 27, 7, 0)

    assert is_trading_hours(dt) is False


def test_is_trading_hours_false_on_weekend():
    """週六應判定為非交易時段"""
    dt = datetime(2026, 8, 1, 12, 0)  # 2026-08-01 為週六

    assert is_trading_hours(dt) is False
