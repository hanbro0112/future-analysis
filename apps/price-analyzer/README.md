# Price Analyzer - 價格分析服務

接收 Pub/Sub 訊息，計算每分鐘統計資訊並寫入 Firestore，並提供每日市場分析報告。

## 功能

### 1. 即時價格分析
- 接收 Pub/Sub tick 資料
- 計算每分鐘 OHLCV 統計
- 多空比分析
- 寫入 Firestore：`market/{商品代碼}/{YYYYMMDD}/{HHMM}`

### 2. 每日市場分析報告
- 每天交易日 08:00 自動生成
- 使用 Gemini 3.5 Flash 分析台股和美股
- 自動跳過週末和假日
- 儲存到 Firestore：`daily_reports/{YYYYMMDD}`

## 環境變數

```bash
# GCP 專案設定
GCP_PROJECT_ID=demo-project
PUBSUB_TOPIC_ID=price-updates
PUBSUB_SUBSCRIPTION_ID=price-subscription

# Firestore Emulator (開發環境)
FIRESTORE_EMULATOR_HOST=localhost:8080
PUBSUB_EMULATOR_HOST=localhost:8085

# Gemini API Key (每日報告功能)
GEMINI_API_KEY=your-gemini-api-key
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

### 測試每日報告

手動觸發每日報告生成（無需等待定時任務）：

```bash
# 在 price-analyzer 目錄下執行
cd apps/price-analyzer
uv run python test_daily_report.py

# 指定特定日期
uv run python test_daily_report.py --date 2026-07-04

# 只生成報告，不儲存到 Firestore
uv run python test_daily_report.py --skip-save
```

**注意事項：**
- 測試時請確認已設定 `GEMINI_API_KEY` 環境變數
- 如果指定的日期是週末，會自動使用最近的交易日
- 使用 `--skip-save` 可以測試 Gemini API 回應而不寫入資料庫

## 每日報告

### 排程規則
- **執行時間**：每天 08:00
- **執行條件**：僅在交易日執行（週一至週五）
- **假日處理**：自動跳過週末和假日

### 分析內容
Gemini 會分析以下項目：
1. 台指期、加權指數、那斯達克指數、費城半導體指數
2. 台積電、TSM (美股)

### 報告格式
儲存在 `daily_reports/{YYYYMMDD}`：

```json
{
  "date": "2026-07-07",
  "previous_date": "2026-07-06",
  "raw_content": "...",  // Markdown 格式的分析內容
  "summary": {},
  "model_used": "gemini-3.5-flash",
  "created_at": "2026-07-07T08:00:00Z"
}
```

**注意**：`raw_content` 欄位為 Markdown 格式，前端會使用 Markdown 渲染器顯示格式化內容。

### 取得 Gemini API Key

1. 前往 [Google AI Studio](https://aistudio.google.com/app/apikey)
2. 建立新的 API Key
3. 設定環境變數：`GEMINI_API_KEY=your-api-key`

## 注意事項

1. 如果未設定 `GEMINI_API_KEY`，服務仍會正常運行，但不會生成每日報告
2. 每日報告會在每天 08:00 自動執行，不需要手動觸發
3. 報告生成失敗不會影響即時價格分析功能
