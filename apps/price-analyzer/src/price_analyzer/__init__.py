"""
Price Analyzer - 價格分析服務
接收 Pub/Sub 訊息並寫入 Firestore
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # 添加 apps 目錄到 Python 路徑

from datetime import datetime
from decimal import Decimal

from config import config
from pubsub import PubSubSubscriber
from firestore_writer import FirestoreWriter
from .strategy import LongShortAnalyzer, TickData


def dict_to_tick(data: dict) -> TickData:
    """將字典資料轉換為 TickData 物件"""
    # 處理 datetime 欄位
    dt = data.get('datetime')
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    elif not isinstance(dt, datetime):
        dt = datetime.now()
    
    # 處理 Decimal 欄位
    def to_decimal(value, default='0'):
        if value is None:
            return Decimal(default)
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
    
    return TickData(
        code=data.get('code', 'UNKNOWN'),
        datetime=dt,
        open=to_decimal(data.get('open')),
        underlying_price=to_decimal(data.get('underlying_price')),
        bid_side_total_vol=int(data.get('bid_side_total_vol', 0)),
        ask_side_total_vol=int(data.get('ask_side_total_vol', 0)),
        avg_price=to_decimal(data.get('avg_price')),
        close=to_decimal(data.get('close')),
        high=to_decimal(data.get('high')),
        low=to_decimal(data.get('low')),
        amount=to_decimal(data.get('amount')),
        total_amount=to_decimal(data.get('total_amount')),
        volume=int(data.get('volume', 0)),
        total_volume=int(data.get('total_volume', 0)),
        tick_type=int(data.get('tick_type', 0)),
        chg_type=int(data.get('chg_type', 0)),
        price_chg=to_decimal(data.get('price_chg')),
        pct_chg=to_decimal(data.get('pct_chg')),
        simtrade=bool(data.get('simtrade', False)),
    )


def main():
    try:
        # 初始化 Firestore Writer
        firestore_writer = FirestoreWriter(
            project_id=config['gcp_project_id']
        )
        
        # 初始化多空比分析器
        analyzer = LongShortAnalyzer()
        
        topic_id = config['pubsub_topic_id']
        subscription_id = config['pubsub_subscription_id']
        project_id = config['gcp_project_id']
        
        # 確保 Topic 存在（若無則自動創建）
        from google.cloud.pubsub_v1 import PublisherClient, SubscriberClient
        publisher_client = PublisherClient()
        topic_path = publisher_client.topic_path(project_id, topic_id)
        
        try:
            publisher_client.get_topic(request={"topic": topic_path})
            print(f"✅ Topic 已存在: {topic_id}")
        except Exception:
            publisher_client.create_topic(request={"name": topic_path})
            print(f"✅ Topic 已創建: {topic_id}")
        
        # 確保 Subscription 存在並綁定到 Topic
        subscriber_client = SubscriberClient()
        subscription_path = subscriber_client.subscription_path(project_id, subscription_id)
        topic_path = f"projects/{project_id}/topics/{topic_id}"
        
        try:
            subscriber_client.get_subscription(request={"subscription": subscription_path})
            print(f"✅ Subscription 已存在: {subscription_id}")
        except Exception:
            try:
                subscriber_client.create_subscription(
                    request={"name": subscription_path, "topic": topic_path}
                )   
                print(f"✅ Subscription 已創建並綁定到 Topic: {subscription_id} -> {topic_id}")
            except Exception as e:
                print(f"⚠️  創建 Subscription 失敗: {e}")
        
        # 初始化 Pub/Sub Subscriber
        subscriber = PubSubSubscriber(
            project_id=project_id,
            subscription_id=subscription_id
        )
        
        # 定義訊息處理函數
        def handle_message(data: dict):
            """處理接收到的訊息並寫入 Firestore"""

             # 驗證必要欄位
            required_fields = ['code', 'close', 'volume']
            missing_fields = [field for field in required_fields if field not in data or data[field] is None]
            
            if missing_fields:
                print(f"⚠️  跳過無效資料：缺少必要欄位 {missing_fields}")
                print(f"📄 收到的資料: {data}\n")
                return
            
            # 驗證數值有效性
            if data.get('close') == 0 or data.get('volume') == 0:
                print(f"⚠️  跳過無效資料：價格或成交量為 0")
                print(f"📄 收到的資料: {data}\n")
                return
            
            print(f"📊 收到 Tick 資料: {data.get('code', 'N/A')} @ {data.get('close', 'N/A')}")
            
            try:
                # 轉換為 TickData 物件
                tick = dict_to_tick(data)
                
                # 執行多空比分析
                analysis_result = analyzer.analyze(tick)
                
                if analysis_result:
                    # 顯示分析結果（簡化版）
                    print(f"🎯 {analysis_result.signal} | "
                          f"多:{analysis_result.long_ratio:.1f}% 空:{analysis_result.short_ratio:.1f}% | "
                          f"期現差:{analysis_result.basis_analysis.basis:+} "
                          f"({analysis_result.basis_analysis.basis_pct:+.2f}%) | "
                          f"量:{analysis_result.volume_indicator.explosion_level} | "
                          f"情緒:{analysis_result.sentiment_indicator.sentiment_label}")
                    
                    # 每10筆 Tick 顯示一次詳細分析
                    if analysis_result.window_1min.tick_count % 10 == 0:
                        print("\n" + analyzer.format_analysis(analysis_result))
                    
                    # 準備儲存的資料（包含原始資料和分析結果）
                    save_data = {
                        'tick': data,
                        'analysis': {
                            'timestamp': analysis_result.timestamp.isoformat(),
                            'signal': analysis_result.signal,
                            'long_ratio': float(analysis_result.long_ratio),
                            'short_ratio': float(analysis_result.short_ratio),
                            'confidence': float(analysis_result.confidence),
                            'windows': {
                                '1min': {
                                    'buy_volume': analysis_result.window_1min.buy_volume,
                                    'sell_volume': analysis_result.window_1min.sell_volume,
                                    'total_volume': analysis_result.window_1min.total_volume,
                                    'price_change_pct': analysis_result.window_1min.price_change_pct,
                                },
                                '5min': {
                                    'buy_volume': analysis_result.window_5min.buy_volume,
                                    'sell_volume': analysis_result.window_5min.sell_volume,
                                    'total_volume': analysis_result.window_5min.total_volume,
                                    'price_change_pct': analysis_result.window_5min.price_change_pct,
                                },
                                '30min': {
                                    'buy_volume': analysis_result.window_30min.buy_volume,
                                    'sell_volume': analysis_result.window_30min.sell_volume,
                                    'total_volume': analysis_result.window_30min.total_volume,
                                    'price_change_pct': analysis_result.window_30min.price_change_pct,
                                },
                            },
                            'volume_explosion': {
                                'current': analysis_result.volume_indicator.current_volume,
                                'avg_today': float(analysis_result.volume_indicator.avg_volume_today),
                                'ratio': float(analysis_result.volume_indicator.explosion_ratio),
                                'level': analysis_result.volume_indicator.explosion_level,
                            },
                            'basis': {
                                'futures_price': str(analysis_result.basis_analysis.futures_price),
                                'spot_price': str(analysis_result.basis_analysis.spot_price),
                                'basis': str(analysis_result.basis_analysis.basis),
                                'basis_pct': float(analysis_result.basis_analysis.basis_pct),
                                'signal': analysis_result.basis_analysis.trend_signal,
                            },
                            'sentiment': {
                                'score': float(analysis_result.sentiment_indicator.sentiment_score),
                                'label': analysis_result.sentiment_indicator.sentiment_label,
                                'bid_ask_ratio': float(analysis_result.sentiment_indicator.bid_ask_ratio),
                                'bid_ask_signal': analysis_result.sentiment_indicator.bid_ask_signal,
                                'continuous_direction': analysis_result.sentiment_indicator.continuous_direction,
                                'momentum_score': float(analysis_result.sentiment_indicator.momentum_score),
                                'volatility_level': analysis_result.sentiment_indicator.volatility_level,
                                'is_bullish': analysis_result.sentiment_indicator.is_bullish,
                                'is_bearish': analysis_result.sentiment_indicator.is_bearish,
                            },
                        }
                    }
                else:
                    # 沒有分析結果時只儲存原始資料
                    save_data = {'tick': data}
                
                # 寫入到 Firestore
                doc_id = firestore_writer.write_document(
                    collection='price_analysis',
                    data=save_data
                )
                print(f"💾 已儲存到 Firestore: {doc_id}\n")
                
            except Exception as e:
                import traceback
                print(f"❌ 處理資料時發生錯誤: {type(e).__name__}: {e}")
                print(f"📄 收到的資料: {data}")
                print(f"🔍 詳細錯誤:\n{traceback.format_exc()}\n")
                # 不 raise，讓訊息可以被標記為失敗並繼續處理下一個訊息
        
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


__all__ = ["main"]