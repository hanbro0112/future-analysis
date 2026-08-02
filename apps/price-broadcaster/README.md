# Price Broadcaster - 報價廣播服務

FastAPI WebSocket 即時報價伺服器，提供每秒一次的報價廣播。

> 分鐘級報價統計（秒級明細前向填充、寫入 Firestore）已移至 [price-analyzer](../price-analyzer/README.md)，
> 本服務只保留即時報價廣播職責。

## 功能

1. **即時報價廣播**：透過 WebSocket 每秒發送最新報價
2. **完整報價資訊**：包含成交價、加權指數、每秒總成交量
3. **Pub/Sub 訂閱**：從 Firestore Pub/Sub 接收 tick 資料
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

# 啟動服務
uv run --package price-broadcaster python -m price_broadcaster.main
```

## API 端點

- `GET /`：服務狀態
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
| `test_ws_client.py` | 本地測試用 WebSocket 客戶端，接收並印出報價訊息 |

## 特性

- ✅ 每秒廣播最新報價給所有 WebSocket 客戶端
- ✅ 提供成交價、加權指數、每秒總成交量資訊
- ✅ 自動累計每秒所有 tick 的成交量
- ✅ 同一秒內多筆成交取最新價格
- ✅ WebSocket 連接管理（自動清理斷開連接）
- ✅ CORS 支援（允許所有來源）
- ✅ 健康檢查端點
- ✅ 正確的服務關閉機制（清理所有背景任務）

## 注意事項

1. **報價資訊**：每筆報價包含成交價、加權指數、每秒總成交量
2. **成交量計算**：每秒自動累計所有 tick 的 volume，下一秒重置
3. **資料來源**：必須先啟動 `price-listener` 服務發送 tick 資料到 Pub/Sub
4. **WebSocket 心跳**：客戶端應定期發送訊息以維持連接
