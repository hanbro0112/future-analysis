# Price Analyzer - 價格分析服務

接收 Pub/Sub 訊息，計算每分鐘統計資訊並寫入 Firestore。

## 功能

### 即時價格分析
- 接收 Pub/Sub tick 資料
- 計算每分鐘 OHLCV 統計
- 多空比分析
- 寫入 Firestore：`market/{商品代碼}/{YYYYMMDD}/{HHMM}`

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
