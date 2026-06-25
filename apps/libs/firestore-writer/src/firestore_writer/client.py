"""
Firestore 客戶端模組
提供寫入資料到 Firestore 的功能，支援 Emulator 和正式環境
"""
import os
import time
from typing import Optional, Dict, Any
from google.cloud import firestore
from google.api_core import retry, exceptions


def is_emulator_mode() -> bool:
    """
    檢查是否在 emulator 模式下運行
    
    Returns:
        True 如果在 emulator 模式，否則 False
    """
    return bool(os.getenv("FIRESTORE_EMULATOR_HOST"))


class FirestoreWriter:
    """Firestore 寫入輔助類別"""
    
    def __init__(self, project_id: str, max_retries: int = 3, retry_delay: float = 1.0):
        """
        初始化 Firestore 客戶端
        
        Args:
            project_id: GCP 專案 ID
            max_retries: 最大重試次數
            retry_delay: 重試延遲時間（秒）
        """
        self.project_id = project_id
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        if is_emulator_mode():
            print(f"🔧 使用 Firestore Emulator: {os.getenv('FIRESTORE_EMULATOR_HOST')}")
            self.db = firestore.Client(project=project_id)
        else:
            print(f"☁️  連接到正式 Firestore 環境")
            self.db = firestore.Client(project=project_id)
    
    def _retry_operation(self, operation, operation_name: str):
        """
        使用指數退避策略重試操作
        
        Args:
            operation: 要執行的操作（函數）
            operation_name: 操作名稱（用於日誌）
            
        Returns:
            操作的返回值
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return operation()
            except (exceptions.ServiceUnavailable, 
                    exceptions.DeadlineExceeded,
                    exceptions.InternalServerError,
                    exceptions.ResourceExhausted) as e:
                last_exception = e
                
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** attempt)  # 指數退避
                    print(f"⚠️  {operation_name} 失敗，{delay:.1f} 秒後重試... (第 {attempt + 1}/{self.max_retries} 次)")
                    time.sleep(delay)
                else:
                    print(f"❌ {operation_name} 達到最大重試次數")
            except Exception as e:
                # 不可重試的錯誤直接拋出
                print(f"❌ {operation_name} 發生不可重試的錯誤: {type(e).__name__}")
                raise
        
        # 所有重試都失敗
        raise last_exception
    
    def write_document(
        self,
        collection: str,
        document_id: Optional[str] = None,
        data: Dict[str, Any] = None,
        merge: bool = False
    ) -> str:
        """
        寫入文件到 Firestore（含重試機制）
        
        Args:
            collection: 集合名稱
            document_id: 文件 ID（可選，不提供則自動生成）
            data: 要寫入的資料
            merge: 是否合併現有文件（True）或覆蓋（False）
            
        Returns:
            文件 ID
        """
        if data is None:
            data = {}
        
        # 自動添加時間戳記
        if 'created_at' not in data:
            data['created_at'] = firestore.SERVER_TIMESTAMP
        data['updated_at'] = firestore.SERVER_TIMESTAMP
        
        def _write():
            if document_id:
                # 使用指定的文件 ID
                doc_ref = self.db.collection(collection).document(document_id)
                doc_ref.set(data, merge=merge)
                # print(f"✅ 文件已寫入: {collection}/{document_id}")
                return document_id
            else:
                # 自動生成文件 ID
                doc_ref = self.db.collection(collection).add(data)
                doc_id = doc_ref[1].id
                # print(f"✅ 文件已寫入: {collection}/{doc_id}")
                return doc_id
        
        try:
            return self._retry_operation(_write, f"寫入文件 {collection}/{document_id or 'auto'}")
        except Exception as e:
            print(f"❌ 寫入 Firestore 失敗: {e}")
            raise
    
    def batch_write(
        self,
        collection: str,
        documents: list[Dict[str, Any]],
        id_field: Optional[str] = None
    ) -> list[str]:
        """
        批次寫入多個文件（含重試機制）
        
        Args:
            collection: 集合名稱
            documents: 文件資料列表
            id_field: 用作文件 ID 的欄位名稱（可選）
            
        Returns:
            文件 ID 列表
        """
        def _batch_write():
            batch = self.db.batch()
            doc_ids = []
            
            for doc_data in documents:
                # 複製資料以避免修改原始資料
                data = doc_data.copy()
                
                # 自動添加時間戳記
                if 'created_at' not in data:
                    data['created_at'] = firestore.SERVER_TIMESTAMP
                data['updated_at'] = firestore.SERVER_TIMESTAMP
                
                # 決定文件 ID
                if id_field and id_field in data:
                    doc_id = str(data[id_field])
                    doc_ref = self.db.collection(collection).document(doc_id)
                else:
                    doc_ref = self.db.collection(collection).document()
                    doc_id = doc_ref.id
                
                batch.set(doc_ref, data)
                doc_ids.append(doc_id)
            
            # 提交批次操作
            batch.commit()
            print(f"✅ 批次寫入完成: {len(doc_ids)} 個文件寫入 {collection}")
            return doc_ids
        
        try:
            return self._retry_operation(_batch_write, f"批次寫入 {len(documents)} 個文件到 {collection}")
        except Exception as e:
            print(f"❌ 批次寫入 Firestore 失敗: {e}")
            raise
    
    def update_document(
        self,
        collection: str,
        document_id: str,
        data: Dict[str, Any]
    ) -> None:
        """
        更新現有文件（含重試機制）
        
        Args:
            collection: 集合名稱
            document_id: 文件 ID
            data: 要更新的資料
        """
        def _update():
            # 自動添加更新時間戳記
            update_data = data.copy()
            update_data['updated_at'] = firestore.SERVER_TIMESTAMP
            
            doc_ref = self.db.collection(collection).document(document_id)
            doc_ref.update(update_data)
            print(f"✅ 文件已更新: {collection}/{document_id}")
        
        try:
            self._retry_operation(_update, f"更新文件 {collection}/{document_id}")
        except Exception as e:
            print(f"❌ 更新 Firestore 失敗: {e}")
            raise
    
    def close(self) -> None:
        """關閉 Firestore 客戶端連線"""
        try:
            self.db.close()
            print("🔌 Firestore 連線已關閉")
        except Exception as e:
            print(f"⚠️  關閉 Firestore 連線時發生錯誤: {e}")
