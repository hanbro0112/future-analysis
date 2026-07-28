# Price Listener - 價格監聽服務

透過永豐證券 Shioaji API 監聽台指期（`MXFR1`）逐筆報價（tick），發布到 Pub/Sub 供下游服務消費。常駐於 Cloud Run，`min-instances` 由 Cloud Scheduler 依日盤/夜盤時段調整。

## 功能

- 登入 Shioaji API 並訂閱期貨合約逐筆報價
- 過濾試撮（`simtrade`）資料，僅發布正式成交的 tick
- 將 tick 展開為 Pub/Sub 訊息（`topic: price-updates`）發布
- 斷線自動重連：偵測 Session down 事件，交易時段內以指數退避重試，最多 5 次
- 定期（每 60 秒）背景檢查連線狀態，交易時段內斷線會自動觸發重連
- 內建極簡 HTTP health check server（`GET /` 回 200），供 Cloud Run 判斷服務存活
- 收到 `SIGTERM`（Cloud Run 關閉 instance）或 `Ctrl+C` 時安全登出並印出 API 用量報告

## 元件說明

| 檔案 | 功用 |
| --- | --- |
| `main.py` | 服務啟動入口，呼叫 `price_listener.main()` |
| `src/price_listener/__init__.py` | 核心邏輯：Shioaji 登入/訂閱、tick 回調發布 Pub/Sub、斷線重連、交易時段判斷、health check server |

### 主要函式

- `get_shioaji_client()`：登入 Shioaji API 並啟用 CA 憑證
- `quote_callback(tick)`：tick 回調，轉換欄位並發布到 Pub/Sub
- `is_trading_hours(check_time)`：判斷是否為日盤（08:45–13:45）或夜盤（15:00–次日 05:00）
- `on_session_down` / `reconnect` / `check_and_reconnect`：斷線偵測與自動重連
- `check_usage(api)`：登出前印出 Shioaji API 流量使用量

## 環境變數

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

## 執行

```bash
# 在 apps 目錄下執行
cd apps
uv sync
uv run --package price-listener python -m price-listener.main
```

## 部署

由 [.github/workflows/deploy-apps.yml](../../.github/workflows/deploy-apps.yml) 建置並部署到 Cloud Run（`--ingress=internal`，需搭配 Secret Manager 掛載 API 金鑰與 CA 憑證）。
