"""
共用時區工具

Cloud Functions 容器內部時鐘預設為 UTC，daily_report / chip_report / ptt_chat
三個 entry point 都需要正確的台北時間才能判斷交易日、盤中/盤後時段與報告日期，
直接用 datetime.now() 會讀到 UTC 時間（例如台北時間週一 09:30 會被讀成
UTC 週一 01:30），統一由這裡提供轉換過的時間。
"""
from datetime import datetime
from zoneinfo import ZoneInfo

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def now_taipei() -> datetime:
    """取得目前台北時間（naive datetime，不帶 tzinfo）"""
    return datetime.now(TAIPEI_TZ).replace(tzinfo=None)
