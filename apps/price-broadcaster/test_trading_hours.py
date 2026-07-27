"""
測試交易時段判斷是否正確以台北時間為準（而非容器預設的 UTC）
"""
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

apps_path = Path(__file__).resolve().parents[1]
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(apps_path))
sys.path.insert(0, str(src_path))

from price_broadcaster import PriceBroadcaster, TAIPEI_TZ

UTC = ZoneInfo("UTC")


def test_is_in_trading_hours_uses_taipei_time_not_utc():
    """UTC 08:30（= 台北 16:30，屬於夜盤時段）應判定為交易時段"""
    broadcaster = PriceBroadcaster()

    dt_utc = datetime(2026, 7, 27, 8, 30, tzinfo=UTC)
    dt_taipei = dt_utc.astimezone(TAIPEI_TZ)

    assert broadcaster._is_in_trading_hours(dt_taipei) is True


def test_is_in_trading_hours_rejects_actual_non_trading_time():
    """台北時間 07:00（盤前休市）應判定為非交易時段"""
    broadcaster = PriceBroadcaster()

    dt_taipei = datetime(2026, 7, 27, 7, 0, tzinfo=TAIPEI_TZ)

    assert broadcaster._is_in_trading_hours(dt_taipei) is False


def test_get_market_type_matches_taipei_night_session():
    """台北時間 16:30 應歸類為夜盤（after_hours）"""
    broadcaster = PriceBroadcaster()

    dt_taipei = datetime(2026, 7, 27, 16, 30, tzinfo=TAIPEI_TZ)

    assert broadcaster._get_market_type(dt_taipei) == "after_hours"
