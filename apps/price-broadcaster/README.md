# Price Broadcaster - 報價廣播服務

FastAPI WebSocket 即時報價伺服器，提供每秒一次的報價廣播。

> 分鐘級報價統計（秒級明細前向填充、寫入 Firestore）已移至 [price-analyzer](../price-analyzer/README.md)，
> 本服務只保留即時報價廣播職責。

## 功能

1. **即時報價廣播**：透過 WebSocket 每秒發送最新報價
2. **完整報價資訊**：包含成交價、加權指數、每秒總成交量
3. **Pub/Sub 訂閱**：從 Pub/Sub（`price-broadcaster-subscription`）接收 tick 資料
4. **價格聚合**：同一秒內多筆成交取最新價格
5. **成交量累計**：自動累計每秒所有 tick 的成交量
6. **WebSocket 連接管理**：自動清理斷開連接

## 資料格式

### WebSocket 訊息
```json
{
  "type": "price",
  "data": {
    "MXFF6": {
      "price": 23450.0,
      "underlying_price": 23644.4,
      "volume": 125
    }
  },
  "timestamp": "2026-07-03T09:00:01.123456"
}
```

欄位說明：
- `price`: 最新成交價
- `underlying_price`: 加權指數（現貨標的指數當前價格）
- `volume`: 該秒總成交量（累計該秒內所有 tick 的成交量）

> 秒級明細前向填充、跨分鐘/跨日處理、寫入 Firestore（`market/{商品代碼}/{YYYYMMDD}_tick/{HHMM}`）
> 的完整說明請見 [price-analyzer README](../price-analyzer/README.md)。

## 執行

```bash
# 在 apps 目錄下執行
cd apps

# 安裝依賴
uv sync

# 啟動服務（預設埠 8080；前端本地預設連 8001，所以本地開發請指定 PORT=8001）
PORT=8001 uv run --package price-broadcaster python -m price-broadcaster.main
```

## 部署

### GCE（目前使用）

由 [.github/workflows/deploy-apps-gce.yml](../../.github/workflows/deploy-apps-gce.yml) 建置 image 並推送到 Artifact Registry，再透過 IAP SSH 在 VM 上以 Docker Compose 重啟，設定見 [infra/gce/README.md](../../infra/gce/README.md)。

```
瀏覽器 ──wss──▶ Cloudflare Proxy (ws.txfutures.com)
                     │ 443（Origin CA，SSL Full strict）
                     ▼
              caddy ──▶ price-broadcaster:8080（compose 內部網路，不對外開放）
```

- 容器只 `expose: 8080`，對外只有 Caddy 的 443；Caddy 憑證為 Cloudflare Origin CA，不是 Let's Encrypt
- 前端建置時以 `NEXT_PUBLIC_WS_URL=wss://ws.txfutures.com` 指向此端點（`/ws/price` 路徑由前端補上）
- `/health` 經 Cloudflare 可用 `curl https://ws.txfutures.com/health` 驗證
- 重啟期間 tick 會留在 Pub/Sub 重啟後補送，但已連線的 WebSocket 客戶端會被中斷，前端會自動重連

### Cloud Run（舊版，歷史參考）

由 [.github/workflows/deploy-apps.yml](../../.github/workflows/deploy-apps.yml) 部署（`--allow-unauthenticated`，瀏覽器直連 Cloud Run 網址）。

## API 端點

- `GET /`：服務狀態（埠號取環境變數 `PORT`，預設 8080）
- `GET /health`：健康檢查（包含連接數和最新報價）
- `WS /ws/price`：WebSocket 報價訂閱

## WebSocket 客戶端範例

### JavaScript
```javascript
const ws = new WebSocket('ws://localhost:8001/ws/price');

ws.onopen = () => {
  console.log('WebSocket 已連接');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('收到報價:', data);
  // data.data 包含 {商品代碼: {price, underlying_price, volume}} 的對應
  // 例如: data.data.MXFF6.price = 23450.0
  // 例如: data.data.MXFF6.underlying_price = 23644.4
  // 例如: data.data.MXFF6.volume = 125
};

ws.onerror = (error) => {
  console.error('WebSocket 錯誤:', error);
};

ws.onclose = () => {
  console.log('WebSocket 已斷開');
};

// 發送心跳包維持連接
setInterval(() => {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send('ping');
  }
}, 30000);
```

### Python 測試客戶端
```bash
# 執行測試客戶端（接收 10 筆訊息）
uv run python test_ws_client.py
```

## 配置

在 `apps/config.py` 中配置 GCP 專案和 Pub/Sub 資訊：

```python
config = {
    'gcp_project_id': 'demo-project',
    'pubsub_topic_id': 'price-updates',
    'pubsub_subscription_id_broadcaster': 'price-broadcaster-subscription'
}
```

> 這裡的 subscription 必須跟 price-analyzer 的分開（`pubsub_subscription_id_analyzer`），
> 兩個服務訂閱同一個 topic，但共用同一個 subscription 會導致訊息被瓜分而非各自收到全部。

## 架構

```
price-broadcaster/
├── main.py                    # 入口檔案
├── pyproject.toml             # 專案配置
├── README.md                  # 說明文件
├── test_ws_client.py          # WebSocket 測試客戶端
├── test_auth.py               # Firebase ID Token 驗證測試
├── test_session_lifecycle.py  # 時段生命週期測試
└── src/
    └── price_broadcaster/
        ├── __init__.py        # FastAPI 應用和 WebSocket 邏輯
        └── auth.py            # Firebase ID Token 驗證
```

## 元件說明

| 檔案 | 功用 |
| --- | --- |
| `main.py` | 服務啟動入口，啟動 FastAPI/uvicorn |
| `src/price_broadcaster/__init__.py` | FastAPI 應用主體：Pub/Sub 訂閱、每秒價格聚合與 WebSocket 廣播、`/health` 健康檢查 |
| `src/price_broadcaster/auth.py` | 驗證前端 WebSocket 連線帶上的 Firebase ID Token（`firebase_admin.auth`），拒絕未登入連線 |
| `src/price_broadcaster/__init__.py` 中的 `supervise_sessions()` | 時段監控：待機時每分鐘、時段進行中每秒判斷是否在啟用窗口（開盤前 5 分鐘到收盤，排除週末與國定假日，由 [libs/trading-calendar](../libs/trading-calendar/README.md) 提供），窗口內啟動廣播與 Pub/Sub 訂閱，收盤時中斷所有連線並清空報價快取 |
| `src/price_broadcaster/__init__.py` 中的 `is_session_open()` 檢查 | WebSocket 連線時以台北時間判斷是否為交易時段，非交易時段拒絕連線（關閉代碼 `4403`） |
| `test_ws_client.py` | 本地測試用 WebSocket 客戶端，接收並印出報價訊息 |

## 特性

- ✅ 每秒廣播最新報價給所有 WebSocket 客戶端
- ✅ 提供成交價、加權指數、每秒總成交量資訊
- ✅ 自動累計每秒所有 tick 的成交量
- ✅ 同一秒內多筆成交取最新價格
- ✅ WebSocket 連接管理（自動清理斷開連接）
- ✅ 非交易時段拒絕 WebSocket 連線（關閉代碼 `4403`）
- ✅ 收盤時主動以 `4403` 中斷所有已連線的客戶端，並清空最新報價，不會在收盤後繼續推送過期價格
- ✅ Pub/Sub 訂閱在時段進行中失敗（重試用盡或不可重試的錯誤）時，會中斷連線（`1012`）並於下一分鐘重新訂閱，不會靜默停擺
- ✅ 每個時段使用全新的 Pub/Sub 訂閱連線
- ✅ CORS 支援（允許所有來源）
- ✅ 健康檢查端點
- ✅ 正確的服務關閉機制（清理所有背景任務）

## 注意事項

1. **報價資訊**：每筆報價包含成交價、加權指數、每秒總成交量
2. **成交量計算**：每秒自動累計所有 tick 的 volume，下一秒重置
3. **資料來源**：必須先啟動 `price-listener` 服務發送 tick 資料到 Pub/Sub
4. **WebSocket 心跳**：客戶端應定期發送訊息以維持連接
5. **交易時段限制**：非交易時段（日盤 8:45-13:45、夜盤 15:00-次日 5:00，週末與國定假日休市）連線會被拒絕，關閉代碼為 `4403`；已連線的客戶端也會在收盤時被以 `4403` 中斷
6. **健康檢查**：`/health` 的 `session_running` 為 `false` 代表目前不在啟用窗口（待機中）或正在等待重啟訂閱
