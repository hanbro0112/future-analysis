import os
import signal
import sys
import shioaji as sj
from shioaji import TickFOPv1
import time
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # 添加 apps 目錄到 Python 路徑
from config import config
from pubsub import PubSubPublisher
from trading_calendar import ActiveWindow, ShouldContinue, is_session_open, run_session_loop

TAIPEI_TZ = ZoneInfo("Asia/Taipei")

# 開盤前 5 分鐘就緒（登入與下載合約清單需要時間），收盤後 1 分鐘才登出，讓最後的 tick 送完
ACTIVE_WINDOW = ActiveWindow(warmup=timedelta(minutes=5), grace=timedelta(minutes=1))

# 正式交易時段內超過這麼久沒收到 tick，視為連線停滯（連線與訂閱旗標都正常、但資料不來）
TICK_STALE_SECONDS = 120.0

# logout 可能卡住，超過這個秒數就放棄等待，避免時段迴圈被拖住
LOGOUT_TIMEOUT_SECONDS = 10.0

_ZERO_PUBLISH_STATS: dict[str, int] = {"published": 0, "failed": 0, "dropped": 0}


def now_taipei() -> datetime:
    """
    取得目前台北時間（naive datetime，不帶 tzinfo）。

    容器內部時鐘預設為 UTC，交易時段判斷與重連時間紀錄都需以台北時間為準，
    否則斷線時可能誤判為「非交易時段」而不重連。
    """
    return datetime.now(TAIPEI_TZ).replace(tzinfo=None)

# 初始化 Pub/Sub Publisher
pubsub_publisher: PubSubPublisher | None = None

# 全域變數管理會話狀態
api_instance: sj.Shioaji | None = None
target_symbols = ["MXFR1"]
is_reconnecting = False
is_session_active = True  # 會話是否活躍
is_subscribed = False  # 合約是否已成功訂閱（登入成功但合約清單尚未下載完成時會是 False）
is_stopping = False  # 本時段正在收尾，重連流程看到後要放棄
max_reconnect_attempts = 5
reconnect_delay = 5  # 秒
last_reconnect_time = None  # 上次重連 / 重新訂閱時間
reconnect_thread: threading.Thread | None = None

# 最後一次收到正式 tick 的時間（time.monotonic()）。由報價回調執行緒寫入、主迴圈讀取，
# 單一變數賦值不可分割，不需要 Lock；訂閱成功時也會重設為基準，避免剛訂閱就被誤判停滯
last_tick_time: float = time.monotonic()
watchdog_resubscribed = False  # 看門狗已用「重新訂閱」處理過一次，仍無 tick 才升級為重連
_prev_publish_stats: dict[str, int] = dict(_ZERO_PUBLISH_STATS)  # 上次心跳的發布統計，用來算差值

# 收到 SIGTERM 時設定，讓每分鐘判斷的迴圈與目前時段一起結束
stop_event = threading.Event()


def create_publisher() -> PubSubPublisher:
    """建立非同步模式的 Publisher 並確認 topic 存在；失敗時釋放剛建立的 publisher 並拋出例外"""
    topic_id = config["pubsub_topic_id"]

    # async_mode：報價回調改用非同步發布，topic 只在建立時確認一次
    publisher = PubSubPublisher(project_id=config["gcp_project_id"], async_mode=True)
    try:
        # 等待 topic 建立完成 - ensure_topic_exists() 是同步調用，會等待建立完成
        publisher.ensure_topic_exists(topic_id)
    except Exception:
        try:
            publisher.close()
        except Exception as close_error:
            print(f"⚠️  釋放未完成初始化的 Publisher 失敗: {close_error}")
        raise
    return publisher


def init_pubsub() -> None:
    """初始化 Pub/Sub Publisher；失敗時拋出例外，由時段迴圈在下一輪重試"""
    global pubsub_publisher

    try:
        pubsub_publisher = create_publisher()
        print(f"✅ Pub/Sub 初始化成功，Topic: {config['pubsub_topic_id']}")
    except Exception as e:
        print(f"⚠️  Pub/Sub 初始化失敗: {e}")
        raise


def quote_callback(tick: TickFOPv1):
    """處理報價回調，推送到 Pub/Sub"""
    global last_tick_time
    # print(f"Received tick: {tick}")

    if tick.simtrade:
        # print("⚠️  試撮交易資料，跳過處理")
        return

    # 收到正式 tick 就代表連線有資料在流動（看門狗以此判斷是否停滯）
    last_tick_time = time.monotonic()

    # 收尾後 Shioaji 可能還有殘留的 tick 回調，此時 publisher 已釋放；
    # 只讀一次全域變數，避免健康檢查換掉 publisher 時前後讀到不同物件
    publisher = pubsub_publisher
    if publisher is None:
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
        
        # 非同步發布到 Pub/Sub：只交給批次佇列就返回，不阻塞 Shioaji 回調執行緒；
        # 送達結果與失敗由 publisher 內部統計（見 PubSubPublisher.get_publish_stats）
        publisher.publish_message_async(
            topic_id=topic_id,
            data=message_data,
            source="price-listener"
        )

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
    global is_reconnecting, is_session_active, reconnect_thread

    try:
        # 只處理 Session down 事件 (event_code == 1)
        if event_code != 1:
            print(f"ℹ️  收到事件: {event} (code: {event_code}, resp: {resp_code})")
            return

        timestamp = now_taipei()

        print(f"\n{'='*60}")
        print(f"⚠️ [{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] 會話斷線事件觸發")
        print(f"{'='*60}")
        print(f"回應代碼: {resp_code}")
        print(f"事件代碼: {event_code}")
        print(f"事件類型: {event}")
        print(f"詳細訊息: {info}")
        print(f"{'='*60}\n")

        # 重連或收尾時我們自己會登出舊連線，它觸發的斷線事件不代表目前連線的狀態
        if is_reconnecting or is_stopping:
            print("ℹ️  正在重連或收尾中，忽略此斷線事件")
            return

        is_session_active = False

        if ACTIVE_WINDOW.contains(timestamp):
            print("🔴 警告：啟用時段內斷線，啟動重新連接...")
            is_reconnecting = True
            # 在單獨的線程中執行重連，避免阻塞事件處理
            reconnect_thread = threading.Thread(target=reconnect, daemon=True)
            reconnect_thread.start()
        else:
            print("ℹ️  不在啟用時段，不重連（下個時段會重新登入）")

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


def make_event_callback(api: sj.Shioaji) -> Callable[..., None]:
    """建立綁定特定連線的事件回調；已被重連取代的舊連線所觸發的事件會被忽略"""
    def callback(*args: object, **kwargs: object) -> None:
        if api is not api_instance:
            print("ℹ️  忽略已被取代的舊連線事件")
            return
        on_event_universal(*args, **kwargs)

    return callback


def call_with_timeout(func: Callable[[], object], timeout: float, label: str) -> bool:
    """
    在背景 daemon 執行緒執行 func，最多等 timeout 秒。

    Shioaji 的阻塞呼叫沒有 timeout，卡住會拖住單一執行緒的時段迴圈；
    超時只是放棄等待（執行緒留在背景，不會阻擋行程結束）。

    Returns:
        True 代表在時限內正常完成；超時或拋出例外都回傳 False 並記錄
    """
    errors: list[Exception] = []

    def runner() -> None:
        try:
            func()
        except Exception as e:
            errors.append(e)

    worker = threading.Thread(target=runner, name=f"timeout-{label}", daemon=True)
    worker.start()
    worker.join(timeout)

    if worker.is_alive():
        print(f"⚠️  {label}超過 {timeout:.0f} 秒未完成，放棄等待")
        return False
    if errors:
        print(f"⚠️  {label}失敗: {errors[0]}")
        return False
    return True


def safe_logout(api: sj.Shioaji) -> bool:
    """登出 Shioaji；最多等 LOGOUT_TIMEOUT_SECONDS 秒，失敗或超時都不拋例外"""
    return call_with_timeout(api.logout, LOGOUT_TIMEOUT_SECONDS, "登出")


def reconnect():
    """執行重連邏輯"""
    global api_instance, is_reconnecting, is_session_active, is_subscribed, last_reconnect_time

    for attempt in range(1, max_reconnect_attempts + 1):
        if is_stopping or stop_event.is_set():
            print("🛑 服務收尾中，放棄重連")
            is_reconnecting = False
            return False

        try:
            print(f"🔄 第 {attempt}/{max_reconnect_attempts} 次重連嘗試...")
            
            # 清理舊連接
            if api_instance:
                print(f"   🔌 正在登出舊連接...")
                if safe_logout(api_instance):
                    print(f"   ✅ 舊連接已登出")

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
            api_instance.set_event_callback(make_event_callback(api_instance))

            # 重新訂閱合約
            print(f"   📡 重新訂閱合約...")
            is_subscribed = subscribe_contracts(api_instance)
            if not is_subscribed:
                raise RuntimeError(f"合約訂閱失敗: {target_symbols}")

            print(f"✅ 第 {attempt} 次重連成功！")
            is_reconnecting = False
            is_session_active = True
            last_reconnect_time = now_taipei()
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


def subscribe_contracts(api: sj.Shioaji, max_attempts: int = 3, retry_delay: int = 5) -> bool:
    """
    訂閱合約，回傳是否全部訂閱成功。

    登入後 Shioaji 合約清單是背景下載的，剛登入時查詢可能會拿到
    'Contract not found'，因此查詢合約本身也需要重試幾次。

    Returns:
        True 代表 target_symbols 全部訂閱成功
    """
    all_success = True

    for code in target_symbols:
        contract = None
        for attempt in range(1, max_attempts + 1):
            try:
                contract = api.Contracts.Futures[code]
            except Exception as e:
                print(f"⚠️ 查詢合約 {code} 失敗（第 {attempt}/{max_attempts} 次）: {e}")
                contract = None

            if contract:
                break

            if attempt < max_attempts:
                print(f"⚠️ 尚未取得合約 {code}（第 {attempt}/{max_attempts} 次），{retry_delay} 秒後重試...")
                time.sleep(retry_delay)

        if not contract:
            print(f"❌ 找不到合約: {code}，已達最大重試次數")
            all_success = False
            continue

        try:
            print(f"📡 正在訂閱 {contract.code} ({contract.name})...")
            api.quote.subscribe(
                contract,
                quote_type=sj.constant.QuoteType.Tick,
                version=sj.constant.QuoteVersion.v1
            )
            print(f"✅ 訂閱成功: {contract.code}")
        except Exception as e:
            print(f"❌ 訂閱合約 {code} 失敗: {e}")
            all_success = False

    if all_success:
        reset_tick_baseline()

    return all_success


def reset_tick_baseline() -> None:
    """把「最後 tick 時間」重設為現在：剛（重新）訂閱完成，停滯時間從此刻重新計算"""
    global last_tick_time
    last_tick_time = time.monotonic()


def resubscribe_contracts(api: sj.Shioaji) -> bool:
    """
    先取消再重新訂閱。已訂閱的合約直接再訂閱可能被 Shioaji 視為重複而不處理，
    所以先嘗試取消；取消失敗（例如本來就沒有訂閱）不影響後續訂閱。
    """
    for code in target_symbols:
        try:
            contract = api.Contracts.Futures[code]
            api.quote.unsubscribe(
                contract,
                quote_type=sj.constant.QuoteType.Tick,
                version=sj.constant.QuoteVersion.v1
            )
        except Exception as e:
            print(f"⚠️ 取消訂閱 {code} 失敗（仍會嘗試重新訂閱）: {e}")

    return subscribe_contracts(api)


def is_tick_stale(now: datetime, tick_age_seconds: float, threshold: float = TICK_STALE_SECONDS) -> bool:
    """
    判斷報價是否停滯：距最後 tick 超過 threshold，且「現在」與「threshold 秒前」都在正式交易時段內。

    開盤前預熱、休市與收盤寬限期本來就沒有正式 tick（試撮會被過濾），不能算停滯；
    要求 threshold 秒前已開盤，是為了避免剛開盤、第一筆 tick 還沒到就被誤判。

    Args:
        now: 目前台北時間（naive）
        tick_age_seconds: 距最後一次收到 tick（或訂閱基準）的秒數
        threshold: 停滯門檻秒數
    """
    if tick_age_seconds <= threshold:
        return False

    return is_session_open(now) and is_session_open(now - timedelta(seconds=threshold))


def check_tick_watchdog(now: datetime) -> None:
    """
    tick 看門狗：連線與訂閱旗標都正常、但交易時段內持續沒有 tick 時自動修復。

    第一次先重新訂閱；重新訂閱後仍沒有 tick 才升級為重新登入。收到 tick 就重置。
    """
    global is_reconnecting, is_subscribed, last_reconnect_time, watchdog_resubscribed

    tick_age = time.monotonic() - last_tick_time
    if not is_tick_stale(now, tick_age):
        watchdog_resubscribed = False
        return

    if not watchdog_resubscribed:
        print(f"\n🐕 [{now.strftime('%Y-%m-%d %H:%M:%S')}] 交易時段內已 {tick_age:.0f} 秒沒有收到 tick，重新訂閱...")
        watchdog_resubscribed = True
        last_reconnect_time = now
        is_subscribed = resubscribe_contracts(api_instance)
        return

    print(f"\n🐕 [{now.strftime('%Y-%m-%d %H:%M:%S')}] 重新訂閱後仍已 {tick_age:.0f} 秒沒有 tick，重新登入...")
    watchdog_resubscribed = False
    is_reconnecting = True
    reconnect()


def take_publish_stats_delta() -> dict[str, int] | None:
    """取得自上次呼叫以來的發布統計差值（published / failed / dropped）；publisher 已釋放時回傳 None"""
    global _prev_publish_stats

    publisher = pubsub_publisher
    if publisher is None:
        return None

    current = publisher.get_publish_stats()
    delta = {key: current[key] - _prev_publish_stats.get(key, 0) for key in current}
    _prev_publish_stats = dict(current)
    return delta


def format_heartbeat(delta: dict[str, int], tick_age_seconds: float) -> str:
    """產生每分鐘心跳 log：tick 數就是進到發布流程的筆數（成功 + 失敗 + 丟棄）"""
    total = delta["published"] + delta["failed"] + delta["dropped"]
    return (
        f"💓 心跳｜近 1 分鐘 tick {total} 筆（發布成功 {delta['published']} / "
        f"失敗 {delta['failed']} / 丟棄 {delta['dropped']}）｜距最後 tick {tick_age_seconds:.0f} 秒"
    )


def should_rebuild_publisher(delta: dict[str, int]) -> bool:
    """這段期間完全沒有發布成功、卻有失敗或丟棄：代表 publisher 已壞（topic 被刪、憑證失效等）"""
    return delta["published"] == 0 and (delta["failed"] + delta["dropped"]) > 0


def rebuild_publisher() -> bool:
    """
    重建 Publisher 並換掉全域實例，成功後才關閉舊的（舊的關閉時會先送完佇列中的訊息）。

    重建失敗時保留舊 publisher，等下一次健康檢查再試。
    """
    global pubsub_publisher, _prev_publish_stats

    try:
        new_publisher = create_publisher()
    except Exception as e:
        print(f"❌ 重建 Pub/Sub Publisher 失敗，保留舊的: {e}")
        return False

    old_publisher = pubsub_publisher
    pubsub_publisher = new_publisher
    _prev_publish_stats = dict(_ZERO_PUBLISH_STATS)
    print("✅ Pub/Sub Publisher 已重建")

    if old_publisher is not None:
        try:
            old_publisher.close()
        except Exception as e:
            print(f"⚠️  關閉舊 Pub/Sub Publisher 失敗: {e}")
    return True


def run_health_checks() -> None:
    """每分鐘執行：印心跳、發布層自癒、檢查連線與訂閱狀態（含 tick 看門狗）"""
    try:
        delta = take_publish_stats_delta()
        if delta is not None:
            print(format_heartbeat(delta, time.monotonic() - last_tick_time))
            if should_rebuild_publisher(delta):
                print("🔴 近 1 分鐘沒有任何發布成功、卻有失敗或丟棄，重建 Pub/Sub Publisher...")
                rebuild_publisher()
    except Exception as e:
        # 心跳與自癒只是輔助，出錯不能影響後面的連線檢查
        print(f"⚠️  心跳 / 發布層檢查失敗: {e}")

    check_and_reconnect()


def check_and_reconnect():
    """
    定期檢查連接與訂閱狀態，在啟用時段內（含開盤前預熱）自動修復：
    - 連接已斷開：重新登入並訂閱（reconnect）
    - 已登入但合約訂閱失敗（例如冷啟動時合約清單還沒下載完成）：重新訂閱
    """
    global is_reconnecting, is_session_active, is_subscribed, last_reconnect_time

    # 如果正在重連或收尾中，跳過
    if is_reconnecting or is_stopping:
        return

    # 檢查是否在啟用時段內
    now = now_taipei()
    if not ACTIVE_WINDOW.contains(now):
        return

    # 避免過於頻繁重試（至少間隔 30 秒）
    if last_reconnect_time:
        elapsed = (now - last_reconnect_time).total_seconds()
        if elapsed < 30:
            return

    # 已登入但合約未訂閱成功：重新訂閱，不需要整個重新登入
    if is_session_active and not is_subscribed:
        print(f"\n🔔 [{now.strftime('%Y-%m-%d %H:%M:%S')}] 偵測到啟用時段內合約尚未訂閱成功，重新訂閱...")
        last_reconnect_time = now
        is_subscribed = subscribe_contracts(api_instance)
        return

    # 連接正常且已訂閱：旗標無法反映「連線停滯、沒有 tick」，由看門狗以最後 tick 時間判斷
    if is_session_active:
        check_tick_watchdog(now)
        return

    print(f"\n🔔 [{now.strftime('%Y-%m-%d %H:%M:%S')}] 檢測到啟用時段且連接已斷開，開始重連...")
    is_reconnecting = True
    reconnect()


class _HealthCheckHandler(BaseHTTPRequestHandler):
    """Cloud Run 健康檢查用，固定回應 200"""

    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


def _start_health_check_server() -> None:
    """在背景 thread 啟動極簡 HTTP server，讓 Cloud Run 判定服務為 healthy"""
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), _HealthCheckHandler)
    server.serve_forever()


def start_listener_session() -> None:
    """建立全新的 Pub/Sub 與 Shioaji 連線並訂閱合約（每個交易時段各一次）"""
    global api_instance, is_session_active, is_subscribed, is_reconnecting, is_stopping, last_reconnect_time
    global watchdog_resubscribed, _prev_publish_stats

    is_stopping = False
    is_reconnecting = False
    last_reconnect_time = None
    watchdog_resubscribed = False
    _prev_publish_stats = dict(_ZERO_PUBLISH_STATS)
    reset_tick_baseline()

    init_pubsub()

    api_instance = get_shioaji_client()
    is_session_active = True

    # 註冊回調函數 - 必須在訂閱之前設定
    print("🔧 註冊報價回調函數...")
    api_instance.quote.set_on_tick_fop_v1_callback(quote_callback)

    # 註冊會話斷線事件處理
    print("🔧 註冊會話事件處理器...")
    api_instance.set_event_callback(make_event_callback(api_instance))
    print("✅ 事件處理器註冊完成（使用通用處理器進行調試）")

    # 訂閱合約
    is_subscribed = subscribe_contracts(api_instance)
    if not is_subscribed:
        print(f"⚠️  合約訂閱未完全成功，啟用時段內將由背景檢查自動重試")


def stop_listener_session() -> None:
    """登出 Shioaji、釋放 Pub/Sub 連線，回到可重新開始的初始狀態"""
    global api_instance, pubsub_publisher, is_session_active, is_subscribed, is_stopping

    is_stopping = True

    # 等重連執行緒放棄，避免它在我們登出後又建立新連線
    if reconnect_thread is not None and reconnect_thread.is_alive() and reconnect_thread is not threading.current_thread():
        reconnect_thread.join(timeout=30)

    if api_instance is not None:
        check_usage(api_instance)
        print("👋 正在關閉連接...")
        if safe_logout(api_instance):
            print("✅ 已安全登出")

    if pubsub_publisher is not None:
        try:
            pubsub_publisher.close()
        except Exception as e:
            print(f"⚠️  關閉 Pub/Sub Publisher 失敗: {e}")

    api_instance = None
    pubsub_publisher = None
    is_session_active = False
    is_subscribed = False


def run_listener_session(should_continue: ShouldContinue) -> None:
    """執行一個交易時段：連線、訂閱，每秒檢查是否該收尾，每 60 秒做一次健康檢查（心跳、連線、tick 看門狗）"""
    try:
        start_listener_session()

        print("\n✅ 已就緒，開始監聽報價...")

        check_counter = 0
        while should_continue():
            stop_event.wait(1)
            check_counter += 1

            # 每 60 秒做一次健康檢查
            if check_counter >= 60:
                check_counter = 0
                run_health_checks()
    finally:
        stop_listener_session()


def _handle_sigterm(signum: int, frame: object) -> None:
    """Cloud Run / Docker 關閉服務時送 SIGTERM（不是 KeyboardInterrupt），通知時段迴圈收尾並結束"""
    print("\n\n🛑 收到 SIGTERM，開始關閉...")
    stop_event.set()


def main() -> None:
    threading.Thread(target=_start_health_check_server, daemon=True).start()
    signal.signal(signal.SIGTERM, _handle_sigterm)

    try:
        run_session_loop(
            name="price-listener",
            run_session=run_listener_session,
            is_active_fn=lambda: ACTIVE_WINDOW.contains(now_taipei()),
            stop_event=stop_event,
        )
    except KeyboardInterrupt:
        print("\n\n🛑 收到退出信號...")
        stop_event.set()

    print("👋 price-listener 已停止")


def get_shioaji_client() -> sj.Shioaji:
    """初始化並登入 Shioaji API"""
    api = sj.Shioaji(simulation=True)
    print("🔌 正在連接 Shioaji API...")

    try:
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
    except Exception:
        # 登入成功但後續步驟失敗時，要登出避免佔用連線數（時段迴圈每分鐘會重試）
        safe_logout(api)
        raise

    print("✅ Shioaji API 登入成功")
    return api


def check_usage(api: sj.Shioaji):
    """檢查 API 使用量並顯示剩餘額度百分比"""
    try:
        usage = api.usage()
    except Exception as e:
        print(f"❌ 取得 API 使用量失敗: {e}")
        return

    try:
        # { connections=1, bytes, limit_bytes=500MB, remaining_bytes }
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
