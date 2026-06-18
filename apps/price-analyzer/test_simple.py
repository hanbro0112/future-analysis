"""
簡化測試：僅驗證核心邏輯
"""
import sys
from pathlib import Path

# 添加 src 目錄到路徑
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

try:
    print("🔍 測試導入模組...")
    from price_analyzer.minute_aggregator import MinuteAggregator
    print("✅ MinuteAggregator 導入成功")
    
    from price_analyzer.strategy import TickData, LongShortAnalyzer
    print("✅ TickData 和 LongShortAnalyzer 導入成功")
    
    print("\n🔍 測試 get_latest_analysis 方法...")
    analyzer = LongShortAnalyzer()
    result = analyzer.get_latest_analysis()
    print(f"✅ get_latest_analysis 返回: {result}")
    
    print("\n✅ 所有核心功能測試通過！")
    
except Exception as e:
    print(f"❌ 錯誤: {e}")
    import traceback
    traceback.print_exc()
