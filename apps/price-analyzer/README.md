# Price Analyzer - 價格分析服務

接收 Pub/Sub 訊息，計算每分鐘統計資訊並寫入 Firestore。

## 功能

### 即時價格分析
- 接收 Pub/Sub tick 資料
- 計算每分鐘 OHLCV 統計
- 多空比分析
- 寫入 Firestore：`market/{商品代碼}/{YYYYMMDD}/{HHMM}`

## 元件說明

| 檔案 | 功用 |
| --- | --- |
| `main.py` | 服務啟動入口 |
| `src/price_analyzer/__init__.py` | 主流程：訂閱 Pub/Sub、`dict_to_tick` 轉換訊息、驅動分析與分鐘聚合、分鐘完成時寫入 Firestore、health check server |
| `src/price_analyzer/strategy.py` | 多空比分析策略：`LongShortAnalyzer` 彙整成交量爆量偵測（`VolumeExplosionIndicator`）、期現價差（`BasisAnalysis`）、市場情緒（`SentimentIndicator`）、多空比（`LongShortRatio`），詳見 [STRATEGY_README.md](src/price_analyzer/STRATEGY_README.md) |
| `src/price_analyzer/minute_aggregator.py` | `MinuteAggregator` 收集每分鐘 tick 並計算 OHLC 統計，逐分鐘產出 `MinuteBar` |

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
