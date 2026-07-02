"""
WebSocket 客戶端測試腳本
測試連接到 price-broadcaster 並接收報價
"""
import asyncio
import websockets
import json


async def test_websocket():
    """測試 WebSocket 連接"""
    uri = "ws://localhost:8001/ws/price"
    
    print(f"🔌 連接到 {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket 連接成功")
            
            # 接收訊息
            for i in range(10):  # 接收 10 次報價
                message = await websocket.recv()
                data = json.loads(message)
                
                print(f"\n📊 收到報價 #{i+1}:")
                print(f"   時間: {data['timestamp']}")
                print(f"   報價: {data['data']}")
                
                # 發送心跳
                await websocket.send("ping")
            
            print("\n✨ 測試完成")
    
    except Exception as e:
        print(f"❌ 錯誤: {e}")


if __name__ == "__main__":
    asyncio.run(test_websocket())
