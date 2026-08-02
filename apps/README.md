# Apps Workspace

這是一個 uv workspace，包含三個常駐的 Cloud Run 服務、一組定時任務 Cloud Functions，以及供彼此共用的程式庫。

## 專案結構

```
apps/
├── pyproject.toml           # Workspace 配置
├── config.py                # 環境變數配置
├── libs/                    # 共享程式庫
│   ├── pubsub/             # Pub/Sub 客戶端模組
│   │   ├── pyproject.toml
│   │   ├── README.md
│   │   └── src/
│   │       └── pubsub/
│   │           ├── __init__.py
│   │           └── client.py
│   └── firestore-writer/   # Firestore 寫入模組
│       ├── pyproject.toml
│       ├── README.md
│       └── src/
│           └── firestore_writer/
│               ├── __init__.py
│               └── client.py
├── price-listener/          # 價格監聽服務（Cloud Run）
│   ├── main.py             # 啟動入口
│   ├── pyproject.toml      # Package 配置
│   └── src/
│       └── price_listener/
│           └── __init__.py
├── price-analyzer/          # 價格分析服務（Cloud Run）
│   ├── main.py             # 啟動入口
│   ├── pyproject.toml      # Package 配置
│   └── src/
│       └── price_analyzer/
│           ├── __init__.py
│           ├── minute_aggregator.py
│           └── strategy.py
├── price-broadcaster/       # 報價廣播服務（Cloud Run）
│   ├── main.py             # 啟動入口
│   ├── pyproject.toml      # Package 配置
│   ├── test_ws_client.py   # WebSocket 測試客戶端
│   └── src/
│       └── price_broadcaster/
│           ├── __init__.py
│           └── auth.py
└── functions/                # 定時任務（Cloud Functions 2nd gen）
    ├── main.py               # 進入點，匯出 daily_report / chip_report
    ├── daily_report.py       # 每日 AI 市場分析（Gemini）
    ├── chip_report.py        # 籌碼快訊圖表擷取
    └── pyproject.toml        # Package 配置
```

## 安裝依賴

在 `apps/` 目錄下執行：

```bash
cd apps
uv sync
```

這會安裝所有專案的依賴。

## 執行應用程式

### 執行 Price Listener（價格監聽服務）

```bash
# 在 apps 目錄下執行
uv run --package price-listener python -m price-listener.main
```

### 執行 Price Analyzer（價格分析服務）

```bash
# 在 apps 目錄下執行
uv run --package price-analyzer python -m price-analyzer.main
```

### 執行 Price Broadcaster（報價廣播服務）

```bash
# 在 apps 目錄下執行
uv run --package price-broadcaster python -m price-broadcaster.main
```

## 環境變數

所有專案共用根目錄的 `.env` 檔案（`future-analysis/.env`）或使用 `config.py` 配置。

### Price Listener 需要的環境變數

```bash
API_KEY=your_api_key
SECRET_KEY=your_secret_key
CA_CERT_PATH=path/to/cert.pfx
CA_PASSWORD=your_password

GCP_PROJECT_ID=demo-project
PUBSUB_TOPIC_ID=price-updates

# Emulator 配置（開發環境）
PUBSUB_EMULATOR_HOST=localhost:8085
```

### Price Analyzer 需要的環境變數

```bash
GCP_PROJECT_ID=demo-project
PUBSUB_SUBSCRIPTION_ID_ANALYZER=price-analyzer-subscription

# Emulator 配置（開發環境）
PUBSUB_EMULATOR_HOST=localhost:8085
FIRESTORE_EMULATOR_HOST=localhost:8080
```

### Price Broadcaster 需要的環境變數

```bash
GCP_PROJECT_ID=demo-project
PUBSUB_SUBSCRIPTION_ID_BROADCASTER=price-broadcaster-subscription

# Emulator 配置（開發環境）
PUBSUB_EMULATOR_HOST=localhost:8085
FIRESTORE_EMULATOR_HOST=localhost:8080
```

> Price Analyzer 與 Price Broadcaster 訂閱同一個 Pub/Sub topic，但必須使用不同的 subscription id
> （`PUBSUB_SUBSCRIPTION_ID_ANALYZER` / `PUBSUB_SUBSCRIPTION_ID_BROADCASTER`），
> 否則本機同時啟動兩個服務時會互相競爭消費、各自漏收一半的 tick。

## 開發

### 添加依賴

為特定專案添加依賴：

```bash
# 為 price-listener 添加依賴
cd price-listener
uv add package-name

# 為 price-analyzer 添加依賴
cd price-analyzer
uv add package-name

# 為 price-broadcaster 添加依賴
cd price-broadcaster
uv add package-name

# 為共享程式庫添加依賴
cd libs/pubsub
uv add package-name
```

### 共享程式庫

共享的程式庫放在 `libs/` 目錄：

- **libs/pubsub** - Pub/Sub Publisher 和 Subscriber
  - `PubSubPublisher`: 發布訊息到 Pub/Sub
  - `PubSubSubscriber`: 訂閱並處理訊息
  - 依賴：`google-cloud-pubsub>=2.38.0`

- **libs/firestore-writer** - Firestore Writer
  - `FirestoreWriter`: 寫入資料到 Firestore
  - 依賴：`google-cloud-firestore>=2.20.0`

所有專案都會自動將 workspace sources 加入 Python path。

## 服務說明

### Price Listener（價格監聽服務）
- 從外部 API 接收即時 tick 資料
- 發布資料到 Pub/Sub topic
- 詳見：[price-listener/README.md](price-listener/README.md)

### Price Analyzer（價格分析服務）
- 訂閱 Pub/Sub 的 tick 資料
- 分析價格並計算指標（如多空比）
- 計算每分鐘 OHLCV 統計，並將分析結果儲存到 Firestore
- 每秒取樣重建秒級報價明細（前向填充、跨分鐘/跨日連續性），儲存到 Firestore
- 詳見：[price-analyzer/README.md](price-analyzer/src/price_analyzer/STRATEGY_README.md)

### Price Broadcaster（報價廣播服務）
- 訂閱 Pub/Sub 的 tick 資料
- 透過 WebSocket 即時廣播最新報價（每秒一次）
- 詳見：[price-broadcaster/README.md](price-broadcaster/README.md)

### Functions（定時任務）
- `daily_report`：每日以 Gemini API 分析台股/美股，寫入 Firestore `daily_reports/{YYYYMMDD}`
- `chip_report`：每交易日抓取台指籌碼快訊 PDF，裁切圖表上傳 Cloud Storage
- 由 Cloud Scheduler 觸發 Cloud Functions (2nd gen)，非常駐服務
- 詳見：[functions/README.md](functions/README.md)
