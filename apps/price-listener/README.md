# Price Listener - 價格監聽服務

透過永豐證券 Shioaji API 監聽台指期（`MXFR1`）逐筆報價（tick），發布到 Pub/Sub 供下游服務消費。常駐運行（Cloud Run 或 GCE），自己依交易日曆決定何時登入、何時收尾。

## 功能

- 每分鐘判斷是否在啟用窗口（開盤前 5 分鐘到收盤後 1 分鐘，排除週末與國定假日），進入窗口才登入 Shioaji，收盤後登出並釋放連線，回到待機等下一個時段；每個時段都是全新連線
- 登入 Shioaji API 並訂閱期貨合約逐筆報價
- 過濾試撮（`simtrade`）資料，僅發布正式成交的 tick
- 將 tick 展開為 Pub/Sub 訊息（`topic: price-updates`）發布
- 斷線自動重連：偵測 Session down 事件，啟用窗口內以指數退避重試，最多 5 次；重連或收尾期間舊連線觸發的斷線事件會被忽略
- 定期（每 60 秒）背景檢查連線與訂閱狀態，啟用窗口內斷線會自動觸發重連
- 合約訂閱失敗自動重試：`subscribe_contracts` 內建重試（處理冷啟動時合約清單尚未下載完成），若仍失敗，啟用窗口內背景檢查會持續重新訂閱，不需整個重新登入
- 登入或初始化失敗不會結束 process，下一分鐘自動重試；登入後憑證啟用失敗會先登出，避免佔用連線數
- 內建極簡 HTTP health check server（`GET /` 回 200），供 Cloud Run 判斷服務存活
- 收到 `SIGTERM`（Cloud Run / Docker 關閉服務）或 `Ctrl+C` 時結束目前時段：登出並印出 API 用量報告後離開

## 元件說明

| 檔案 | 功用 |
| --- | --- |
| `main.py` | 服務啟動入口，呼叫 `price_listener.main()` |
| `src/price_listener/__init__.py` | 核心邏輯：Shioaji 登入/訂閱、tick 回調發布 Pub/Sub、斷線重連、時段生命週期、health check server |

交易日曆與每分鐘判斷的時段迴圈由共用的 [libs/trading-calendar](../libs/trading-calendar/README.md) 提供。

### 主要函式

- `run_listener_session(should_continue)`：執行一個時段（連線、訂閱、監看連線狀態，窗口結束時收尾）
- `get_shioaji_client()`：登入 Shioaji API 並啟用 CA 憑證
- `quote_callback(tick)`：tick 回調，轉換欄位並發布到 Pub/Sub
- `subscribe_contracts(api)`：訂閱合約，查詢合約清單失敗時會重試，回傳是否全部訂閱成功
- `on_session_down` / `reconnect` / `check_and_reconnect`：斷線偵測與自動重連、合約訂閱失敗重試
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
