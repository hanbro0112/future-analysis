"""
Price Broadcaster - 報價廣播服務
透過 WebSocket 提供即時報價
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # 添加 apps 目錄到 Python 路徑

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Set
from collections import defaultdict
from zoneinfo import ZoneInfo

# 台指期交易時段以台北時間為準；容器內部時鐘預設為 UTC，
# 所有涉及交易時段判斷與 Firestore 文件路徑命名的時間都需以此時區為準。
TAIPEI_TZ = ZoneInfo("Asia/Taipei")

# WebSocket 關閉代碼：非交易時段拒絕連線 / 收盤時中斷連線（自訂應用層代碼，對應 HTTP 403）
WS_CLOSE_CODE_NOT_TRADING_HOURS = 4403
# WebSocket 標準關閉代碼：伺服器關閉中 / 服務重啟中
WS_CLOSE_CODE_GOING_AWAY = 1001
WS_CLOSE_CODE_SERVICE_RESTART = 1012

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import config
from pubsub import PubSubSubscriber
from trading_calendar import ActiveWindow, is_session_open

from .auth import verify_firebase_token, InvalidTokenError

# 開盤前 5 分鐘就開始訂閱；廣播不需要寫入資料，所以收盤當下就結束（不留緩衝）
ACTIVE_WINDOW = ActiveWindow(warmup=timedelta(minutes=5))

# 待機時每分鐘判斷一次是否進入啟用窗口；時段進行中縮短間隔，才能在收盤後立刻中斷連線
IDLE_CHECK_INTERVAL_SECONDS = 60.0
RUNNING_CHECK_INTERVAL_SECONDS = 1.0

# 等待 Pub/Sub 訂閱關閉的上限秒數
SUBSCRIBER_STOP_TIMEOUT_SECONDS = 10.0


class TickData:
    """Tick 資料"""
    def __init__(self, code: str, datetime: datetime, close: Decimal, 
                 underlying_price: Optional[Decimal] = None, volume: int = 0):
        self.code = code
        self.datetime = datetime
        self.close = close
        self.underlying_price = underlying_price
        self.volume = volume


class PriceBroadcaster:
    """報價廣播器"""
    
    def __init__(self):
        self.app = FastAPI(title="Price Broadcaster")
        
        # CORS 設定
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # WebSocket 連接管理
        self.active_connections: Set[WebSocket] = set()
        
        # 最新報價快取（每秒更新）
        # 格式: {code: {"price": float, "underlying_price": float, "volume": int}}
        self.latest_prices: Dict[str, dict] = {}

        # 每秒總成交量累計（每秒重置）
        # 格式: {code: volume}
        self.second_volumes: Dict[str, int] = defaultdict(int)

        # Pub/Sub 訂閱器（用於關閉時清理）
        self.subscriber: Optional[PubSubSubscriber] = None
        
        # 設定路由
        self.setup_routes()
        
        # 背景任務
        self.broadcast_task: Optional[asyncio.Task] = None
        self.pubsub_task: Optional[asyncio.Task] = None
        self.supervisor_task: Optional[asyncio.Task] = None

    @property
    def session_running(self) -> bool:
        """目前是否正在進行一個交易時段（背景任務已啟動）"""
        return self.broadcast_task is not None

    def setup_routes(self):
        """設定 API 路由"""
        
        @self.app.get("/")
        async def root():
            return {"message": "Price Broadcaster is running"}
        
        @self.app.get("/health")
        async def health():
            return {
                "status": "healthy",
                "session_running": self.session_running,
                "connections": len(self.active_connections),
                "latest_prices": self.latest_prices
            }
        
        @self.app.websocket("/ws/price")
        async def websocket_endpoint(websocket: WebSocket):
            token = websocket.query_params.get("token")
            try:
                verify_firebase_token(token)
            except InvalidTokenError as e:
                print(f"❌ WebSocket 驗證失敗: {e}")
                await websocket.close(code=4401)
                return

            if not is_session_open():
                print("⛔ 非交易時段，拒絕 WebSocket 連線")
                await websocket.close(code=WS_CLOSE_CODE_NOT_TRADING_HOURS)
                return

            await self.handle_websocket(websocket)
    
    async def handle_websocket(self, websocket: WebSocket):
        """處理 WebSocket 連接"""
        await websocket.accept()
        self.active_connections.add(websocket)
        
        print(f"✅ WebSocket 連接建立，目前連接數: {len(self.active_connections)}")
        
        try:
            # 發送當前最新報價
            if self.latest_prices:
                await websocket.send_json({
                    "type": "price",
                    "data": self.latest_prices,
                    "timestamp": datetime.now(TAIPEI_TZ).isoformat()
                })
            
            # 保持連接
            while True:
                # 接收訊息（心跳包）
                await websocket.receive_text()
        
        except WebSocketDisconnect:
            # print(f"🔌 WebSocket 連接斷開")
            pass
        except Exception as e:
            # print(f"❌ WebSocket 錯誤: {e}")
            pass
        finally:
            self.active_connections.discard(websocket)
            print(f"📊 連接已移除，目前連接數: {len(self.active_connections)}")
    
    async def broadcast_prices(self):
        """每秒廣播最新報價給所有 WebSocket 客戶端"""
        while True:
            try:
                await asyncio.sleep(1)

                # 重置每秒成交量累計，下一秒重新累計（分鐘級報價統計已移至 price-analyzer）
                if self.latest_prices:
                    self.second_volumes.clear()

                # 如果有連接才廣播
                if not self.active_connections or not self.latest_prices:
                    continue
                
                # 準備報價訊息
                message = {
                    "type": "price",
                    "data": self.latest_prices,
                    "timestamp": datetime.now(TAIPEI_TZ).isoformat()
                }
                
                # 廣播給所有連接的客戶端
                disconnected = set()
                for connection in list(self.active_connections):
                    try:
                        await connection.send_json(message)
                    except Exception as e:
                        print(f"⚠️  發送失敗: {e}")
                        disconnected.add(connection)
                
                # 移除斷開的連接
                self.active_connections -= disconnected
                
            except Exception as e:
                print(f"❌ 廣播錯誤: {e}")
                await asyncio.sleep(1)
    
    def process_tick(self, data: dict):
        """處理接收到的 tick 資料"""
        try:
            # 驗證必要欄位
            if 'code' not in data or 'close' not in data:
                return
            
            code = data['code']
            close_price = float(data['close'])
            underlying_price = float(data.get('underlying_price', 0))
            volume = int(data.get('volume', 0))
            
            # 累計每秒的總成交量
            self.second_volumes[code] += volume
            
            # 更新最新報價（同一秒內多筆取最新價格，但累計成交量）
            self.latest_prices[code] = {
                "price": close_price,
                "underlying_price": underlying_price,
                "volume": self.second_volumes[code]
            }
            
        except Exception as e:
            print(f"⚠️  處理 tick 錯誤: {e}")
    
    async def subscribe_pubsub(self):
        """訂閱 Pub/Sub 訊息；訂閱失敗（重試用盡或不可重試的錯誤）會拋出例外，由時段監控收尾後重啟"""
        topic_id = config['pubsub_topic_id']
        subscription_id = config['pubsub_subscription_id_broadcaster']
        project_id = config['gcp_project_id']

        print(f"🚀 開始訂閱 Pub/Sub: {project_id}/{subscription_id}")

        # 初始化訂閱器（保存引用以便關閉時清理）
        self.subscriber = PubSubSubscriber(
            project_id=project_id,
            subscription_id=subscription_id,
            topic_id=topic_id
        )

        # 在背景執行緒中訂閱（阻塞式）
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self.subscriber.subscribe,
            self.process_tick
        )

    async def close_all_connections(self, code: int) -> None:
        """主動中斷所有 WebSocket 連線，避免客戶端停留在已經沒有新報價的連線上"""
        connections = list(self.active_connections)
        self.active_connections.clear()

        for connection in connections:
            try:
                await connection.close(code=code)
            except Exception as e:
                print(f"⚠️  關閉 WebSocket 連線時發生錯誤: {e}")

        if connections:
            print(f"🔌 已中斷 {len(connections)} 個 WebSocket 連線 (code: {code})")

    async def start_background_tasks(self):
        """開始一個交易時段：啟動每秒廣播與 Pub/Sub 訂閱（每個時段都建立全新的訂閱連線）"""
        print("⏰ 啟動背景任務...")

        # 啟動廣播任務
        self.broadcast_task = asyncio.create_task(self.broadcast_prices())
        print("✅ 報價廣播任務已啟動")

        # 啟動 Pub/Sub 訂閱任務
        self.pubsub_task = asyncio.create_task(self.subscribe_pubsub())
        print("✅ Pub/Sub 訂閱任務已啟動")

    async def stop_background_tasks(self, close_code: int = WS_CLOSE_CODE_NOT_TRADING_HOURS):
        """
        結束交易時段：關閉訂閱、停止背景任務、中斷所有連線並清空報價快取。
        回到待機狀態後，下一個窗口可以重新呼叫 start_background_tasks()。
        """
        print("🛑 停止背景任務...")

        # 先關閉 Pub/Sub 訂閱器（這會讓阻塞的 subscribe() 呼叫乾淨地返回）
        if self.subscriber:
            try:
                self.subscriber.close()
                print("🔌 Pub/Sub 訂閱已關閉")
            except Exception as e:
                print(f"⚠️  關閉 Pub/Sub 訂閱時發生錯誤: {e}")

        # 等訂閱執行緒返回，確認不會再有 tick 寫進報價快取（訂閱若已因錯誤結束，這裡會把錯誤記錄下來）
        if self.pubsub_task and not self.pubsub_task.cancelled():
            try:
                await asyncio.wait_for(self.pubsub_task, timeout=SUBSCRIBER_STOP_TIMEOUT_SECONDS)
            except TimeoutError:
                print("⚠️  等待 Pub/Sub 訂閱結束逾時，強制取消")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"⚠️  Pub/Sub 訂閱結束時發生錯誤: {e}")

        if self.broadcast_task and not self.broadcast_task.done():
            self.broadcast_task.cancel()
            try:
                await self.broadcast_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"⚠️  取消廣播任務時發生錯誤: {e}")

        # 廣播任務停止後再中斷連線，避免廣播迴圈與清除連線集合同時進行
        await self.close_all_connections(close_code)

        # 收盤後的報價已過期，清空以免下個時段開始前還被當成最新報價送出
        self.latest_prices.clear()
        self.second_volumes.clear()

        self.broadcast_task = None
        self.pubsub_task = None
        self.subscriber = None

        print("✨ 背景任務已停止")

    async def reconcile_session(self) -> None:
        """依目前是否在啟用窗口內，啟動、結束或重啟交易時段"""
        active = ACTIVE_WINDOW.contains()

        if active and not self.session_running:
            print("▶️  進入啟用時段，開始廣播")
            await self.start_background_tasks()
        elif not active and self.session_running:
            print("⏹️  啟用時段結束，中斷連線並回到待機")
            await self.stop_background_tasks()
        elif self.pubsub_task is not None and self.pubsub_task.done():
            # 訂閱任務在時段進行中意外結束，收尾後待下一輪檢查重新啟動
            print("⚠️  Pub/Sub 訂閱任務在時段進行中結束，收尾後將重新啟動本時段")
            await self.stop_background_tasks(close_code=WS_CLOSE_CODE_SERVICE_RESTART)

    async def supervise_sessions(self) -> None:
        """持續判斷是否在啟用窗口內：待機時每分鐘檢查一次，時段進行中每秒檢查一次"""
        while True:
            try:
                await self.reconcile_session()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"❌ 時段監控發生錯誤: {e}")

            await asyncio.sleep(
                RUNNING_CHECK_INTERVAL_SECONDS if self.session_running else IDLE_CHECK_INTERVAL_SECONDS
            )

    async def shutdown(self) -> None:
        """服務關閉：停止時段監控，並結束進行中的時段"""
        if self.supervisor_task and not self.supervisor_task.done():
            self.supervisor_task.cancel()
            try:
                await self.supervisor_task
            except asyncio.CancelledError:
                pass

        await self.stop_background_tasks(close_code=WS_CLOSE_CODE_GOING_AWAY)


# 全域實例
broadcaster = PriceBroadcaster()


@broadcaster.app.on_event("startup")
async def startup_event():
    """應用啟動事件：開始每分鐘判斷是否啟用的時段監控"""
    broadcaster.supervisor_task = asyncio.create_task(broadcaster.supervise_sessions())


@broadcaster.app.on_event("shutdown")
async def shutdown_event():
    """應用關閉事件"""
    await broadcaster.shutdown()


def main() -> None:
    """主函數"""
    # 預設值同步為 Cloud Run 注入的 PORT 預設值（8080），避免本機測試與正式環境行為不一致
    port = int(os.environ.get("PORT", 8080))
    print("🚀 Price Broadcaster 啟動中...")

    if config["is_local"]:
        print(f"📊 WebSocket 端點: ws://localhost:{port}/ws/price")
        print(f"🔍 健康檢查: http://localhost:{port}/health\n")

    uvicorn.run(
        broadcaster.app,
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
        # 使用新版 sans-I/O 實作，避免 websockets legacy 在客戶端異常斷線時印出冗長 traceback
        ws="websockets-sansio",
    )


__all__ = ["main", "broadcaster"]
