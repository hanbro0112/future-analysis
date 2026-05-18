"""
Price Analyzer 主程式
訂閱 Pub/Sub 訊息並寫入 Firestore
"""
from pubsub import PubSubSubscriber
from firestore_writer import FirestoreWriter
from price_analyzer import config


def main():
    """主程式"""
    try:
        # 初始化 Firestore Writer
        firestore_writer = FirestoreWriter(
            project_id=config['project_id']
        )
        
        # 初始化 Pub/Sub Subscriber
        subscriber = PubSubSubscriber(
            project_id=config['project_id'],
            subscription_id=config['subscription_id']
        )
        
        # 定義訊息處理函數
        def handle_message(data: dict):
            """處理接收到的訊息並寫入 Firestore"""
            print(f"📊 處理資料: {data}")
            
            try:
                # 寫入到 Firestore
                doc_id = firestore_writer.write_document(
                    collection=config['collection_name'],
                    data=data
                )
                print(f"💾 資料已儲存到 Firestore: {doc_id}\n")
                
            except Exception as e:
                print(f"❌ 處理資料時發生錯誤: {e}\n")
                raise
        
        # 開始訂閱（阻塞式運行）
        print("🚀 Price Analyzer 已啟動\n")
        subscriber.subscribe(callback=handle_message)
        
    except KeyboardInterrupt:
        print("\n\n👋 正在停止服務...")
    except Exception as e:
        print(f"\n❌ 發生錯誤: {e}")
        sys.exit(1)
    finally:
        # 清理資源
        if 'firestore_writer' in locals():
            firestore_writer.close()
        if 'subscriber' in locals():
            subscriber.close()
        print("✨ 服務已停止")


if __name__ == "__main__":
    main()
