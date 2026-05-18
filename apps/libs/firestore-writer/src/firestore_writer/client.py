"""
Firestore 客戶端模組
提供寫入資料到 Firestore 的功能，支援 Emulator 和正式環境
"""
import os
from typing import Optional, Dict, Any
from google.cloud import firestore


def is_emulator_mode() -> bool:
    """
    檢查是否在 emulator 模式下運行
    
    Returns:
        True 如果在 emulator 模式，否則 False
    """
    return bool(os.getenv("FIRESTORE_EMULATOR_HOST"))


class FirestoreWriter:
    """Firestore 寫入輔助類別"""
    
    def __init__(self, project_id: str):
        """
        初始化 Firestore 客戶端
        
        Args:
            project_id: GCP 專案 ID
        """
        self.project_id = project_id
        
        if is_emulator_mode():
            print(f"🔧 使用 Firestore Emulator: {os.getenv('FIRESTORE_EMULATOR_HOST')}")
            self.db = firestore.Client(project=project_id)
        else:
            print(f"☁️  連接到正式 Firestore 環境")
            self.db = firestore.Client(project=project_id)
    
    def write_document(
        self,
        collection: str,
        document_id: Optional[str] = None,
        data: Dict[str, Any] = None,
        merge: bool = False
    ) -> str:
        """
        寫入文件到 Firestore
        
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
        
        try:
            if document_id:
                # 使用指定的文件 ID
                doc_ref = self.db.collection(collection).document(document_id)
                doc_ref.set(data, merge=merge)
                print(f"✅ 文件已寫入: {collection}/{document_id}")
                return document_id
            else:
                # 自動生成文件 ID
                doc_ref = self.db.collection(collection).add(data)
                doc_id = doc_ref[1].id
                print(f"✅ 文件已寫入: {collection}/{doc_id}")
                return doc_id
                
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
        批次寫入多個文件
        
        Args:
            collection: 集合名稱
            documents: 文件資料列表
            id_field: 用作文件 ID 的欄位名稱（可選）
            
        Returns:
            文件 ID 列表
        """
        batch = self.db.batch()
        doc_ids = []
        
        try:
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
        更新現有文件
        
        Args:
            collection: 集合名稱
            document_id: 文件 ID
            data: 要更新的資料
        """
        try:
            # 自動添加更新時間戳記
            data['updated_at'] = firestore.SERVER_TIMESTAMP
            
            doc_ref = self.db.collection(collection).document(document_id)
            doc_ref.update(data)
            print(f"✅ 文件已更新: {collection}/{document_id}")
            
        except Exception as e:
            print(f"❌ 更新 Firestore 失敗: {e}")
            raise
    
    def close(self) -> None:
        """關閉 Firestore 客戶端連線"""
        self.db.close()
        print("🔌 Firestore 連線已關閉")
