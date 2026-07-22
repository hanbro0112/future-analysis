import sys
import shioaji as sj
from shioaji import TickFOPv1
import time
import threading
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # 添加 apps 目錄到 Python 路徑
from config import config
from pubsub import PubSubPublisher

# 初始化 Pub/Sub Publisher
pubsub_publisher: PubSubPublisher | None = None

# 全域變數管理會話狀態
api_instance: sj.Shioaji | None = None
target_symbols = ["MXFR1"]
is_reconnecting = False
is_session_active = True  # 會話是否活躍
max_reconnect_attempts = 5
reconnect_delay = 5  # 秒
last_reconnect_time = None  # 上次重連時間


def init_pubsub():
    """初始化 Pub/Sub Publisher"""
    global pubsub_publisher
    
    project_id = config["gcp_project_id"]
    topic_id = config["pubsub_topic_id"]
    
    try:
        pubsub_publisher = PubSubPublisher(project_id=project_id)
        # 等待 topic 建立完成 - ensure_topic_exists() 是同步調用，會等待建立完成
        pubsub_publisher.ensure_topic_exists(topic_id)
        print(f"✅ Pub/Sub 初始化成功，Topic: {topic_id}")
    except Exception as e:
        print(f"⚠️  Pub/Sub 初始化失敗: {e}")
        exit(1)


def is_trading_hours(check_time: datetime | None = None) -> bool:
    """
    判斷是否為交易時段
    
    交易時段：
    - 日盤：週一到週五 8:45-13:45
    - 夜盤：週一到週四 15:00-次日 5:00，週五 15:00-23:59
    
    Args:
        check_time: 要檢查的時間，預設為當前時間
    
    Returns:
        True 如果在交易時段內
    """
    if check_time is None:
        check_time = datetime.now()
    
    weekday = check_time.weekday()  # 0=週一, 6=週日
    hour = check_time.hour
    minute = check_time.minute
    time_minutes = hour * 60 + minute
    
    # 週末不交易
    if weekday >= 5:
        return False
    
    # 日盤：8:45-13:45
    if 8 * 60 + 45 <= time_minutes <= 13 * 60 + 45:
        return True
    
    # 夜盤：15:00-次日 5:00
    # 週一到週四的夜盤可以延續到次日（週二到週五凌晨）
    if weekday <= 3:  # 週一到週四
        if time_minutes >= 15 * 60:  # 15:00 之後（當天夜盤開始）
            return True
        if time_minutes <= 5 * 60:  # 次日 5:00 之前（前一天夜盤延續）
            return True
    
    # 週五處理：
    # - 凌晨 0:00-5:00：週四夜盤的延續
    # - 日盤時段：已在上面處理
    # - 15:00-23:59：週五夜盤（不延續到週六）
    if weekday == 4:  # 週五
        if time_minutes <= 5 * 60:  # 週四夜盤延續到週五凌晨 5:00
            return True
        if time_minutes >= 15 * 60:  # 週五夜盤開始（不延續）
            return True
    
    return False


def quote_callback(tick: TickFOPv1):
    """處理報價回調，推送到 Pub/Sub"""
    print(f"Received tick: {tick}")

    if tick.simtrade:
        print("⚠️  試撮交易資料，跳過處理")
        return
    
    try:
        topic_id = config["pubsub_topic_id"]
        
        # 準備訊息資料 - 展開 tick 物件的各個欄位
        message_data = {
            "code": tick.code,
            "datetime": tick.datetime.isoformat() if tick.datetime else None,
            "open": str(tick.open) if tick.open is not None else None,
            "underlying_price": str(tick.underlying_price) if tick.underlying_price is not None else None,
            "bid_side_total_vol": tick.bid_side_total_vol,
            "ask_side_total_vol": tick.ask_side_total_vol,
            "avg_price": str(tick.avg_price) if tick.avg_price is not None else None,
            "close": str(tick.close) if tick.close is not None else None,
            "high": str(tick.high) if tick.high is not None else None,
            "low": str(tick.low) if tick.low is not None else None,
            "amount": str(tick.amount) if tick.amount is not None else None,
            "total_amount": str(tick.total_amount) if tick.total_amount is not None else None,
            "volume": tick.volume,
            "total_volume": tick.total_volume,
            "tick_type": tick.tick_type,
            "chg_type": tick.chg_type,
            "price_chg": str(tick.price_chg) if tick.price_chg is not None else None,
            "pct_chg": str(tick.pct_chg) if tick.pct_chg is not None else None,
            "simtrade": tick.simtrade,
        }
        
        # 發布到 Pub/Sub
        message_id = pubsub_publisher.publish_message(
            topic_id=topic_id,
            data=message_data,
            source="price-listener"
        )
        print(f"📤 已發布到 Pub/Sub，訊息 ID: {message_id}")
        
    except Exception as e:
        print(f"❌ 發送訊息到 Pub/Sub 失敗: {e}")


def on_session_down(resp_code: int, event_code: int, info: str, event: str):
    """
    處理會話斷線事件
    
    Shioaji 事件回調的參數格式：
    - resp_code: 回應代碼
    - event_code: 事件代碼 (1 = Session down, 其他為其他事件)
    - info: 錯誤訊息
    - event: 事件類型字串
    """
    global is_reconnecting, is_session_active
    
    try:
        # 只處理 Session down 事件 (event_code == 1)
        if event_code != 1:
            print(f"ℹ️  收到事件: {event} (code: {event_code}, resp: {resp_code})")
            return
        
        is_session_active = False
        timestamp = datetime.now()
        
        print(f"\n{'='*60}")
        print(f"⚠️ [{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] 會話斷線事件觸發")
        print(f"{'='*60}")
        print(f"回應代碼: {resp_code}")
        print(f"事件代碼: {event_code}")
        print(f"事件類型: {event}")
        print(f"詳細訊息: {info}")
        print(f"{'='*60}\n")
        
        # 檢查是否在交易時段內
        in_trading_hours = is_trading_hours(timestamp)
        
        if in_trading_hours and not is_reconnecting:
            print("🔴 警告：交易時段內斷線，啟動重新連接...")
            is_reconnecting = True
            # 在單獨的線程中執行重連，避免阻塞事件處理
            reconnect_thread = threading.Thread(target=reconnect, daemon=True)
            reconnect_thread.start()
        else:
            print("ℹ️  盤後時間斷線，將在下次交易時段開始前自動重連")
            print("💤 進入待機模式，等待交易時段...")
            
    except Exception as e:
        print(f"❌ on_session_down 處理錯誤: {e}")
        print(f"   參數: resp_code={resp_code}, event_code={event_code}, event={event}")
        import traceback
        traceback.print_exc()


def on_event_universal(*args, **kwargs):
    """
    通用事件處理器（用於調試）
    接受任意參數格式
    """
    print(f"\n🔍 [調試] 通用事件處理器被觸發")
    print(f"   args: {args}")
    print(f"   kwargs: {kwargs}")
    print(f"   args 數量: {len(args)}")
    
    # 嘗試解析參數
    if len(args) >= 4:
        resp_code, event_code, info, event = args[0], args[1], args[2], args[3]
        on_session_down(resp_code, event_code, info, event)
    elif len(args) == 1:
        # 可能是一個對象
        event_obj = args[0]
        print(f"   事件對象類型: {type(event_obj)}")
        print(f"   事件對象: {event_obj}")
        
        # 嘗試提取屬性
        try:
            if hasattr(event_obj, 'resp_code'):
                on_session_down(
                    event_obj.resp_code,
                    event_obj.event_code,
                    event_obj.info,
                    event_obj.event
                )
            elif isinstance(event_obj, dict):
                on_session_down(
                    event_obj.get('resp_code', 0),
                    event_obj.get('event_code', 0),
                    event_obj.get('info', ''),
                    event_obj.get('event', '')
                )
        except Exception as e:
            print(f"   ❌ 解析事件對象失敗: {e}")
    else:
        print(f"   ⚠️ 無法識別的參數格式")
    print()


def reconnect():
    """執行重連邏輯"""
    global api_instance, is_reconnecting, is_session_active, last_reconnect_time
    
    for attempt in range(1, max_reconnect_attempts + 1):
        try:
            print(f"🔄 第 {attempt}/{max_reconnect_attempts} 次重連嘗試...")
            
            # 清理舊連接
            if api_instance:
                try:
                    print(f"   🔌 正在登出舊連接...")
                    api_instance.logout()
                    print(f"   ✅ 舊連接已登出")
                except Exception as e:
                    print(f"   ⚠️ 登出失敗: {e}")
            
            # 等待一段時間再重連
            print(f"   ⏳ 等待 {reconnect_delay} 秒...")
            time.sleep(reconnect_delay)
            
            # 重新建立連接
            print(f"   🔌 正在重新連接 Shioaji API...")
            api_instance = get_shioaji_client()
            print(f"   ✅ API 連接成功")
            
            # 重新註冊回調函數
            print(f"   📝 註冊報價回調...")
            api_instance.quote.set_on_tick_fop_v1_callback(quote_callback)
            
            # 註冊斷線事件處理
            print(f"   📝 註冊事件回調...")
            api_instance.set_event_callback(on_event_universal)
            
            # 重新訂閱合約
            print(f"   📡 重新訂閱合約...")
            subscribe_contracts(api_instance)
            
            print(f"✅ 第 {attempt} 次重連成功！")
            is_reconnecting = False
            is_session_active = True
            last_reconnect_time = datetime.now()
            return True
            
        except Exception as e:
            print(f"❌ 第 {attempt} 次重連失敗: {e}")
            import traceback
            traceback.print_exc()
            
            if attempt < max_reconnect_attempts:
                wait_time = reconnect_delay * attempt  # 指數退避
                print(f"⏳ 等待 {wait_time} 秒後重試...\n")
                time.sleep(wait_time - reconnect_delay)  # 已經 sleep 過 reconnect_delay
    
    print(f"❌ 重連失敗，已達最大重試次數 ({max_reconnect_attempts})")
    is_reconnecting = False
    is_session_active = False
    return False
    is_session_active = False
    return False


def subscribe_contracts(api: sj.Shioaji):
    """訂閱合約"""
    for code in target_symbols:
        try:
            contract = api.Contracts.Futures[code]
            if contract:
                print(f"📡 正在訂閱 {contract.code} ({contract.name})...")
                api.quote.subscribe(
                    contract, 
                    quote_type=sj.constant.QuoteType.Tick,
                    version=sj.constant.QuoteVersion.v1
                )
                print(f"✅ 訂閱成功: {contract.code}")
            else:
                print(f"❌ 找不到合約: {code}")
        except Exception as e:
            print(f"❌ 訂閱合約 {code} 失敗: {e}")


def check_and_reconnect():
    """
    定期檢查連接狀態，在交易時段內且連接斷開時自動重連
    """
    global is_reconnecting, is_session_active, last_reconnect_time
    
    # 如果正在重連中，跳過
    if is_reconnecting:
        return
    
    # 如果連接正常，跳過
    if is_session_active:
        return
    
    # 檢查是否在交易時段內
    now = datetime.now()
    if not is_trading_hours(now):
        return
    
    # 避免過於頻繁重連（至少間隔 30 秒）
    if last_reconnect_time:
        elapsed = (now - last_reconnect_time).total_seconds()
        if elapsed < 30:
            return
    
    print(f"\n🔔 [{now.strftime('%Y-%m-%d %H:%M:%S')}] 檢測到交易時段且連接已斷開，開始重連...")
    is_reconnecting = True
    reconnect()


def main() -> None:
    global api_instance, is_session_active
    
    init_pubsub()
    
    api_instance = get_shioaji_client()
    is_session_active = True
    
    # 註冊回調函數 - 必須在訂閱之前設定
    print("🔧 註冊報價回調函數...")
    api_instance.quote.set_on_tick_fop_v1_callback(quote_callback)
    
    # 註冊會話斷線事件處理
    print("🔧 註冊會話事件處理器...")
    api_instance.set_event_callback(on_event_universal)
    print("✅ 事件處理器註冊完成（使用通用處理器進行調試）")
    
    # 訂閱合約
    subscribe_contracts(api_instance)
    
    # 顯示交易時段資訊
    now = datetime.now()
    if is_trading_hours(now):
        print(f"\n✅ 當前為交易時段，開始監聽報價...")
    else:
        print(f"\nℹ️  當前為盤後時間，將在交易時段開始時自動監聽報價...")
    
    try:
        print("📌 按 Ctrl+C 退出程式\n")
        check_counter = 0
        while True:
            time.sleep(1)
            check_counter += 1
            
            # 每 60 秒檢查一次連接狀態
            if check_counter >= 60:
                check_counter = 0
                check_and_reconnect()
                
    except KeyboardInterrupt:
        print("\n\n🛑 接收到退出信號...")
        check_usage(api_instance)
        print("👋 正在關閉連接...")
        try:
            api_instance.logout()
            print("✅ 已安全登出")
        except:
            pass


def get_shioaji_client() -> sj.Shioaji:
    """初始化並登入 Shioaji API"""
    api = sj.Shioaji(simulation=True)
    print("🔌 正在連接 Shioaji API...")
    api.login(
        api_key=config["api_key"],
        secret_key=config["secret_key"],
    )
    
    # ca 憑證放在專案根目錄
    project_root = Path(__file__).resolve().parents[4]
    ca_path = str(project_root / config["ca_cert_path"])
    
    api.activate_ca(
        ca_path= ca_path,
        ca_passwd=config["ca_password"]
    )
    print("✅ Shioaji API 登入成功")
    return api


def check_usage(api: sj.Shioaji):
    """檢查 API 使用量並顯示剩餘額度百分比"""
    try:
        # { connections=1, bytes, limit_bytes=500MB, remaining_bytes }
        usage = api.usage()
        
        # 提取 limit_bytes 和 remaining_bytes（物件屬性，不是字典）
        limit_bytes = usage.limit_bytes
        remaining_bytes = usage.remaining_bytes
        
        if limit_bytes > 0:
            # 計算剩餘百分比
            remaining_percentage = (remaining_bytes / limit_bytes) * 100
            used_percentage = 100 - remaining_percentage
            
            # 將 bytes 轉換為 MB 以便閱讀
            limit_mb = limit_bytes / (1024 * 1024)
            remaining_mb = remaining_bytes / (1024 * 1024)
            used_mb = limit_mb - remaining_mb
            
            print(f"📊 API 使用量報告")
            print(f"   已使用: {used_mb:.0f} MB ({used_percentage:.1f}%)")
            print(f"   剩餘額度: {remaining_mb:.0f} MB ({remaining_percentage:.1f}%)\n")
            
            # 根據剩餘百分比顯示警告
            if remaining_percentage < 10:
                print(f"⚠️  警告：剩餘額度不足 10%，請注意流量使用！")
            elif remaining_percentage < 25:
                print(f"⚡ 提醒：剩餘額度低於 25%")
        else:
            print(f"⚠️  無法計算使用量百分比，usage 資料: {usage}")
    except Exception as e:
        print(f"❌ 檢查使用量時發生錯誤: {e}")
        print(f"   原始資料: {usage}")


__all__ = ["main"]
