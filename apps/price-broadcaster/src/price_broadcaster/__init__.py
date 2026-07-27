"""
Price Broadcaster - 報價廣播服務
透過 WebSocket 提供即時報價，並儲存每秒報價到 Firestore
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

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import config
from pubsub import PubSubSubscriber
from firestore_writer import FirestoreWriter

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
        
        # 每秒報價儲存（用於每分鐘寫入 Firestore）
        # key: (code, minute_timestamp), value: {second: {price, underlying_price, volume}}
        self.minute_prices: Dict[tuple, Dict[int, dict]] = defaultdict(dict)
        
        # 保存每個商品最後一分鐘的最後價格（用於填充下一分鐘的第 0 秒）
        self.last_minute_prices: Dict[str, float] = {}
        
        # 每秒總成交量累計（每秒重置）
        # 格式: {code: volume}
        self.second_volumes: Dict[str, int] = defaultdict(int)
        
        # 初始化 Firestore Writer
        self.firestore_writer = FirestoreWriter(
            project_id=config['gcp_project_id']
        )
        
        # Pub/Sub 訂閱器（用於關閉時清理）
        self.subscriber: Optional[PubSubSubscriber] = None
        
        # 設定路由
        self.setup_routes()
        
        # 背景任務
        self.broadcast_task: Optional[asyncio.Task] = None
        self.pubsub_task: Optional[asyncio.Task] = None
        self.save_task: Optional[asyncio.Task] = None
    
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
                
                # 儲存當前秒的報價（用於每分鐘寫入）- 不論是否有連接都要儲存
                if self.latest_prices:
                    now = datetime.now(TAIPEI_TZ)
                    current_second = now.second
                    minute_timestamp = now.replace(second=0, microsecond=0)
                    
                    for code, price_info in self.latest_prices.items():
                        key = (code, minute_timestamp)
                        # 儲存完整的報價資訊
                        self.minute_prices[key][current_second] = {
                            "price": price_info["price"],
                            "underlying_price": price_info["underlying_price"],
                            "volume": price_info["volume"]
                        }
                    
                    # 重置每秒成交量累計
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
    
    async def save_minute_prices(self):
        """每分鐘儲存報價到 Firestore"""
        while True:
            try:
                # 等待到下一分鐘開始
                now = datetime.now(TAIPEI_TZ)
                seconds_to_wait = 60 - now.second
                await asyncio.sleep(seconds_to_wait)

                # 睡眠後重新取得當前時間
                current_time = datetime.now(TAIPEI_TZ)
                current_minute = current_time.replace(second=0, microsecond=0)
                
                # 計算上一分鐘的時間戳
                prev_minute = current_minute - timedelta(minutes=1)

                # 儲存上一分鐘的所有報價
                keys_to_remove = []
                for (code, minute_timestamp), prices in self.minute_prices.items():
                    if minute_timestamp == prev_minute and prices:
                        # 檢查是否在交易時段，只有交易時段才寫入
                        if not self._is_in_trading_hours(minute_timestamp):
                            print(f"⏸️  非交易時段，跳過儲存: {minute_timestamp.strftime('%Y-%m-%d %H:%M')}")
                            keys_to_remove.append((code, minute_timestamp))
                            continue
                        
                        # 取得商品代碼（移除合約月份）
                        clean_code = code[:3] if len(code) >= 3 else code
                        
                        # 決定日期：夜盤跨日時（00:00-05:00）使用前一天日期
                        market_type = self._get_market_type(minute_timestamp)
                        bar_date = minute_timestamp
                        if market_type == 'after_hours' and minute_timestamp.hour < 6:
                            # 夜盤且在 00:00-05:59，日期為前一天
                            bar_date = minute_timestamp - timedelta(days=1)
                        
                        # 建立 Firestore 路徑：market/{code}/{YYYYMMDD_tick}/{HHMM}
                        date_str = bar_date.strftime('%Y%m%d')
                        time_str = minute_timestamp.strftime('%H%M')
                        collection_path = f"market/{clean_code}/{date_str}_tick"
                        doc_id = time_str
                        
                        # 準備儲存的資料（格式：{秒數: {price, underlying_price, volume}}）- 只儲存 0-59 秒
                        filtered_prices = {
                            second: price_info 
                            for second, price_info in prices.items()
                            if 0 <= second <= 59
                        }
                        
                        # 前向填充缺失的秒數（只填充 price）
                        save_data = {}
                        last_price = None
                        
                        # 如果第 0 秒缺失，嘗試使用上一分鐘的最後價格
                        if 0 not in filtered_prices and code in self.last_minute_prices:
                            last_price = self.last_minute_prices[code]
                        
                        for second in range(60):
                            if second in filtered_prices:
                                # 有資料，使用實際報價（完整資訊）
                                price_info = filtered_prices[second]
                                last_price = price_info["price"]
                                save_data[str(second).zfill(2)] = price_info
                            elif last_price is not None:
                                # 缺失資料，只填充 price
                                save_data[str(second).zfill(2)] = {"price": last_price}
                            # 如果 last_price 還是 None，則跳過該秒
                        
                        # 保存這一分鐘的最後價格供下一分鐘使用
                        if last_price is not None:
                            self.last_minute_prices[code] = last_price
                        
                        # 寫入到 Firestore
                        try:
                            # 計算實際報價筆數（不含時間戳）
                            price_count = len(save_data)

                            self.firestore_writer.write_document(
                                collection=collection_path,
                                data=save_data,
                                document_id=doc_id
                            )

                            print(f"💾 已儲存分鐘報價: {clean_code}/{date_str}_tick/{doc_id} "
                                  f"(報價 {price_count} 筆)")
                        except Exception as e:
                            print(f"❌ 儲存報價時發生錯誤: {e}")
                        
                        keys_to_remove.append((code, minute_timestamp))
                
                # 清理已儲存的資料
                for key in keys_to_remove:
                    del self.minute_prices[key]
                
            except Exception as e:
                print(f"❌ 儲存分鐘報價錯誤: {e}")
                await asyncio.sleep(1)
    
    def _get_market_type(self, dt: datetime) -> str:
        """
        判斷市場時段類型
        
        台指期交易時間：
        - 日盤：08:45 - 13:45
        - 夜盤：15:00 - 05:00 (次日)
        
        Args:
            dt: 時間
            
        Returns:
            'regular' 或 'after_hours'
        """
        hour = dt.hour
        minute = dt.minute
        time_in_minutes = hour * 60 + minute
        
        # 日盤時段：08:45 - 13:45
        day_session_start = 8 * 60 + 45  # 525
        day_session_end = 13 * 60 + 45   # 825
        
        # 夜盤時段：15:00 - 05:00 (次日)
        night_session_start = 15 * 60    # 900
        night_session_end = 5 * 60       # 300 (次日)
        
        if day_session_start <= time_in_minutes <= day_session_end:
            return 'regular'
        elif time_in_minutes >= night_session_start or time_in_minutes <= night_session_end:
            return 'after_hours'
        else:
            # 盤前或休市時段，預設為 regular
            return 'regular'
    
    def _is_in_trading_hours(self, dt: datetime) -> bool:
        """
        判斷指定時間是否在交易時段內
        
        台指期交易時間：
        - 日盤：週一至週五 08:45 - 13:45
        - 夜盤：週一至週五 15:00 - 次日 05:00
        - 週六：00:00-05:00（週五夜盤延續）
        - 週日：15:00 開始（週日夜盤）
        
        Args:
            dt: 時間
            
        Returns:
            是否在交易時段
        """
        day = dt.weekday()  # 0 = 週一, 6 = 週日
        hour = dt.hour
        minute = dt.minute
        time_in_minutes = hour * 60 + minute
        
        # 時段定義（與前端保持一致）
        day_session_start = 8 * 60 + 45  # 08:45 (525 分鐘)
        day_session_end = 13 * 60 + 45   # 13:45 (825 分鐘)
        night_session_start = 15 * 60    # 15:00 (900 分鐘)
        night_session_end = 5 * 60       # 05:00 (300 分鐘)
        
        # 週六：只有 00:00-05:00 算是週五夜盤的延續
        if day == 5:  # 週六
            return time_in_minutes < night_session_end
        
        # 週日：只有夜盤（15:00 開始）
        if day == 6:  # 週日
            return time_in_minutes >= night_session_start
        
        # 週一至週五
        # 日盤時段
        if day_session_start <= time_in_minutes <= day_session_end:
            return True
        # 夜盤時段（15:00 之後或 05:00 之前）
        elif time_in_minutes >= night_session_start or time_in_minutes < night_session_end:
            return True
        
        # 其他時間不在交易時段
        return False
    
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
            subscription_id = config['pubsub_subscription_id']
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
        
        # 啟動儲存任務
        self.save_task = asyncio.create_task(self.save_minute_prices())
        print("✅ 報價儲存任務已啟動")
        
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
        tasks = [self.broadcast_task, self.save_task, self.pubsub_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"⚠️  取消任務時發生錯誤: {e}")
        
        # 最後關閉 Firestore Writer
        try:
            self.firestore_writer.close()
        except Exception as e:
            print(f"⚠️  關閉 Firestore Writer 時發生錯誤: {e}")
        
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
