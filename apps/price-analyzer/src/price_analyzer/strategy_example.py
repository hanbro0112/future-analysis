"""
策略使用範例
展示如何使用 LongShortAnalyzer 分析 Tick 資料
"""
from datetime import datetime
from decimal import Decimal
from strategy import LongShortAnalyzer, TickData


def create_sample_tick(
    close: float,
    volume: int,
    tick_type: int,
    underlying_price: float,
    timestamp: datetime
) -> TickData:
    """建立範例 Tick 資料"""
    return TickData(
        code='MXFF6',
        datetime=timestamp,
        open=Decimal(str(close)),
        underlying_price=Decimal(str(underlying_price)),
        bid_side_total_vol=6318,
        ask_side_total_vol=5685,
        avg_price=Decimal(str(close)),
        close=Decimal(str(close)),
        high=Decimal(str(close + 10)),
        low=Decimal(str(close - 10)),
        amount=Decimal(str(close * volume)),
        total_amount=Decimal('542396345'),
        volume=volume,
        total_volume=12353,
        tick_type=tick_type,  # 1: 外盤(買), 2: 內盤(賣)
        chg_type=2,
        price_chg=Decimal('50'),
        pct_chg=Decimal('0.113973'),
        simtrade=False
    )


def example_bullish_scenario():
    """範例：偏多情境"""
    print("🐂 測試情境：偏多行情")
    print("-" * 60)
    
    analyzer = LongShortAnalyzer()
    base_time = datetime(2026, 5, 26, 9, 0, 0)
    
    # 模擬一系列偏多的 Tick
    ticks = [
        # 價格上漲 + 外盤為主
        create_sample_tick(43900, 10, 1, 43850, base_time),  # 外盤
        create_sample_tick(43905, 8, 1, 43850, base_time.replace(second=5)),  # 外盤
        create_sample_tick(43910, 12, 1, 43855, base_time.replace(second=10)),  # 外盤
        create_sample_tick(43908, 5, 2, 43855, base_time.replace(second=15)),  # 內盤 (小量)
        create_sample_tick(43915, 15, 1, 43860, base_time.replace(second=20)),  # 外盤 (爆量)
        create_sample_tick(43920, 18, 1, 43865, base_time.replace(second=25)),  # 外盤 (爆量)
        create_sample_tick(43918, 6, 2, 43865, base_time.replace(second=30)),  # 內盤
        create_sample_tick(43925, 20, 1, 43870, base_time.replace(second=35)),  # 外盤 (爆量)
    ]
    
    # 逐筆分析
    for tick in ticks:
        result = analyzer.analyze(tick)
        if result:
            print(f"\n時間: {tick.datetime.strftime('%H:%M:%S')} | "
                  f"價格: {tick.close} | "
                  f"量: {tick.volume} | "
                  f"{'🟢外盤' if tick.tick_type == 1 else '🔴內盤'}")
    
    # 顯示最終分析
    if result:
        print("\n" + analyzer.format_analysis(result))


def example_bearish_scenario():
    """範例：偏空情境"""
    print("\n\n🐻 測試情境：偏空行情")
    print("-" * 60)
    
    analyzer = LongShortAnalyzer()
    base_time = datetime(2026, 5, 26, 14, 0, 0)
    
    # 模擬一系列偏空的 Tick
    ticks = [
        # 價格下跌 + 內盤為主
        create_sample_tick(43900, 8, 2, 43920, base_time),  # 內盤 + 逆價差
        create_sample_tick(43895, 12, 2, 43920, base_time.replace(second=5)),  # 內盤
        create_sample_tick(43890, 15, 2, 43915, base_time.replace(second=10)),  # 內盤 (爆量)
        create_sample_tick(43892, 6, 1, 43915, base_time.replace(second=15)),  # 外盤 (小量)
        create_sample_tick(43885, 18, 2, 43910, base_time.replace(second=20)),  # 內盤 (爆量)
        create_sample_tick(43880, 20, 2, 43910, base_time.replace(second=25)),  # 內盤 (爆量)
        create_sample_tick(43883, 5, 1, 43905, base_time.replace(second=30)),  # 外盤
        create_sample_tick(43875, 22, 2, 43905, base_time.replace(second=35)),  # 內盤 (爆量)
    ]
    
    # 逐筆分析
    for tick in ticks:
        result = analyzer.analyze(tick)
        if result:
            print(f"\n時間: {tick.datetime.strftime('%H:%M:%S')} | "
                  f"價格: {tick.close} | "
                  f"量: {tick.volume} | "
                  f"{'🟢外盤' if tick.tick_type == 1 else '🔴內盤'}")
    
    # 顯示最終分析
    if result:
        print("\n" + analyzer.format_analysis(result))


def example_neutral_scenario():
    """範例：中性盤整"""
    print("\n\n⚖️  測試情境：中性盤整")
    print("-" * 60)
    
    analyzer = LongShortAnalyzer()
    base_time = datetime(2026, 5, 26, 11, 0, 0)
    
    # 模擬盤整的 Tick
    ticks = [
        create_sample_tick(43900, 8, 1, 43895, base_time),
        create_sample_tick(43902, 7, 2, 43895, base_time.replace(second=5)),
        create_sample_tick(43898, 9, 2, 43893, base_time.replace(second=10)),
        create_sample_tick(43901, 8, 1, 43898, base_time.replace(second=15)),
        create_sample_tick(43900, 7, 1, 43898, base_time.replace(second=20)),
        create_sample_tick(43899, 8, 2, 43896, base_time.replace(second=25)),
        create_sample_tick(43901, 9, 1, 43899, base_time.replace(second=30)),
        create_sample_tick(43900, 8, 2, 43899, base_time.replace(second=35)),
    ]
    
    # 逐筆分析
    for tick in ticks:
        result = analyzer.analyze(tick)
    
    # 顯示最終分析
    if result:
        print("\n" + analyzer.format_analysis(result))


if __name__ == "__main__":
    # 執行各種情境測試
    example_bullish_scenario()
    example_bearish_scenario()
    example_neutral_scenario()
    
    print("\n\n✅ 所有範例執行完成！")
