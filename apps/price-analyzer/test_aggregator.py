"""
測試分鐘聚合器功能
"""
import sys
from pathlib import Path

# 添加 src 目錄到路徑
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from datetime import datetime, timedelta
from decimal import Decimal
from price_analyzer.strategy import TickData
from price_analyzer.minute_aggregator import MinuteAggregator


def create_mock_tick(
    code: str = "MXFF6",
    dt: datetime = None,
    price: float = 21800,
    volume: int = 10,
    tick_type: int = 1
) -> TickData:
    """建立模擬 tick 資料"""
    if dt is None:
        dt = datetime.now()
    
    return TickData(
        code=code,
        datetime=dt,
        open=Decimal(str(price)),
        underlying_price=Decimal(str(price - 10)),
        bid_side_total_vol=1000,
        ask_side_total_vol=1000,
        avg_price=Decimal(str(price)),
        close=Decimal(str(price)),
        high=Decimal(str(price + 5)),
        low=Decimal(str(price - 5)),
        amount=Decimal(str(price * volume)),
        total_amount=Decimal(str(price * volume * 100)),
        volume=volume,
        total_volume=volume * 100,
        tick_type=tick_type,
        chg_type=2,
        price_chg=Decimal('50'),
        pct_chg=Decimal('0.23'),
        simtrade=False
    )


def test_minute_aggregator():
    """測試分鐘聚合器"""
    completed_bars = []
    
    def on_complete(bar):
        completed_bars.append(bar)
        print(f"✅ 完成分鐘資料: {bar.time} | O:{bar.open} H:{bar.high} L:{bar.low} C:{bar.close} V:{bar.volume}")
    
    aggregator = MinuteAggregator(on_minute_complete=on_complete)
    
    # 建立測試資料：3 個不同分鐘的 tick
    base_time = datetime(2026, 6, 17, 9, 0, 0)
    
    # 第一分鐘：09:00
    print("\n=== 第一分鐘 09:00 ===")
    for i in range(5):
        tick = create_mock_tick(
            dt=base_time + timedelta(seconds=i*10),
            price=21800 + i,
            volume=10,
            tick_type=1 if i % 2 == 0 else 2
        )
        aggregator.add_tick(tick)
        print(f"  + Tick {i+1}: {tick.close} @ {tick.datetime.strftime('%H:%M:%S')}")
    
    # 第二分鐘：09:01（會觸發第一分鐘完成）
    print("\n=== 第二分鐘 09:01 ===")
    for i in range(5):
        tick = create_mock_tick(
            dt=base_time + timedelta(minutes=1, seconds=i*10),
            price=21805 + i,
            volume=15,
            tick_type=2 if i % 2 == 0 else 1
        )
        aggregator.add_tick(tick)
        print(f"  + Tick {i+1}: {tick.close} @ {tick.datetime.strftime('%H:%M:%S')}")
    
    # 第三分鐘：09:02（會觸發第二分鐘完成）
    print("\n=== 第三分鐘 09:02 ===")
    for i in range(3):
        tick = create_mock_tick(
            dt=base_time + timedelta(minutes=2, seconds=i*10),
            price=21810 + i,
            volume=20,
            tick_type=1
        )
        aggregator.add_tick(tick)
        print(f"  + Tick {i+1}: {tick.close} @ {tick.datetime.strftime('%H:%M:%S')}")
    
    # 強制完成所有剩餘的資料
    print("\n=== 強制完成剩餘資料 ===")
    aggregator.flush_all()
    
    # 驗證結果
    print(f"\n=== 測試結果 ===")
    print(f"完成的分鐘數: {len(completed_bars)}")
    
    for i, bar in enumerate(completed_bars, 1):
        print(f"\n分鐘 {i}: {bar.date} {bar.time}")
        print(f"  商品代碼: {bar.code}")
        print(f"  市場類型: {bar.market_type}")
        print(f"  OHLC: {bar.open} / {bar.high} / {bar.low} / {bar.close}")
        print(f"  成交量: {bar.volume} (買:{bar.buy_volume} 賣:{bar.sell_volume})")
        print(f"  Tick 數: {bar.tick_count}")
        print(f"  Firestore 路徑: market/{bar.code[:3]}/{bar.date.replace('-', '')}/{bar.time}")


def test_market_type():
    """測試市場時段判定"""
    aggregator = MinuteAggregator()
    
    test_times = [
        (datetime(2026, 6, 17, 8, 45), "regular", "日盤開始"),
        (datetime(2026, 6, 17, 10, 30), "regular", "日盤中"),
        (datetime(2026, 6, 17, 13, 45), "regular", "日盤結束"),
        (datetime(2026, 6, 17, 15, 0), "after_hours", "夜盤開始"),
        (datetime(2026, 6, 17, 22, 30), "after_hours", "夜盤中"),
        (datetime(2026, 6, 18, 3, 0), "after_hours", "夜盤深夜"),
        (datetime(2026, 6, 18, 5, 0), "after_hours", "夜盤結束"),
    ]
    
    print("\n=== 市場時段判定測試 ===")
    for dt, expected, desc in test_times:
        result = aggregator._get_market_type(dt)
        status = "✅" if result == expected else "❌"
        print(f"{status} {dt.strftime('%H:%M')} -> {result} ({desc})")


if __name__ == "__main__":
    print("🧪 開始測試分鐘聚合器\n")
    test_minute_aggregator()
    test_market_type()
    print("\n✨ 測試完成")
