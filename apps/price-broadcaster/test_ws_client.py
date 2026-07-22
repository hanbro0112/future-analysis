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
            print("✅ WebSocket 連接成功\n")
            
            # 接收訊息
            for i in range(10):  # 接收 10 次報價
                message = await websocket.recv()
                data = json.loads(message)
                
                print(f"📊 收到報價 #{i+1}:")
                print(f"   時間: {data['timestamp']}")
                
                # 顯示每個商品的詳細報價資訊
                if data.get('data'):
                    for code, price_info in data['data'].items():
                        if isinstance(price_info, dict):
                            print(f"   {code}:")
                            print(f"      成交價: {price_info.get('price', 'N/A')}")
                            print(f"      加權指數: {price_info.get('underlying_price', 'N/A')}")
                            print(f"      每秒成交量: {price_info.get('volume', 'N/A')}")
                        else:
                            # 相容舊格式（單純的價格）
                            print(f"   {code}: {price_info}")
                print()
                
                # 發送心跳
                await websocket.send("ping")
            
            print("✨ 測試完成")
    
    except Exception as e:
        print(f"❌ 錯誤: {e}")


if __name__ == "__main__":
    asyncio.run(test_websocket())
