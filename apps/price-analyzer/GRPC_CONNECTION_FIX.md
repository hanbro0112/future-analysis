# gRPC 連線錯誤修復說明

## 問題描述
服務運行時出現錯誤：`499 Received RST_STREAM with error code 8`

這是 gRPC 長連線被伺服器重置的常見問題，通常發生在：
- 長時間空閒導致連線超時
- 網路不穩定
- 服務器端流量控制

## 修復內容

### 1. Pub/Sub Subscriber 改進 (`libs/pubsub/src/pubsub/client.py`)

#### 新增功能：
- ✅ **自動重連機制**：當連線中斷時自動重試
- ✅ **Flow Control 配置**：避免資源耗盡
  - `max_messages=100`：同時處理的最大訊息數
  - `max_bytes=10MB`：最大記憶體使用量
- ✅ **智能錯誤偵測**：識別可重試的錯誤類型
  - `RST_STREAM`
  - `499` (Client Closed Request)
  - `503` (Service Unavailable)
  - `UNAVAILABLE`
  - `DEADLINE_EXCEEDED`
- ✅ **指數退避策略**：逐步增加重試間隔，避免過度請求

#### 新增參數：
```python
subscriber.subscribe(
    callback=handle_message,
    max_retries=0,      # 0 = 無限重試
    retry_delay=5       # 首次重試延遲 5 秒
)
```

### 2. Firestore Writer 改進 (`libs/firestore-writer/src/firestore_writer/client.py`)

#### 新增功能：
- ✅ **寫入操作重試**：所有寫入操作自動重試（最多 3 次）
- ✅ **指數退避**：1s → 2s → 4s 的重試延遲
- ✅ **錯誤分類**：僅重試暫時性錯誤
  - `ServiceUnavailable`
  - `DeadlineExceeded`
  - `InternalServerError`
  - `ResourceExhausted`

#### 新增參數：
```python
firestore_writer = FirestoreWriter(
    project_id=config['gcp_project_id'],
    max_retries=3,      # 最多重試 3 次
    retry_delay=1.0     # 首次重試延遲 1 秒
)
```

### 3. Main 程式改進 (`price-analyzer/src/price_analyzer/__init__.py`)

#### 改進：
- ✅ **完整的異常處理**：捕獲並記錄詳細的錯誤堆疊
- ✅ **資源清理保護**：即使發生錯誤也能正確關閉連線
- ✅ **未完成資料處理**：服務停止前自動完成聚合中的分鐘資料

## 使用方式

### 正常運行
```bash
cd apps
uv run --package price-analyzer python -m price-analyzer.main
```

服務現在會：
1. 自動處理連線中斷並重連
2. 在每次重試前顯示重試訊息
3. 遇到不可重試的錯誤時才停止

### 預期日誌輸出

**正常運行：**
```
🎧 開始監聽訂閱: projects/xxx/subscriptions/xxx
📨 收到訊息 ID: 123456
✅ 訊息已確認: 123456
```

**遇到可重試錯誤：**
```
⚠️  訂閱發生錯誤: 499 Received RST_STREAM with error code 8
🔄 將在 5 秒後重試... (第 1 次)
🔌 已重新建立訂閱者連線
🎧 開始監聽訂閱: projects/xxx/subscriptions/xxx
```

**遇到不可重試錯誤：**
```
❌ 訂閱發生不可重試的錯誤: PermissionDenied
```

## 測試建議

1. **長時間運行測試**：讓服務運行數小時，觀察是否能自動恢復連線
2. **網路中斷測試**：暫時斷開網路後重連，確認服務能自動恢復
3. **高負載測試**：發送大量訊息，確認 Flow Control 正常運作

## 注意事項

- 無限重試模式 (`max_retries=0`) 適用於生產環境，確保服務持續運行
- 如需有限重試，可調整 `max_retries` 參數
- 每次重試會重新建立訂閱者客戶端，避免使用損壞的連線
- Firestore 的重試是針對單次寫入操作，不影響整體服務運行
