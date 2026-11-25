"""
測試籌碼報告處理功能
"""
from datetime import datetime

import chip_report as chip_report_module
from chip_report import process_chip_report, resolve_report_date


def test_resolve_report_date_before_rollover_uses_previous_day():
    """午夜後、下午 3 點前仍視為前一個報告日"""
    result = resolve_report_date(datetime(2026, 11, 26, 0, 5))
    assert result.date() == datetime(2026, 11, 25).date()

    result = resolve_report_date(datetime(2026, 11, 26, 14, 59))
    assert result.date() == datetime(2026, 11, 25).date()


def test_resolve_report_date_after_rollover_uses_today():
    """下午 3 點後才換日（Scheduler 於 15:21 觸發需取得當天）"""
    result = resolve_report_date(datetime(2026, 11, 26, 15, 0))
    assert result.date() == datetime(2026, 11, 26).date()

    result = resolve_report_date(datetime(2026, 11, 26, 15, 21))
    assert result.date() == datetime(2026, 11, 26).date()


def test_resolve_report_date_crosses_month_boundary():
    """月初午夜後應回到上個月最後一天"""
    result = resolve_report_date(datetime(2026, 12, 1, 0, 30))
    assert result.date() == datetime(2026, 11, 30).date()


def test_chip_report_entry_uses_resolved_date(monkeypatch):
    """HTTP entry point 過了午夜重新觸發時，應以前一天為目標日期"""
    captured: list[datetime] = []

    monkeypatch.setattr(chip_report_module, "now_taipei", lambda: datetime(2026, 11, 26, 0, 5))

    def _fake_process(target_date: datetime) -> bool:
        captured.append(target_date)
        return True

    monkeypatch.setattr(chip_report_module, "process_chip_report", _fake_process)

    body, status = chip_report_module.chip_report(None)

    assert status == 200
    assert captured[0].date() == datetime(2026, 11, 25).date()


def test_chip_report():
    """測試籌碼報告處理"""
    print("開始測試籌碼報告處理...\n")

    # 測試今天的報告
    target_date = datetime.now()
    success = process_chip_report(target_date)

    if success:
        print("\n✅ 測試通過")
    else:
        print("\n❌ 測試失敗")

    return success


if __name__ == "__main__":
    test_chip_report()
