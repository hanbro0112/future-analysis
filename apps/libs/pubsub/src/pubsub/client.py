"""
Pub/Sub 客戶端模組
提供連接 Pub/Sub Emulator 或正式環境的功能
"""
import os
import json
import time
from typing import Callable, Optional
from google.cloud import pubsub_v1
from google.cloud.pubsub_v1.publisher import Client as PublisherClient
from google.cloud.pubsub_v1.types import FlowControl
from google.api_core.exceptions import AlreadyExists
from concurrent.futures import TimeoutError


def get_publisher_client(project_id: str = "demo-project") -> PublisherClient:
    """
    取得 Pub/Sub Publisher 客戶端
    
    Args:
        project_id: GCP 專案 ID，預設為 demo-project（適用於 emulator）
    
    Returns:
        PublisherClient 實例
    
    Environment Variables:
        PUBSUB_EMULATOR_HOST: 設定後會自動連接到 emulator（例如：localhost:8085）
    """
    emulator_host = os.getenv("PUBSUB_EMULATOR_HOST")
    
    if emulator_host:
        print(f"🔧 使用 Pub/Sub Emulator: {emulator_host}")
    else:
        print(f"☁️  連接到正式 Pub/Sub 環境")
    
    return pubsub_v1.PublisherClient()


def is_emulator_mode() -> bool:
    """
    檢查是否在 emulator 模式下運行
    
    Returns:
        True 如果在 emulator 模式，否則 False
    """
    return bool(os.getenv("PUBSUB_EMULATOR_HOST"))


class PubSubPublisher:
    """Pub/Sub Publisher 輔助類別"""
    
    def __init__(self, project_id: str = "demo-project"):
        self.project_id = project_id
        self.client = get_publisher_client(project_id)
        self._topic_cache = set()
    
    def get_topic_path(self, topic_id: str) -> str:
        """取得 topic 的完整路徑"""
        return self.client.topic_path(self.project_id, topic_id)
    
    def topic_exists(self, topic_id: str) -> bool:
        """
        檢查 topic 是否存在
        
        Args:
            topic_id: Topic ID
        
        Returns:
            True 如果存在，否則 False
        """
        if topic_id in self._topic_cache:
            return True
            
        topic_path = self.get_topic_path(topic_id)
        
        try:
            self.client.get_topic(request={"topic": topic_path})
            self._topic_cache.add(topic_id)
            return True
        except Exception:
            return False
    
    def ensure_topic_exists(self, topic_id: str) -> str:
        """
        確保 topic 存在，不存在則自動建立
        
        Args:
            topic_id: Topic ID
        
        Returns:
            Topic 路徑
        """
        if topic_id in self._topic_cache:
            return self.get_topic_path(topic_id)
        
        if self.topic_exists(topic_id):
            return self.get_topic_path(topic_id)
        
        return self.create_topic(topic_id)
    
    def create_topic(self, topic_id: str) -> str:
        """
        建立 topic
        
        Args:
            topic_id: Topic ID
        
        Returns:
            Topic 路徑
        """
        topic_path = self.get_topic_path(topic_id)
        
        try:
            topic = self.client.create_topic(request={"name": topic_path})
            self._topic_cache.add(topic_id)
            print(f"✅ Topic 建立成功: {topic.name}")
            return topic.name
        except AlreadyExists:
            self._topic_cache.add(topic_id)
            print(f"ℹ️  Topic 已存在: {topic_path}")
            return topic_path
        except Exception as e:
            print(f"❌ 建立 Topic 失敗: {e}")
            raise
    
    def publish_message(self, topic_id: str, data: dict, **attributes) -> str:
        """
        發布訊息到指定 topic，自動確保 topic 存在
        
        Args:
            topic_id: Topic ID
            data: 要發布的資料（會轉換為 JSON）
            **attributes: 額外的訊息屬性
        
        Returns:
            訊息 ID
        """
        # 確保 topic 存在
        self.ensure_topic_exists(topic_id)
        
        topic_path = self.get_topic_path(topic_id)
        
        # 將資料轉換為 JSON bytes
        message_data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        
        # 發布訊息
        future = self.client.publish(topic_path, message_data, **attributes)
        message_id = future.result()
        
        return message_id
    
    def publish_batch(self, topic_id: str, messages: list[dict]) -> list[str]:
        """
        批次發布多個訊息
        
        Args:
            topic_id: Topic ID
            messages: 要發布的訊息列表
        
        Returns:
            訊息 ID 列表
        """
        # 確保 topic 存在
        self.ensure_topic_exists(topic_id)
        
        message_ids = []
        for message in messages:
            message_id = self.publish_message(topic_id, message)
            message_ids.append(message_id)
        
        return message_ids
    
    def delete_topic(self, topic_id: str) -> None:
        """
        刪除 topic
        
        Args:
            topic_id: Topic ID
        """
        topic_path = self.get_topic_path(topic_id)
        self.client.delete_topic(request={"topic": topic_path})
        self._topic_cache.discard(topic_id)
        print(f"🗑️  Topic 已刪除: {topic_path}")


class PubSubSubscriber:
    """Pub/Sub 訂閱者輔助類別"""
    
    def __init__(self, project_id: str, subscription_id: str, topic_id: Optional[str] = None):
        """
        初始化訂閱者
        
        Args:
            project_id: GCP 專案 ID
            subscription_id: 訂閱 ID
            topic_id: Topic ID（可選，用於自動創建訂閱）
        """
        self.project_id = project_id
        self.subscription_id = subscription_id
        self.topic_id = topic_id
        self.subscriber = pubsub_v1.SubscriberClient()
        self.subscription_path = self.subscriber.subscription_path(
            project_id, subscription_id
        )
        self._streaming_pull_future = None  # 保存 future 引用以便取消
        
        if is_emulator_mode():
            print(f"🔧 使用 Pub/Sub Emulator: {os.getenv('PUBSUB_EMULATOR_HOST')}")
        else:
            print(f"☁️  連接到正式 Pub/Sub 環境")
    
    def subscription_exists(self) -> bool:
        """
        檢查訂閱是否存在
        
        Returns:
            True 如果存在，否則 False
        """
        try:
            self.subscriber.get_subscription(request={"subscription": self.subscription_path})
            return True
        except Exception:
            return False
    
    def create_subscription(self) -> str:
        """
        建立訂閱
        
        Returns:
            訂閱路徑
        """
        if not self.topic_id:
            raise ValueError("無法建立訂閱：未提供 topic_id")
        
        # 確保 topic 存在（使用 Publisher 來建立 topic）
        try:
            publisher = PubSubPublisher(project_id=self.project_id)
            topic_path = publisher.ensure_topic_exists(self.topic_id)
            print(f"✅ Topic 已確認存在: {topic_path}")
        except Exception as e:
            print(f"❌ 確保 topic 存在時失敗: {e}")
            raise
        
        # 建立訂閱
        try:
            subscription = self.subscriber.create_subscription(
                request={
                    "name": self.subscription_path,
                    "topic": topic_path
                }
            )
            print(f"✅ 訂閱建立成功: {subscription.name}")
            return subscription.name
        except AlreadyExists:
            print(f"ℹ️  訂閱已存在: {self.subscription_path}")
            return self.subscription_path
        except Exception as e:
            print(f"❌ 建立訂閱失敗: {e}")
            raise
    
    def ensure_subscription_exists(self) -> str:
        """
        確保訂閱存在，不存在則自動建立
        
        Returns:
            訂閱路徑
        """
        if self.subscription_exists():
            return self.subscription_path
        
        return self.create_subscription()
    
    def subscribe(
        self,
        callback: Callable[[dict], None],
        timeout: Optional[float] = None,
        max_retries: int = 5,
        retry_delay: int = 5
    ) -> None:
        """
        訂閱訊息並處理（含自動重連機制）
        
        Args:
            callback: 處理訊息的回調函數，接收解析後的訊息資料
            timeout: 超時時間（秒），None 表示永久運行
            max_retries: 最大重試次數（0 表示無限重試）
            retry_delay: 重試延遲時間（秒）
        """
        # 確保訂閱存在
        try:
            self.ensure_subscription_exists()
        except Exception as e:
            print(f"❌ 無法確保訂閱存在: {e}")
            if not self.subscription_exists():
                raise
        
        def message_callback(message: pubsub_v1.subscriber.message.Message) -> None:
            """處理接收到的訊息"""
            try:
                # 解析訊息資料
                data = json.loads(message.data.decode('utf-8'))
                
                # print(f"📨 收到訊息 ID: {message.message_id}")
                
                # 呼叫使用者提供的回調函數
                callback(data)
                
                # 確認訊息已處理
                message.ack()
                # print(f"✅ 訊息已確認: {message.message_id}")
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON 解析錯誤: {e}")
                message.nack()
            except Exception as e:
                print(f"❌ 處理訊息時發生錯誤: {e}")
                message.nack()
        
        # 配置 Flow Control 以避免資源耗盡
        flow_control = FlowControl(
            max_messages=100,  # 同時處理的最大訊息數
            max_bytes=10 * 1024 * 1024,  # 10 MB
        )
        
        retry_count = 0
        while True:
            try:
                print(f"🎧 開始監聽訂閱: {self.subscription_path}")
                
                # 建立串流拉取（含 flow control）
                streaming_pull_future = self.subscriber.subscribe(
                    self.subscription_path,
                    callback=message_callback,
                    flow_control=flow_control
                )
                
                # 保存引用以便外部取消
                self._streaming_pull_future = streaming_pull_future
                
                # 重置重試計數器（成功連線）
                retry_count = 0
                
                # 等待訊息（阻塞式）
                streaming_pull_future.result(timeout=timeout)
                
                # 正常結束（timeout）
                break
                
            except TimeoutError:
                streaming_pull_future.cancel()
                print(f"⏰ 訂閱已超時")
                break
                
            except KeyboardInterrupt:
                streaming_pull_future.cancel()
                print(f"\n🛑 訂閱已停止")
                break
                
            except Exception as e:
                error_msg = str(e)
                
                # 取消當前串流
                try:
                    streaming_pull_future.cancel()
                except:
                    pass
                
                # 檢查是否為可重試的錯誤
                is_retryable = (
                    "RST_STREAM" in error_msg or
                    "499" in error_msg or
                    "503" in error_msg or
                    "UNAVAILABLE" in error_msg or
                    "DEADLINE_EXCEEDED" in error_msg
                )
                
                if not is_retryable:
                    print(f"❌ 訂閱發生不可重試的錯誤: {e}")
                    raise
                
                # 執行重試邏輯
                retry_count += 1
                
                if max_retries > 0 and retry_count > max_retries:
                    print(f"❌ 已達最大重試次數 ({max_retries})，停止訂閱")
                    raise
                
                print(f"⚠️  訂閱發生錯誤: {e}")
                print(f"🔄 將在 {retry_delay} 秒後重試... (第 {retry_count} 次)")
                
                # 延遲後重試
                time.sleep(retry_delay)
                
                # 重新建立訂閱者客戶端
                try:
                    self.subscriber.close()
                except:
                    pass
                
                self.subscriber = pubsub_v1.SubscriberClient()
                print(f"🔌 已重新建立訂閱者連線")
    
    def close(self) -> None:
        """關閉訂閱者連線"""
        # 先取消訂閱 future（如果存在）
        if self._streaming_pull_future:
            try:
                self._streaming_pull_future.cancel()
                print("🛑 已取消訂閱串流")
            except Exception as e:
                print(f"⚠️  取消訂閱串流時發生錯誤: {e}")
        
        # 關閉訂閱者客戶端
        try:
            self.subscriber.close()
            print("🔌 訂閱者連線已關閉")
        except Exception as e:
            print(f"⚠️  關閉訂閱者時發生錯誤: {e}")
