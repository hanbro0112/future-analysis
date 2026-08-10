"""
測試共用時區工具
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import timezone_utils


def test_now_taipei_converts_utc_container_clock_to_taipei_wall_clock(monkeypatch):
    """
    Cloud Functions 容器內部時鐘預設為 UTC，now_taipei() 需正確轉換，
    否則台北時間週一 09:30 會被讀成 UTC 週一 01:30，讓 daily_report /
    chip_report / ptt_chat 的交易日、時段、日期判斷全部出錯
    """
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            utc_now = datetime(2026, 8, 10, 1, 30, tzinfo=ZoneInfo("UTC"))
            return utc_now.astimezone(tz) if tz else utc_now

    monkeypatch.setattr(timezone_utils, "datetime", _FixedDatetime)

    result = timezone_utils.now_taipei()

    assert result.tzinfo is None
    assert (result.year, result.month, result.day) == (2026, 8, 10)
    assert (result.hour, result.minute) == (9, 30)
