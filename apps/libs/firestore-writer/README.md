# Firestore Writer 模組

提供 GCP Firestore 的寫入功能，支援 Emulator 和正式環境。

## 功能

- **FirestoreWriter**: Firestore 資料寫入
  - 單筆文件寫入
  - 批次寫入
  - 文件更新
  - 自動時間戳記（created_at, updated_at）

## 使用方式

```python
from firestore_writer import FirestoreWriter

# 初始化
writer = FirestoreWriter(project_id="my-project")

# 寫入文件
doc_id = writer.write_document(
    collection="prices",
    data={"symbol": "AAPL", "price": 150.5}
)

# 批次寫入
doc_ids = writer.batch_write(
    collection="prices",
    documents=[
        {"symbol": "AAPL", "price": 150.5},
        {"symbol": "GOOGL", "price": 2800.0},
    ]
)

# 更新文件
writer.update_document(
    collection="prices",
    document_id=doc_id,
    data={"price": 151.0}
)

# 關閉連線
writer.close()
```

## 環境變數

### Emulator 模式

```bash
FIRESTORE_EMULATOR_HOST=localhost:8080
```

設定此環境變數後，會自動連接到本地 Emulator。

## 自動時間戳記

所有寫入的文件會自動添加：
- `created_at`: 文件建立時間（僅在首次建立時）
- `updated_at`: 文件更新時間（每次寫入都會更新）
