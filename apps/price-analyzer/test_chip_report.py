"""
測試籌碼報告處理功能
"""
import sys
from pathlib import Path

# 添加 src 目錄到 Python 路徑
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from price_analyzer.chip_report import process_chip_report
from datetime import datetime


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
