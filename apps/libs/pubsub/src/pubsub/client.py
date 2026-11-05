"""
Pub/Sub 客戶端模組
提供連接 Pub/Sub Emulator 或正式環境的功能
"""
import os
import json
import threading
import time
from typing import Callable, Optional
from google.cloud import pubsub_v1
from google.cloud.pubsub_v1.publisher import Client as PublisherClient
from google.cloud.pubsub_v1.types import (
    BatchSettings,
    FlowControl,
    LimitExceededBehavior,
    PublisherOptions,
    PublishFlowControl,
)
from google.api_core.exceptions import (
    Aborted,
    AlreadyExists,
    Cancelled,
    DeadlineExceeded,
    GatewayTimeout,
    InternalServerError,
    ResourceExhausted,
    RetryError,
    ServiceUnavailable,
    TooManyRequests,
    Unknown,
)
from concurrent.futures import CancelledError, TimeoutError

# 暫時性錯誤：重新建立串流通常就能恢復（權限不足、訂閱不存在等永久性錯誤不在此列）
_RETRYABLE_EXCEPTIONS = (
    ServiceUnavailable,
    DeadlineExceeded,
    GatewayTimeout,
    InternalServerError,
    Aborted,
    ResourceExhausted,
    TooManyRequests,
    Unknown,
    Cancelled,
    RetryError,
)

# 原始 gRPC 錯誤沒有被包成 api_core 例外時，退而用訊息內容判斷
_RETRYABLE_MESSAGE_MARKERS = ("RST_STREAM", "UNAVAILABLE", "DEADLINE_EXCEEDED")

# 串流撐過這段時間才失敗，視為先前連線是健康的，連續失敗次數重新計算
HEALTHY_STREAM_SECONDS = 60.0

# 非同步發布的批次設定：累積到 100 則或 10ms 就送出，每筆最多多等 10ms
ASYNC_BATCH_MAX_MESSAGES = 100
ASYNC_BATCH_MAX_BYTES = 1024 * 1024
ASYNC_BATCH_MAX_LATENCY_SECONDS = 0.01

# 尚未送達的訊息上限；超過時 publish 直接丟出例外（記為丟棄），不阻塞呼叫端（Shioaji 回調執行緒）
ASYNC_FLOW_CONTROL_MESSAGE_LIMIT = 10_000
ASYNC_FLOW_CONTROL_BYTE_LIMIT = 20 * 1024 * 1024

# 發布失敗的 log 節流：第 1 次與之後每 N 次才印一行，避免服務異常時洗版
PUBLISH_FAILURE_LOG_EVERY = 100


def is_retryable_error(error: BaseException) -> bool:
    """判斷訂閱串流的錯誤是否為暫時性錯誤（值得重建串流重試）"""
    if isinstance(error, _RETRYABLE_EXCEPTIONS):
        return True

    message = str(error)
    return any(marker in message for marker in _RETRYABLE_MESSAGE_MARKERS)


def get_publisher_client(
    project_id: str = "demo-project",
    batch_settings: BatchSettings | None = None,
    publisher_options: PublisherOptions | None = None,
) -> PublisherClient:
    """
    取得 Pub/Sub Publisher 客戶端

    Args:
        project_id: GCP 專案 ID，預設為 demo-project（適用於 emulator）
        batch_settings: 批次發布設定，None 表示使用函式庫預設值
        publisher_options: 發布選項（例如 flow control），None 表示使用函式庫預設值

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

    kwargs: dict[str, object] = {}
    if batch_settings is not None:
        kwargs["batch_settings"] = batch_settings
    if publisher_options is not None:
        kwargs["publisher_options"] = publisher_options
    return pubsub_v1.PublisherClient(**kwargs)


def build_async_publisher_settings() -> tuple[BatchSettings, PublisherOptions]:
    """
    非同步發布使用的批次與 flow control 設定。

    flow control 超過上限時選擇丟出例外（ERROR）而不是阻塞（BLOCK），
    因為呼叫端是 Shioaji 的報價回調執行緒，絕不能被卡住。
    """
    batch_settings = BatchSettings(
        max_messages=ASYNC_BATCH_MAX_MESSAGES,
        max_bytes=ASYNC_BATCH_MAX_BYTES,
        max_latency=ASYNC_BATCH_MAX_LATENCY_SECONDS,
    )
    publisher_options = PublisherOptions(
        flow_control=PublishFlowControl(
            message_limit=ASYNC_FLOW_CONTROL_MESSAGE_LIMIT,
            byte_limit=ASYNC_FLOW_CONTROL_BYTE_LIMIT,
            limit_exceeded_behavior=LimitExceededBehavior.ERROR,
        )
    )
    return batch_settings, publisher_options


def is_emulator_mode() -> bool:
    """
    檢查是否在 emulator 模式下運行
    
    Returns:
        True 如果在 emulator 模式，否則 False
    """
    return bool(os.getenv("PUBSUB_EMULATOR_HOST"))


class PubSubPublisher:
    """Pub/Sub Publisher 輔助類別"""
    
    def __init__(self, project_id: str = "demo-project", async_mode: bool = False):
        """
        Args:
            project_id: GCP 專案 ID
            async_mode: True 時套用非同步發布用的批次與 flow control 設定，
                搭配 publish_message_async 使用（例如 price-listener 的報價回調）
        """
        self.project_id = project_id
        if async_mode:
            batch_settings, publisher_options = build_async_publisher_settings()
            self.client = get_publisher_client(project_id, batch_settings, publisher_options)
        else:
            self.client = get_publisher_client(project_id)
        self._topic_cache = set()

        # 非同步發布的統計（done callback 在 publisher 內部執行緒，需加鎖）
        self._stats_lock = threading.Lock()
        self._published_count = 0
        self._failed_count = 0
        self._dropped_count = 0

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
    
    def publish_message_async(self, topic_id: str, data: dict, **attributes) -> bool:
        """
        非同步發布訊息：只把訊息交給 publisher 的批次佇列就返回，不等待伺服器回應。

        不會檢查 topic 是否存在（呼叫端應在初始化時用 ensure_topic_exists 確認過），
        發布結果由 done callback 統計；任何失敗都不會拋出，避免影響呼叫端（報價回調）。

        Args:
            topic_id: Topic ID
            data: 要發布的資料（會轉換為 JSON）
            **attributes: 額外的訊息屬性

        Returns:
            True 代表已交給 publisher；False 代表被丟棄（flow control 超限、publisher 已停止等）
        """
        try:
            message_data = json.dumps(data, ensure_ascii=False).encode("utf-8")
            future = self.client.publish(self.get_topic_path(topic_id), message_data, **attributes)
        except Exception as e:
            self._record_dropped(e)
            return False

        future.add_done_callback(self._on_publish_done)
        return True

    def _on_publish_done(self, future: "pubsub_v1.publisher.futures.Future") -> None:
        """發布完成的回調：成功計數，失敗計數並節流記錄"""
        try:
            future.result()
        except Exception as e:
            with self._stats_lock:
                self._failed_count += 1
                failed = self._failed_count
            if failed == 1 or failed % PUBLISH_FAILURE_LOG_EVERY == 0:
                print(f"❌ Pub/Sub 非同步發布失敗（累計 {failed} 筆）: {type(e).__name__}: {e}")
            return

        with self._stats_lock:
            self._published_count += 1

    def _record_dropped(self, error: BaseException) -> None:
        """訊息在交給 publisher 前就被丟棄：計數並節流記錄"""
        with self._stats_lock:
            self._dropped_count += 1
            dropped = self._dropped_count
        if dropped == 1 or dropped % PUBLISH_FAILURE_LOG_EVERY == 0:
            print(f"⚠️  Pub/Sub 訊息被丟棄（累計 {dropped} 筆）: {type(error).__name__}: {error}")

    def get_publish_stats(self) -> dict[str, int]:
        """取得非同步發布統計：published（已確認送達）、failed（送出失敗）、dropped（未送出即丟棄）"""
        with self._stats_lock:
            return {
                "published": self._published_count,
                "failed": self._failed_count,
                "dropped": self._dropped_count,
            }

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
    
    def close(self) -> None:
        """釋放 Publisher 連線，並先把批次佇列中尚未送出的訊息送完；呼叫後不可再發布訊息"""
        self.client.stop()

        stats = self.get_publish_stats()
        if stats["failed"] or stats["dropped"]:
            print(f"📊 Pub/Sub 非同步發布統計: 成功 {stats['published']} / "
                  f"失敗 {stats['failed']} / 丟棄 {stats['dropped']}")

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
        self._stop_event = threading.Event()  # close() 後設定，讓 subscribe() 乾淨地結束
        self._close_lock = threading.Lock()

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
    
    def _on_message_failure(self, message: pubsub_v1.subscriber.message.Message, error: Exception) -> None:
        """
        訊息處理失敗（解析錯誤、callback 拋出例外）的統一出口。

        目前策略：一律 ack。報價資料時效性高，重送只會造成亂序與重複累計成交量，
        所以失敗的訊息不再重送。

        之後若要改策略（例如暫時性錯誤 nack、永久性錯誤送 dead-letter、依錯誤類型區分），
        只需要修改這個方法，不用動 subscribe() 的串流邏輯。
        """
        try:
            message.ack()
        except Exception as ack_error:
            print(f"⚠️  失敗訊息 ack 時發生錯誤: {type(ack_error).__name__}: {ack_error} "
                  f"(原始錯誤: {type(error).__name__}: {error})")

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
            max_retries: 連續失敗的最大重試次數（0 表示無限重試）；串流穩定運作
                HEALTHY_STREAM_SECONDS 秒後才失敗會重新計算
            retry_delay: 重試延遲時間（秒）

        Raises:
            不可重試的錯誤，或連續失敗超過 max_retries 時，原例外會直接拋出；
            呼叫 close() 則會讓本方法正常返回。
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
                self._on_message_failure(message, e)
            except Exception as e:
                print(f"❌ 處理訊息時發生錯誤: {e}")
                self._on_message_failure(message, e)
        
        # 配置 Flow Control 以避免資源耗盡
        flow_control = FlowControl(
            max_messages=100,  # 同時處理的最大訊息數
            max_bytes=10 * 1024 * 1024,  # 10 MB
        )
        
        retry_count = 0
        while not self._stop_event.is_set():
            streaming_pull_future = None
            stream_started = time.monotonic()
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

                # 等待訊息（阻塞式）
                streaming_pull_future.result(timeout=timeout)

                # 正常結束（timeout）
                break

            except CancelledError:
                # close() 主動取消串流（例如收盤或服務關閉），不是錯誤
                print(f"🛑 訂閱串流已取消")
                break

            except TimeoutError:
                if streaming_pull_future is not None:
                    streaming_pull_future.cancel()
                print(f"⏰ 訂閱已超時")
                break

            except KeyboardInterrupt:
                if streaming_pull_future is not None:
                    streaming_pull_future.cancel()
                print(f"\n🛑 訂閱已停止")
                break

            except Exception as e:
                # 取消當前串流
                try:
                    if streaming_pull_future is not None:
                        streaming_pull_future.cancel()
                except Exception:
                    pass

                # close() 之後關閉連線造成的例外屬於預期行為
                if self._stop_event.is_set():
                    break

                if not is_retryable_error(e):
                    print(f"❌ 訂閱發生不可重試的錯誤: {type(e).__name__}: {e}")
                    raise

                # 串流撐過一段時間才失敗，代表先前連線是健康的，連續失敗次數重新計算
                if time.monotonic() - stream_started >= HEALTHY_STREAM_SECONDS:
                    retry_count = 0
                retry_count += 1

                if max_retries > 0 and retry_count > max_retries:
                    print(f"❌ 已達最大重試次數 ({max_retries})，停止訂閱")
                    raise

                print(f"⚠️  訂閱發生錯誤: {type(e).__name__}: {e}")
                print(f"🔄 將在 {retry_delay} 秒後重試... (第 {retry_count} 次)")

                # 延遲後重試（close() 會立刻中斷等待）
                if self._stop_event.wait(retry_delay):
                    break

                # 重新建立訂閱者客戶端
                try:
                    self.subscriber.close()
                except Exception:
                    pass

                self.subscriber = pubsub_v1.SubscriberClient()
                print(f"🔌 已重新建立訂閱者連線")

    def close(self) -> None:
        """關閉訂閱者連線；若 subscribe() 正在阻塞等待，會讓它乾淨地返回。可重複呼叫"""
        with self._close_lock:
            if self._stop_event.is_set():
                return
            self._stop_event.set()

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
