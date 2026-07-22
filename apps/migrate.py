"""
Firestore Migration Script

cd apps
uv run python migrate.py

"""
import sys
from pathlib import Path

# 添加 apps 目錄到 Python 路徑
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import config
from firestore_writer import FirestoreWriter


def migrate_date(symbol: str, from_date: str, to_date: str, delete_source: bool = False):
    """
    遷移 Firestore 資料從一個日期到另一個日期
    
    Args:
        symbol: 商品代碼（例如：MXF）
        from_date: 來源日期（例如：20260630）
        to_date: 目標日期（例如：20260629）
        delete_source: 是否刪除來源資料
    """
    # 初始化 Firestore（使用 FirestoreWriter 來獲取 client）
    writer = FirestoreWriter(project_id=config['gcp_project_id'])
    db = writer.db
    
    # 來源和目標路徑
    source_path = f"market/{symbol}/{from_date}"
    target_path = f"market/{symbol}/{to_date}"
    
    print(f"🔄 開始遷移資料...")
    print(f"   來源: {source_path}")
    print(f"   目標: {target_path}")
    print(f"   刪除來源: {'是' if delete_source else '否'}")
    print()
    
    # 讀取來源資料
    source_ref = db.collection(source_path)
    docs = source_ref.stream()
    
    migrated_count = 0
    deleted_count = 0
    error_count = 0
    
    for doc in docs:
        try:
            doc_id = doc.id
            doc_data = doc.to_dict()
            
            # 更新 date 欄位
            if 'date' in doc_data:
                # 將 YYYY-MM-DD 格式轉換
                target_date_formatted = f"{to_date[:4]}-{to_date[4:6]}-{to_date[6:]}"
                doc_data['date'] = target_date_formatted
            
            # 寫入目標位置
            target_ref = db.collection(target_path).document(doc_id)
            target_ref.set(doc_data)
            
            migrated_count += 1
            print(f"✅ 已遷移: {doc_id} (O:{doc_data.get('open')} C:{doc_data.get('close')} V:{doc_data.get('volume')})")
            
            # 如果需要，刪除來源資料
            if delete_source:
                doc.reference.delete()
                deleted_count += 1
                print(f"🗑️  已刪除: {doc_id}")
        
        except Exception as e:
            error_count += 1
            print(f"❌ 處理文件 {doc_id} 時發生錯誤: {e}")
    
    print()
    print("=" * 60)
    print(f"📊 遷移完成統計:")
    print(f"   成功遷移: {migrated_count} 筆")
    if delete_source:
        print(f"   已刪除: {deleted_count} 筆")
    print(f"   錯誤: {error_count} 筆")
    print("=" * 60)


"""
將 MXF 20260630 的資料移到 20260629
"""
def mxf_0630_to_0629():
    """
    遷移任務：MXF 20260630 → 20260629
    將夜盤跨日資料移回正確的日期
    """
    symbol = "MXF"
    from_date = "20260630"
    to_date = "20260629"
    delete_source = False  # 設為 True 會刪除來源資料
    
    # 確認遷移
    print(f"⚠️  即將遷移資料:")
    print(f"   商品: {symbol}")
    print(f"   {from_date} → {to_date}")
    print()
    
    response = input("確認執行遷移？(y/n): ")
    if response.lower() != 'y':
        print("❌ 已取消遷移")
        return
    
    print()
    migrate_date(symbol, from_date, to_date, delete_source)


def main():
    """主程式"""
    print("=" * 60)
    print("Firestore 資料遷移工具")
    print("=" * 60)
    print()
    
    # 執行遷移任務
    mxf_0630_to_0629()


if __name__ == "__main__":
    main()
