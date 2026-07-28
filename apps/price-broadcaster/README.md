# Price Broadcaster - 報價廣播服務

FastAPI WebSocket 即時報價伺服器，提供每秒一次的報價廣播，並儲存完整的每秒報價資料。

## 功能

1. **即時報價廣播**：透過 WebSocket 每秒發送最新報價
2. **完整報價資訊**：包含成交價、加權指數、每秒總成交量
3. **Pub/Sub 訂閱**：從 Firestore Pub/Sub 接收 tick 資料
4. **價格聚合**：同一秒內多筆成交取最新價格
5. **成交量累計**：自動累計每秒所有 tick 的成交量
6. **自動填充**：缺失的秒數自動使用前一秒價格填充，確保每分鐘完整 60 筆
7. **跨分鐘連續**：第 0 秒缺失時使用上一分鐘最後價格
8. **夜盤跨日處理**：夜盤 00:00-05:59 的資料儲存到前一天
9. **歷史儲存**：每分鐘將 60 筆報價儲存到 Firestore

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

### Firestore 儲存
- **路徑**：`market/{商品代碼}/{YYYYMMDD_tick}/{HHMM}`
- **格式**：`{秒數: {price, underlying_price, volume}}`（固定 60 筆，00-59）
- **填充規則**：缺失的秒數只填充 `price` 欄位

範例：
```
market/MXF/20260703_tick/0900
{
  "00": {
    "price": 23450.0,
    "underlying_price": 23644.4,
    "volume": 125
  },
  "01": {
    "price": 23451.0,
    "underlying_price": 23645.1,
    "volume": 89
  },
  "02": {
    "price": 23451.0  // 缺失資料，只填充 price
  },
  ...
  "59": {
    "price": 23455.0,
    "underlying_price": 23648.2,
    "volume": 156
  },
  "created_at": <timestamp>,
  "updated_at": <timestamp>
}
```

每個秒數包含：
- `price`: 該秒的成交價（**必有**，缺失時自動填充）
- `underlying_price`: 該秒的加權指數（有實際資料時才有）
- `volume`: 該秒的總成交量（有實際資料時才有）

## 自動填充機制

### 前向填充 (Forward Fill)
缺失的秒數會自動使用最近一次的價格填充（**僅填充 price**，不包含 underlying_price 和 volume）：

```
實際資料: 
  45 秒 = {price: 23450, underlying_price: 23644.4, volume: 125}
  46 秒缺失
  47 秒 = {price: 23452, underlying_price: 23645.2, volume: 98}

填充結果: 
  46 秒 = {price: 23450}  // 只填充 price
```

### 跨分鐘填充
如果某分鐘的第 0 秒缺失，會使用上一分鐘的最後價格（59 秒）：

```
上一分鐘 03:21:59 = {price: 23450, underlying_price: 23644.4, volume: 125}
本分鐘 03:22:00 缺失 → 填充為 {price: 23450}
```

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
    'pubsub_subscription_id': 'price-subscription'
}
```

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
| `src/price_broadcaster/__init__.py` | FastAPI 應用主體：Pub/Sub 訂閱、每秒價格聚合與 WebSocket 廣播、缺秒前向填充、跨分鐘/跨日處理、每分鐘寫入 Firestore、`/health` 健康檢查 |
| `src/price_broadcaster/auth.py` | 驗證前端 WebSocket 連線帶上的 Firebase ID Token（`firebase_admin.auth`），拒絕未登入連線 |
| `test_ws_client.py` | 本地測試用 WebSocket 客戶端，接收並印出報價訊息 |

## 時間處理

### 交易時段
- **日盤**：08:45 - 13:45
- **夜盤**：15:00 - 05:00（次日）

### 跨日處理
夜盤 00:00-05:59 的資料會儲存到前一天：

```
實際時間: 2026-07-03 01:30
儲存路徑: market/MXF/20260702_tick/0130
```

## 特性

- ✅ 每秒廣播最新報價給所有 WebSocket 客戶端
- ✅ 提供成交價、加權指數、每秒總成交量資訊
- ✅ 自動累計每秒所有 tick 的成交量
- ✅ 同一秒內多筆成交取最新價格
- ✅ WebSocket 連接管理（自動清理斷開連接）
- ✅ 每分鐘自動儲存完整 60 筆報價
- ✅ 前向填充缺失秒數（Forward Fill）
- ✅ 跨分鐘連續性保證
- ✅ 夜盤跨日處理
- ✅ CORS 支援（允許所有來源）
- ✅ 健康檢查端點
- ✅ 正確的服務關閉機制（清理所有背景任務）

## 注意事項

1. **報價資訊**：每筆報價包含成交價、加權指數、每秒總成交量
2. **成交量計算**：每秒自動累計所有 tick 的 volume，下一秒重置
3. **儲存格式**：Firestore 中每個秒數儲存完整的報價物件（有實際資料時）
4. **填充機制**：缺失秒數**只填充 price 欄位**，不包含 underlying_price 和 volume
5. **報價連續性**：服務會確保每分鐘都有完整的 60 筆報價（透過填充機制）
6. **資料來源**：必須先啟動 `price-listener` 服務發送 tick 資料到 Pub/Sub
7. **Firestore Emulator**：開發環境使用 Emulator，需設定 `FIRESTORE_EMULATOR_HOST`
8. **WebSocket 心跳**：客戶端應定期發送訊息以維持連接
