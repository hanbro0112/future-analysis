"""
Cloud Functions 進入點
Cloud Scheduler 透過 HTTP 觸發 daily_report / chip_report
"""
from daily_report import daily_report
from chip_report import chip_report

__all__ = ["daily_report", "chip_report"]
