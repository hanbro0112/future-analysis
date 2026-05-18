# Apps Workspace

這是一個 uv workspace，包含兩個獨立的應用程式。

## 專案結構

```
apps/
├── pyproject.toml           # Workspace 配置
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
├── price-analyzer/          # 價格分析服務
│   ├── main.py             # 啟動入口
│   ├── pyproject.toml      # Package 配置
│   └── src/
│       └── price_analyzer/
│           ├── __init__.py
│           └── config.py
└── price-listener/          # 價格監聽服務
    ├── main.py             # 啟動入口
    ├── pyproject.toml      # Package 配置
    └── src/
        └── price_listener/
            ├── __init__.py
            └── config.py
```

## 安裝依賴

在 `apps/` 目錄下執行：

```bash
cd apps
uv sync
```

這會安裝兩個專案的所有依賴。

## 執行應用程式

### 執行 Price Analyzer

```bash
# 方式 1：使用 uv run（推薦）
cd apps/price-analyzer
uv run price-analyzer

# 方式 2：直接執行 main.py
uv run python main.py
```

### 執行 Price Listener

```bash
# 方式 1：使用 uv run（推薦）
cd apps/price-listener
uv run price-listener

# 方式 2：直接執行 main.py
uv run python main.py
```

## 環境變數

兩個專案共用根目錄的 `.env` 檔案（`future-analysis/.env`）。

### Price Analyzer 需要的環境變數：

```bash
GCP_PROJECT_ID=demo-project
PUBSUB_SUBSCRIPTION_ID=price-subscription
FIRESTORE_COLLECTION=prices

# Emulator 配置（開發環境）
PUBSUB_EMULATOR_HOST=localhost:8085
FIRESTORE_EMULATOR_HOST=localhost:8080
```

### Price Listener 需要的環境變數：

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

## 開發

### 共享程式庫

共享的程式庫放在 `libs/` 目錄：

- **libs/pubsub** - Pub/Sub Publisher 和 Subscriber
  - `PubSubPublisher`: 發布訊息到 Pub/Sub
  - `PubSubSubscriber`: 訂閱並處理訊息
  - 依賴：`google-cloud-pubsub>=2.38.0`

- **libs/firestore-writer** - Firestore Writer

# 為共享程式庫添加依賴
cd libs/pubsub
uv add package-name
```
cd price-analyzer
uv add package-name

# 為 price-listener 添加依賴
cd price-listener
uv add package-name
```

### 共享程式庫

共享的程式庫放在 `libs/` 目錄：
- `libs/pubsub.py` - Pub/Sub Publisher 和 Subscriber
- `libs/firestore.py` - Firestore Writer

兩個專案都會自動將 `libs/` 加入 Python path。
