# Pub/Sub 客戶端模組

提供 GCP Pub/Sub 的 Publisher 和 Subscriber 功能，支援 Emulator 和正式環境。

## 功能

- **PubSubPublisher**: 發布訊息到 Pub/Sub
  - 自動建立 Topic
  - 支援單筆和批次發布
  - Topic 快取機制
  
- **PubSubSubscriber**: 訂閱並處理訊息
  - 串流拉取訊息
  - 自動 JSON 解析
  - 暫時性錯誤（`ServiceUnavailable`、`DeadlineExceeded` 等）自動重建串流重試；權限不足、訂閱不存在等永久性錯誤直接拋出
  - `max_retries` 計算「連續失敗」次數，串流穩定運作 60 秒以上才失敗會重新計算；用盡後拋出例外交給上層重啟
  - `close()` 可重複呼叫，會讓阻塞中的 `subscribe()` 乾淨地返回（不拋例外）

## 使用方式

### Publisher

```python
from pubsub import PubSubPublisher

# 初始化
publisher = PubSubPublisher(project_id="my-project")

# 發布訊息
message_id = publisher.publish_message(
    topic_id="my-topic",
    data={"price": 100.5, "symbol": "AAPL"},
    source="price-service"
)
```

### Subscriber

```python
from pubsub import PubSubSubscriber

def handle_message(data: dict):
    print(f"收到訊息: {data}")

# 初始化
subscriber = PubSubSubscriber(
    project_id="my-project",
    subscription_id="my-subscription"
)

# 開始監聽
subscriber.subscribe(callback=handle_message)
```

## 環境變數

### Emulator 模式

```bash
PUBSUB_EMULATOR_HOST=localhost:8085
```

設定此環境變數後，會自動連接到本地 Emulator。
