"""
Price Analyzer - 價格分析服務
接收 Pub/Sub 訊息，計算每分鐘統計資訊並寫入 Firestore
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # 添加 apps 目錄到 Python 路徑

from datetime import datetime, time as datetime_time
from decimal import Decimal
import threading

from config import config
from pubsub import PubSubSubscriber
from firestore_writer import FirestoreWriter
from .strategy import LongShortAnalyzer, TickData
from .minute_aggregator import MinuteAggregator, MinuteBar
from .daily_report import DailyReportGenerator


# ========== 獨立回調函數 ==========

def on_minute_complete(minute_bar: MinuteBar, firestore_writer: FirestoreWriter, analyzer: LongShortAnalyzer):
    """當一分鐘的資料完成時，寫入 Firestore"""
    try:
        # 取得商品代碼（移除合約月份，只保留商品類型）
        # 例如：MXFF6 -> MXF
        code = minute_bar.code[:3] if len(minute_bar.code) >= 3 else minute_bar.code
        
        # 建立 Firestore 路徑：market/{code}/{YYYYMMDD}/{HHMM}
        collection_path = f"market/{code}/{minute_bar.date.replace('-', '')}"
        doc_id = minute_bar.time
        
        # 準備儲存的資料
        save_data = minute_bar.to_dict()
        
        # 加入多空分析結果（如果有）
        # 使用最後一個 tick 的分析結果作為該分鐘的分析
        analysis_result = analyzer.get_latest_analysis()
        if analysis_result:
            save_data['analysis'] = {
                'signal': analysis_result.signal,
                'long_ratio': float(analysis_result.long_ratio),
                'short_ratio': float(analysis_result.short_ratio),
                'confidence': float(analysis_result.confidence),
                'volume_explosion_level': analysis_result.volume_indicator.explosion_level,
                'sentiment_label': analysis_result.sentiment_indicator.sentiment_label,
                'sentiment_score': float(analysis_result.sentiment_indicator.sentiment_score),
                'basis': float(analysis_result.basis_analysis.basis),
                'basis_pct': float(analysis_result.basis_analysis.basis_pct),
            }
        
        # 寫入到 Firestore（使用指定的 document ID）
        firestore_writer.write_document(
            collection=collection_path,
            data=save_data,
            document_id=doc_id
        )
        
        print(f"💾 已儲存分鐘資料: {code}/{minute_bar.date.replace('-', '')}/{doc_id} "
              f"(O:{minute_bar.open} H:{minute_bar.high} L:{minute_bar.low} C:{minute_bar.close} "
              f"V:{minute_bar.volume})\n")
        
    except Exception as e:
        import traceback
        print(f"❌ 儲存分鐘資料時發生錯誤: {type(e).__name__}: {e}")
        print(f"🔍 詳細錯誤:\n{traceback.format_exc()}\n")


def schedule_auto_flush(aggregator: MinuteAggregator, timer_lock: threading.Lock, timer_ref: dict):
    """定時檢查並自動 flush（每 30 秒執行一次）"""
    try:
        aggregator.auto_flush_if_needed(delay_minutes=1.5)
    except Exception as e:
        print(f"⚠️  自動 flush 時發生錯誤: {e}")
    
    # 重新排程下一次檢查
    with timer_lock:
        if timer_ref.get('timer') is not None:  # 確認沒有被取消
            timer = threading.Timer(30.0, lambda: schedule_auto_flush(aggregator, timer_lock, timer_ref))
            timer.daemon = True
            timer.start()
            timer_ref['timer'] = timer


def generate_and_save_report(report_generator: DailyReportGenerator, firestore_writer: FirestoreWriter, 
                            timer_lock: threading.Lock, timer_ref: dict):
    """生成並儲存每日報告"""
    try:
        if report_generator is None:
            print("⚠️  每日報告生成器未初始化，跳過報告生成")
            schedule_daily_report(report_generator, firestore_writer, timer_lock, timer_ref)
            return
        
        now = datetime.now()
        
        # 檢查是否為交易日
        if not report_generator.is_trading_day(now):
            print(f"⏸️  {now.strftime('%Y-%m-%d')} 不是交易日，跳過報告生成")
            schedule_daily_report(report_generator, firestore_writer, timer_lock, timer_ref)
            return
        
        print(f"\n{'='*60}")
        print(f"📊 開始生成每日報告 - {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")
        
        # 生成報告
        report_data = report_generator.generate_report(now)
        
        # 儲存到 Firestore
        report_generator.save_report(report_data, firestore_writer)
        
        print(f"{'='*60}")
        print(f"✅ 每日報告生成完成")
        print(f"{'='*60}\n")
        
    except Exception as e:
        import traceback
        print(f"❌ 生成每日報告時發生錯誤: {e}")
        print(f"🔍 詳細錯誤:\n{traceback.format_exc()}\n")
    
    finally:
        # 重新排程下一次執行
        schedule_daily_report(report_generator, firestore_writer, timer_lock, timer_ref)


def schedule_daily_report(report_generator: DailyReportGenerator, firestore_writer: FirestoreWriter,
                         timer_lock: threading.Lock, timer_ref: dict):
    """定時檢查並生成每日報告（每天 8:00 執行）"""
    try:
        now = datetime.now()
        target_time = datetime.combine(now.date(), datetime_time(8, 0))  # 今天 8:00
        
        # 如果已經過了今天的 8:00，計算明天 8:00 的秒數
        if now >= target_time:
            target_time = datetime.combine(now.date(), datetime_time(8, 0))
            from datetime import timedelta
            target_time += timedelta(days=1)
        
        # 計算距離下次執行的秒數
        seconds_until_target = (target_time - now).total_seconds()
        
        # 設定定時器
        with timer_lock:
            if timer_ref.get('timer') is not None:  # 確認沒有被取消
                timer = threading.Timer(
                    seconds_until_target, 
                    lambda: generate_and_save_report(report_generator, firestore_writer, timer_lock, timer_ref)
                )
                timer.daemon = True
                timer.start()
                timer_ref['timer'] = timer
                
                next_run_time = target_time.strftime('%Y-%m-%d %H:%M:%S')
                print(f"📅 下次每日報告生成時間: {next_run_time}")
        
    except Exception as e:
        print(f"⚠️  排程每日報告時發生錯誤: {e}")


def handle_message(data: dict, analyzer: LongShortAnalyzer, aggregator: MinuteAggregator):
    """處理接收到的 tick 訊息，加入分鐘聚合器"""
    # 驗證必要欄位
    required_fields = ['code', 'close', 'volume']
    missing_fields = [field for field in required_fields if field not in data or data[field] is None]
    
    if missing_fields:
        print(f"⚠️  跳過無效資料：缺少必要欄位 {missing_fields}")
        return
    
    # 驗證數值有效性
    if data.get('close') == 0 or data.get('volume') == 0:
        print(f"⚠️  跳過無效資料：價格或成交量為 0")
        return
    
    print(f"📊 收到 Tick: {data.get('code', 'N/A')} @ {data.get('close', 'N/A')}")
    
    try:
        # 轉換為 TickData 物件
        tick = dict_to_tick(data)
        
        # 執行多空比分析（保留在記憶體中）
        analysis_result = analyzer.analyze(tick)
        
        if analysis_result:
            # 顯示即時分析結果（包含視窗統計）
            window_1m = analysis_result.window_1min
            print(f"   🎯 {analysis_result.signal} | "
                  f"多:{analysis_result.long_ratio:.1f}% 空:{analysis_result.short_ratio:.1f}% | "
                  f"買:{window_1m.buy_volume} 賣:{window_1m.sell_volume} ")
        
        # 加入分鐘聚合器
        completed_bar = aggregator.add_tick(tick)
        # completed_bar 會在回調函數中自動處理
        
    except Exception as e:
        import traceback
        print(f"❌ 處理資料時發生錯誤: {type(e).__name__}: {e}")
        print(f"🔍 詳細錯誤:\n{traceback.format_exc()}\n")


# ========== 工具函數 ==========

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
    """Price Analyzer 主程式"""
    # 定時器控制（使用字典來保持可變引用）
    flush_timer_ref = {'timer': None}
    daily_report_timer_ref = {'timer': None}
    timer_lock = threading.Lock()
    
    try:
        # 初始化 Firestore Writer
        firestore_writer = FirestoreWriter(
            project_id=config['gcp_project_id']
        )

        # 初始化每日報告生成器
        report_generator = DailyReportGenerator()
        
        # 初始化多空比分析器
        analyzer = LongShortAnalyzer()
        
        # 初始化分鐘聚合器（使用 lambda 綁定參數）
        aggregator = MinuteAggregator(
            on_minute_complete=lambda bar: on_minute_complete(bar, firestore_writer, analyzer)
        )
        
        # 取得 Pub/Sub 配置
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

        # 啟動每日報告定時器
        if report_generator is not None:
            with timer_lock:
                daily_report_timer_ref['timer'] = threading.Timer(
                    1.0,
                    lambda: schedule_daily_report(report_generator, firestore_writer, timer_lock, daily_report_timer_ref)
                )
                daily_report_timer_ref['timer'].daemon = True
                daily_report_timer_ref['timer'].start()
            print("📅 每日報告定時器已啟動（每天 8:00 執行）\n")
        
        # 啟動自動 flush 定時器
        with timer_lock:
            flush_timer_ref['timer'] = threading.Timer(
                30.0, 
                lambda: schedule_auto_flush(aggregator, timer_lock, flush_timer_ref)
            )
            flush_timer_ref['timer'].daemon = True
            flush_timer_ref['timer'].start()
            print("⏰ 自動 flush 定時器已啟動（每 30 秒檢查一次）\n")
            
        
        # 開始訂閱（阻塞式運行）
        print("🚀 Price Analyzer 已啟動（分鐘級聚合模式）\n")
        print("📊 資料結構：market/{商品代碼}/{YYYYMMDD}/{HHMM}\n")
        
        # 訂閱訊息（使用 lambda 綁定參數）
        subscriber.subscribe(
            callback=lambda data: handle_message(data, analyzer, aggregator)
        )
        
    except KeyboardInterrupt:
        print("\n\n👋 正在停止服務...")
        # 停止定時器
        with timer_lock:
            if flush_timer_ref.get('timer') is not None:
                flush_timer_ref['timer'].cancel()
                flush_timer_ref['timer'] = None
            if daily_report_timer_ref.get('timer') is not None:
                daily_report_timer_ref['timer'].cancel()
                daily_report_timer_ref['timer'] = None
        # 強制完成所有未完成的分鐘資料
        if 'aggregator' in locals():
            print("📦 正在完成剩餘的分鐘資料...")
            aggregator.flush_all()
    except Exception as e:
        print(f"\n❌ 發生錯誤: {e}")
        sys.exit(1)
    finally:
        # 清理定時器
        with timer_lock:
            if flush_timer_ref.get('timer') is not None:
                flush_timer_ref['timer'].cancel()
            if daily_report_timer_ref.get('timer') is not None:
                daily_report_timer_ref['timer'].cancel()
        # 清理資源
        if 'firestore_writer' in locals():
            firestore_writer.close()
        if 'subscriber' in locals():
            subscriber.close()
        print("✨ 服務已停止")


__all__ = ["main"]