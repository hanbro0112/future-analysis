"""
Pub/Sub 客戶端模組
提供連接 Pub/Sub Emulator 或正式環境的功能
"""
import os
import json
from typing import Callable, Optional, Any
from google.cloud import pubsub_v1
from google.cloud.pubsub_v1.publisher import Client as PublisherClient
from google.api_core.exceptions import AlreadyExists


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
