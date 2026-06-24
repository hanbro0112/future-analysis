# future-analysis
分析台指期多空交易資訊




# firestore data structure
market (Collection)
  ┗ 📄 MXF (Document - 商品代碼，如小台指期全)
        ┗ 📂 20260617 (Subcollection - 交易日)
            ┗ 📄 0901 (Document ID: 時分 - 每分鐘資訊分析)
            ┗ 📄 0902 
              ├── timestamp: 2026-06-15T09:01:00Z (Timestamp)
              ├── date: "2026-06-15" (String)
              ├── market_type: "regular" (String - regular / after_hours 日盤/夜盤)
              ├── open: 21850 (Number)
              ├── high: 21865 (Number)
              ├── low: 21840 (Number)
              ├── close: 21855 (Number)
              ├── volume: 1250 (Number - 分鐘總成交量)
              └── 其他分析資料


# tick data structure
Tick(
    code='MXFF6',                                  # 期貨商品代碼 (例如：MXFF6 代表 微型臺指期貨 2026年6月合約)
    datetime=datetime.datetime(2026, 5, 25, 16, 19, 39, 243000), # 交易所派發該筆行情的時間 (精確至微秒)
    open=Decimal('43845'),                         # 今日開盤價
    underlying_price=Decimal('43644.4'),           # 現貨標的指數當前價格 (例如大盤加權指數，用以計算期現貨價差)
    bid_side_total_vol=6318,                       # 委買總量 / 買方所有掛單委託的總口數
    ask_side_total_vol=5685,                       # 委賣總量 / 賣方所有掛單委託的總口數
    avg_price=Decimal('43908.066462'),             # 今日截至目前的成交均價 (總成交金額 / 總成交口數)
    close=Decimal('43920'),                        # 最新成交價 (當前這一筆撮合的價格)
    high=Decimal('43974'),                         # 今日盤中最高價
    low=Decimal('43806'),                          # 今日盤中最低價
    amount=Decimal('263520'),                      # 單筆成交金額 (此筆撮合口數所對應的契約價值或實質金額)
    total_amount=Decimal('542396345'),             # 今日累計總成交金額
    volume=6,                                      # 單筆成交量 / 本次撮合成交口數 (Lot)
    total_volume=12353,                            # 今日累計總成交量 (口數)
    tick_type=2,                                   # 成交內外盤判定 {1: 外盤/買進, 2: 內盤/賣出, 0: 無法判定}
    chg_type=2,                                    # 漲跌狀態標記 {1: 漲停, 2: 上漲, 3: 平盤, 4: 下跌, 5: 跌停}
    price_chg=Decimal('50'),                       # 漲跌價差 (最新成交價對比昨日收盤/結算價的絕對差額)
    pct_chg=Decimal('0.113973'),                   # 漲跌幅百分比 (例如：0.113973 代表上漲了約 0.114%)
    simtrade=False                                 # 是否為盤前/盤中試撮狀態 {True: 試撮未真正成交, False: 實時正式成交}
)