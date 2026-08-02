"""
Price Broadcaster - 報價廣播服務
透過 WebSocket 提供即時報價
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # 添加 apps 目錄到 Python 路徑

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Set
from collections import defaultdict
from zoneinfo import ZoneInfo

# 台指期交易時段以台北時間為準；容器內部時鐘預設為 UTC，
# 所有涉及交易時段判斷與 Firestore 文件路徑命名的時間都需以此時區為準。
TAIPEI_TZ = ZoneInfo("Asia/Taipei")

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import config
from pubsub import PubSubSubscriber

from .auth import verify_firebase_token, InvalidTokenError


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
    
    def setup_routes(self):
        """設定 API 路由"""
        
        @self.app.get("/")
        async def root():
            return {"message": "Price Broadcaster is running"}
        
        @self.app.get("/health")
        async def health():
            return {
                "status": "healthy",
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
                for connection in self.active_connections:
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
        """訂閱 Pub/Sub 訊息"""
        try:
            topic_id = config['pubsub_topic_id']
            subscription_id = config['pubsub_subscription_id_broadcaster']
            project_id = config['gcp_project_id']
            topic_id = config['pubsub_topic_id']
            
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
            
        except Exception as e:
            print(f"❌ Pub/Sub 訂閱錯誤: {e}")
    
    async def start_background_tasks(self):
        """啟動背景任務"""
        print("⏰ 啟動背景任務...")
        
        # 啟動廣播任務
        self.broadcast_task = asyncio.create_task(self.broadcast_prices())
        print("✅ 報價廣播任務已啟動")

        # 啟動 Pub/Sub 訂閱任務
        self.pubsub_task = asyncio.create_task(self.subscribe_pubsub())
        print("✅ Pub/Sub 訂閱任務已啟動")
    
    async def stop_background_tasks(self):
        """停止背景任務"""
        print("🛑 停止背景任務...")
        
        # 先關閉 Pub/Sub 訂閱器（這會中斷阻塞的 subscribe() 呼叫）
        if self.subscriber:
            try:
                self.subscriber.close()
                print("🔌 Pub/Sub 訂閱已關閉")
            except Exception as e:
                print(f"⚠️  關閉 Pub/Sub 訂閱時發生錯誤: {e}")
        
        # 然後取消所有背景任務
        tasks = [self.broadcast_task, self.pubsub_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"⚠️  取消任務時發生錯誤: {e}")

        print("✨ 背景任務已停止")


# 全域實例
broadcaster = PriceBroadcaster()


@broadcaster.app.on_event("startup")
async def startup_event():
    """應用啟動事件"""
    await broadcaster.start_background_tasks()


@broadcaster.app.on_event("shutdown")
async def shutdown_event():
    """應用關閉事件"""
    await broadcaster.stop_background_tasks()


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
        log_level="info"
    )


__all__ = ["main", "broadcaster"]
