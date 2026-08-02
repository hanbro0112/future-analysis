# Price Analyzer - 價格分析服務

接收 Pub/Sub 訊息，計算每分鐘統計資訊並寫入 Firestore。

## 功能

### 即時價格分析
- 接收 Pub/Sub tick 資料
- 計算每分鐘 OHLCV 統計
- 多空比分析
- 寫入 Firestore：`market/{商品代碼}/{YYYYMMDD}/{HHMM}`

### 秒級報價明細（原 price-broadcaster 職責）
- 每秒取樣目前已知的最新報價（price、underlying_price、每秒總成交量）
- 缺秒前向填充：缺失的秒數只填充 `price` 欄位；本分鐘第 0 秒缺失時使用上一分鐘最後價格
- 夜盤跨日處理：00:00-05:59 的資料儲存到前一天
- 只在交易時段內才寫入，非交易時段的秒級資料會被捨棄
- 寫入 Firestore：`market/{商品代碼}/{YYYYMMDD}_tick/{HHMM}`，格式為 `{秒數: {price, underlying_price, volume}}`（固定 60 筆，`00`~`59`）

## Flush 機制

分鐘 OHLC 與秒級明細共用同一個每秒觸發的背景定時器（`schedule_auto_flush`），而非各自獨立排程：
- **每秒取樣**：`MinuteAggregator.sample_current_second()` 取樣秒級報價，並在偵測到分鐘邊界時完成上一分鐘的秒級明細
- **逾時保險 flush**：`MinuteAggregator.auto_flush_if_needed(delay_minutes=1.5)` 檢查是否有分鐘 OHLC 因為沒有新 tick 到達而卡住，超過門檻就強制完成
- 分鐘 OHLC 的即時 finalize 仍由 tick 驅動（新分鐘的 tick 到達時，自動完成上一分鐘），定時器只是保險機制

## 元件說明

| 檔案 | 功用 |
| --- | --- |
| `main.py` | 服務啟動入口 |
| `src/price_analyzer/__init__.py` | 主流程：訂閱 Pub/Sub、`dict_to_tick` 轉換訊息、驅動分析與分鐘聚合、每秒背景定時器（秒級取樣 + 逾時保險 flush）、分鐘/秒級資料完成時寫入 Firestore、health check server |
| `src/price_analyzer/strategy.py` | 多空比分析策略：`LongShortAnalyzer` 彙整成交量爆量偵測（`VolumeExplosionIndicator`）、期現價差（`BasisAnalysis`）、市場情緒（`SentimentIndicator`）、多空比（`LongShortRatio`），詳見 [STRATEGY_README.md](src/price_analyzer/STRATEGY_README.md) |
| `src/price_analyzer/minute_aggregator.py` | `MinuteAggregator` 收集每分鐘 tick 並計算 OHLC 統計，逐分鐘產出 `MinuteBar`；同時收集每秒報價快照，前向填充後產出 `SecondBar` |

## 環境變數

```bash
# GCP 專案設定
GCP_PROJECT_ID=demo-project
PUBSUB_TOPIC_ID=price-updates
PUBSUB_SUBSCRIPTION_ID=price-subscription

# Firestore Emulator (開發環境)
FIRESTORE_EMULATOR_HOST=localhost:8080
PUBSUB_EMULATOR_HOST=localhost:8085
```

## 安裝依賴

```bash
cd apps/price-analyzer
uv sync
```

## 執行

### 啟動服務

```bash
cd apps
uv run --package price-analyzer python -m price_analyzer.main
```
