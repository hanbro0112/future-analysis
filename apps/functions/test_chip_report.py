"""
測試籌碼報告處理功能
"""
from datetime import datetime

from chip_report import process_chip_report


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
