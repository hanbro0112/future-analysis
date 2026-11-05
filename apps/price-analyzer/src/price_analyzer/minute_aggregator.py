"""
分鐘級資料聚合器
收集每分鐘的 tick 資料並計算 OHLC 和統計資訊，同時以 tick 自己的時間戳
重建每分鐘 60 筆的秒級報價明細。

遲到（亂序）的 tick：
- 分鐘 OHLC 與秒級明細的 finalize 時機維持不變（給前端的資料固定在同樣的時間點寫出）。
- finalize 之後的 bar 會保留在記憶體（整個時段），遲到的 tick 直接更新對應的舊 bar 並標記為 dirty。
- dirty 的 bar 每隔一段時間（預設 1 分鐘）補寫一次，但只補寫「已經過了保留時間（預設 5 分鐘）」的，
  避免頻繁重寫還在變動的分鐘；收盤時（flush_all）一次補寫全部。
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Callable, List
from zoneinfo import ZoneInfo

from trading_calendar import is_session_open

from .strategy import TickData

TAIPEI_TZ = ZoneInfo("Asia/Taipei")

# dirty bar 的補寫間隔（秒）
DIRTY_FLUSH_INTERVAL_SECONDS = 60.0

# 分鐘結束後要等多久，dirty bar 才會被定期補寫（避免重寫還在變動的分鐘）
DIRTY_HOLD_MINUTES = 5

# 遲到 tick 的 log 節流：第 1 筆與之後每 N 筆才印一行
LATE_TICK_LOG_EVERY = 100


def now_taipei() -> datetime:
    """
    取得目前台北時間（naive datetime，不帶 tzinfo）。

    tick.datetime 來自 Shioaji，本身是不帶 tzinfo 的台北當地時間；
    容器內部時鐘預設為 UTC，若直接用 datetime.now() 會與 tick 時間差 8 小時，
    因此統一用這個函數取得「數值正確但仍為 naive」的台北時間，才能跟 tick 時間戳直接比較。
    """
    return datetime.now(TAIPEI_TZ).replace(tzinfo=None)


@dataclass
class MinuteBar:
    """分鐘級 K 線資料"""
    code: str
    timestamp: datetime  # 分鐘開始時間
    date: str  # YYYY-MM-DD
    time: str  # HHMM
    market_type: str  # regular / after_hours

    # OHLC
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    # 成交量
    volume: int  # 分鐘總成交量

    # 內外盤統計
    buy_volume: int = 0  # 外盤成交量
    sell_volume: int = 0  # 內盤成交量

    # 價格統計
    avg_price: Decimal = Decimal('0')

    # Tick 統計
    tick_count: int = 0

    # 委買賣量
    bid_total_vol: int = 0
    ask_total_vol: int = 0

    def to_dict(self) -> dict:
        """轉換為字典格式供 Firestore 儲存"""
        return {
            'code': self.code,
            'timestamp': self.timestamp,
            'date': self.date,
            'time': self.time,
            'market_type': self.market_type,
            'open': float(self.open),
            'high': float(self.high),
            'low': float(self.low),
            'close': float(self.close),
            'volume': self.volume,
            'buy_volume': self.buy_volume,
            'sell_volume': self.sell_volume,
            'avg_price': float(self.avg_price),
            'tick_count': self.tick_count,
            'bid_total_vol': self.bid_total_vol,
            'ask_total_vol': self.ask_total_vol,
        }


@dataclass
class SecondBar:
    """單一商品、單一分鐘的秒級報價明細（原 price-broadcaster 每分鐘報價統計，前向填充後 60 筆）"""
    code: str
    date: str  # YYYYMMDD
    time: str  # HHMM
    prices: Dict[str, dict]  # key: "00"~"59"，value: {price, underlying_price?, volume?}


@dataclass
class _MinuteState:
    """
    單一商品、單一分鐘的聚合狀態（分鐘 OHLC 與秒級原始資料）。

    finalize（寫出）之後仍保留在聚合器中，讓遲到的 tick 可以更新它。
    """
    code: str
    timestamp: datetime  # 分鐘開始時間
    date: str  # YYYY-MM-DD
    time: str  # HHMM
    market_type: str

    # OHLC：open / close 以 tick 時間決定，不受到達順序影響
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    open_ts: datetime
    close_ts: datetime

    volume: int = 0
    buy_volume: int = 0
    sell_volume: int = 0
    total_amount: Decimal = Decimal('0')
    tick_count: int = 0
    bid_total_vol: int = 0
    ask_total_vol: int = 0

    # 秒級原始資料（只含真的有 tick 的秒）：second -> {price, underlying_price, volume}
    seconds: Dict[int, dict] = field(default_factory=dict)
    second_ts: Dict[int, datetime] = field(default_factory=dict)  # 每一秒目前價格對應的 tick 時間

    # 秒級明細第一次寫出時，上一分鐘最後價格（第 0 秒缺失時前向填充用），之後補寫沿用同一個值
    carry_price: Optional[float] = None

    # 寫出狀態
    minute_finalized: bool = False
    seconds_finalized: bool = False
    seconds_skipped: bool = False  # 非交易時段，不寫出秒級明細
    minute_dirty: bool = False  # finalize 後又被遲到 tick 更新，尚未補寫
    seconds_dirty: bool = False


class MinuteAggregator:
    """分鐘級資料聚合器"""

    def __init__(
        self,
        on_minute_complete: Optional[Callable[[MinuteBar], None]] = None,
        on_second_data_complete: Optional[Callable[[SecondBar], None]] = None,
        on_minute_update: Optional[Callable[[MinuteBar], None]] = None,
        on_second_data_update: Optional[Callable[[SecondBar], None]] = None,
        dirty_flush_interval_seconds: float = DIRTY_FLUSH_INTERVAL_SECONDS,
        dirty_hold_minutes: float = DIRTY_HOLD_MINUTES,
    ):
        """
        初始化聚合器

        Args:
            on_minute_complete: 分鐘 OHLC 第一次完成時的回調函數
            on_second_data_complete: 秒級報價明細第一次完成時的回調函數（原 price-broadcaster 職責）
            on_minute_update: 已寫出的分鐘資料被遲到 tick 更新後，補寫時的回調函數
            on_second_data_update: 已寫出的秒級明細被遲到 tick 更新後，補寫時的回調函數
            dirty_flush_interval_seconds: 定期補寫 dirty bar 的間隔
            dirty_hold_minutes: 分鐘結束後要等多久才會被定期補寫
        """
        self.on_minute_complete = on_minute_complete
        self.on_second_data_complete = on_second_data_complete
        self.on_minute_update = on_minute_update
        self.on_second_data_update = on_second_data_update
        self.dirty_flush_interval = timedelta(seconds=dirty_flush_interval_seconds)
        self.dirty_hold = timedelta(minutes=dirty_hold_minutes)

        # 本時段所有分鐘狀態（含已寫出的），key: (code, minute_timestamp)；時段結束隨聚合器一起釋放
        self.minute_states: Dict[tuple, _MinuteState] = {}

        # 分鐘 OHLC 尚未 finalize 的狀態（即「當前正在聚合」的分鐘）
        self.current_bars: Dict[tuple, _MinuteState] = {}

        # 秒級明細尚未 finalize 的狀態
        self._open_seconds: Dict[tuple, _MinuteState] = {}

        # finalize 後被遲到 tick 更新、等待補寫的 key
        self._dirty_keys: set[tuple[str, datetime]] = set()

        # 記錄最後處理的時間（目前看過最晚的 tick 所在分鐘）
        self.last_minute: Optional[datetime] = None

        # 每個商品最後一個已寫出的秒級明細的最後價格，供下一分鐘第 0 秒缺失時前向填充
        self.last_minute_prices: Dict[str, float] = {}
        self._last_price_minute: Dict[str, datetime] = {}

        # 上次補寫 dirty bar 的時間（wall clock）
        self.last_dirty_flush_at: Optional[datetime] = None

        # 遲到 tick 統計
        self.late_updated_count = 0  # 更新了已寫出的舊 bar
        self.late_discarded_count = 0  # 找不到對應的 bar（例如服務重啟後），無法安全更新而丟棄

    # ========== tick 輸入 ==========

    def add_tick(self, tick: TickData) -> Optional[MinuteBar]:
        """
        添加一筆 tick 資料（分鐘 OHLC 與秒級明細一併更新）

        Args:
            tick: Tick 資料

        Returns:
            如果完成了上一分鐘的資料，返回 MinuteBar，否則返回 None
        """
        # 取得分鐘時間戳（對齊到分鐘）
        minute_timestamp = tick.datetime.replace(second=0, microsecond=0)
        key = (tick.code, minute_timestamp)

        completed_bar = None
        if self.last_minute is None or minute_timestamp > self.last_minute:
            # 進入更晚的分鐘：完成所有更早的分鐘（finalize 時機與過去相同）
            if self.last_minute is not None:
                completed_bar = self._finalize_minutes_before(minute_timestamp)
            self.last_minute = minute_timestamp

        state = self.minute_states.get(key)
        if state is None:
            if minute_timestamp < self.last_minute:
                # 遲到的 tick 但記憶體中沒有對應的 bar（例如服務重啟）：
                # 此時建立新 bar 會讓只有一筆 tick 的資料覆蓋已完整的文件，所以丟棄
                self.late_discarded_count += 1
                self._log_late(self.late_discarded_count, f"找不到 {tick.code} {minute_timestamp.strftime('%H:%M')} 的資料，丟棄遲到 tick")
                return completed_bar

            candidate = self._create_state(tick, minute_timestamp)
            state = self.minute_states.setdefault(key, candidate)  # 多執行緒同時建立時只保留一份
            if state is candidate:
                self.current_bars[key] = state
                self._open_seconds[key] = state

        self._apply_tick(state, tick)
        return completed_bar

    def _create_state(self, tick: TickData, minute_timestamp: datetime) -> _MinuteState:
        """建立新的分鐘狀態（尚未套用這筆 tick）"""
        market_type = self._get_market_type(minute_timestamp)
        return _MinuteState(
            code=tick.code,
            timestamp=minute_timestamp,
            date=self._bar_date(minute_timestamp, market_type).strftime('%Y-%m-%d'),
            time=minute_timestamp.strftime('%H%M'),
            market_type=market_type,
            open=tick.close,
            high=tick.close,
            low=tick.close,
            close=tick.close,
            open_ts=tick.datetime,
            close_ts=tick.datetime,
        )

    def _apply_tick(self, state: _MinuteState, tick: TickData) -> None:
        """
        把 tick 套用到分鐘狀態。

        最高 / 最低 / 成交量 / 內外盤與到達順序無關；open 取時間最早的 tick，
        close（與委買賣量）取時間最晚的 tick，因此亂序到達也能得到正確結果。
        """
        state.high = max(state.high, tick.close)
        state.low = min(state.low, tick.close)
        state.volume += tick.volume
        state.total_amount += tick.amount
        state.tick_count += 1

        if tick.datetime < state.open_ts:
            state.open = tick.close
            state.open_ts = tick.datetime
        if tick.datetime >= state.close_ts:
            state.close = tick.close
            state.close_ts = tick.datetime
            state.bid_total_vol = tick.bid_side_total_vol
            state.ask_total_vol = tick.ask_side_total_vol

        # 內外盤統計
        if tick.tick_type == 1:  # 外盤 (買進)
            state.buy_volume += tick.volume
        elif tick.tick_type == 2:  # 內盤 (賣出)
            state.sell_volume += tick.volume

        # 秒級原始資料：同一秒內價格取時間最晚的一筆，成交量累加
        second = tick.datetime.second
        entry = state.seconds.get(second)
        if entry is None:
            state.seconds[second] = {
                "price": float(tick.close),
                "underlying_price": float(tick.underlying_price),
                "volume": tick.volume,
            }
            state.second_ts[second] = tick.datetime
        else:
            entry["volume"] += tick.volume
            if tick.datetime >= state.second_ts[second]:
                entry["price"] = float(tick.close)
                entry["underlying_price"] = float(tick.underlying_price)
                state.second_ts[second] = tick.datetime

        # 已寫出的 bar 被更新：標記為 dirty（放在最後，確保補寫時一定能看到完整的更新）
        late = False
        if state.minute_finalized:
            state.minute_dirty = True
            late = True
        if state.seconds_finalized and not state.seconds_skipped:
            state.seconds_dirty = True
            late = True
        if late:
            self._dirty_keys.add((state.code, state.timestamp))
            self.late_updated_count += 1
            self._log_late(self.late_updated_count, f"遲到 tick 更新已寫出的 {state.code} {state.time}，待補寫")

    # ========== 分鐘 OHLC ==========

    def _finalize_minutes_before(self, minute_timestamp: datetime) -> Optional[MinuteBar]:
        """完成所有早於 minute_timestamp 的分鐘 bar，回傳最後一個完成的 bar"""
        completed_bar = None
        for key in list(self.current_bars.keys()):
            state = self.current_bars.get(key)
            if state is None or state.timestamp >= minute_timestamp:
                continue
            print(f"✅ 完成分鐘 {state.timestamp.strftime('%H:%M')} "
                  f"(共 {state.tick_count} 筆 Tick, 成交量: {state.volume})")
            completed_bar = self._emit_minute(state)
        return completed_bar

    def _emit_minute(self, state: _MinuteState) -> MinuteBar:
        """完成一個分鐘 bar：標記為已寫出（狀態仍保留供遲到 tick 更新），並觸發回調"""
        state.minute_finalized = True
        self.current_bars.pop((state.code, state.timestamp), None)

        bar = self._build_minute_bar(state)
        if self.on_minute_complete:
            self.on_minute_complete(bar)
        return bar

    def _build_minute_bar(self, state: _MinuteState) -> MinuteBar:
        """由目前的分鐘狀態建立 MinuteBar 快照"""
        avg_price = Decimal('0')
        if state.volume > 0 and state.total_amount > 0:
            avg_price = state.total_amount / Decimal(state.volume)

        return MinuteBar(
            code=state.code,
            timestamp=state.timestamp,
            date=state.date,
            time=state.time,
            market_type=state.market_type,
            open=state.open,
            high=state.high,
            low=state.low,
            close=state.close,
            volume=state.volume,
            buy_volume=state.buy_volume,
            sell_volume=state.sell_volume,
            avg_price=avg_price,
            tick_count=state.tick_count,
            bid_total_vol=state.bid_total_vol,
            ask_total_vol=state.ask_total_vol,
        )

    # ========== 秒級明細 ==========

    def finalize_seconds_if_needed(self) -> None:
        """
        每秒呼叫一次：wall clock 進入新的一分鐘時，完成所有更早分鐘的秒級明細。

        用 wall clock 判斷（與過去相同），因此 finalize 時機固定；
        處理落後而在 finalize 之後才到達的 tick，會以 tick 時間補進對應的舊明細並等待補寫。
        """
        current_minute = now_taipei().replace(second=0, microsecond=0)
        due = [
            state for state in list(self._open_seconds.values())
            if state.timestamp < current_minute
        ]
        for state in sorted(due, key=lambda s: s.timestamp):
            self._emit_seconds(state)

    def _emit_seconds(self, state: _MinuteState) -> None:
        """完成單一商品在指定分鐘的秒級明細並觸發回調（非交易時段不寫出）"""
        key = (state.code, state.timestamp)
        self._open_seconds.pop(key, None)
        state.seconds_finalized = True

        if not self._is_in_trading_hours(state.timestamp):
            state.seconds_skipped = True
            return

        state.carry_price = self.last_minute_prices.get(state.code)
        second_bar, last_price = self._build_second_bar(state)

        # 只讓時間較新的分鐘更新「上一分鐘最後價格」，避免補寫舊分鐘時倒退
        if last_price is not None and state.timestamp >= self._last_price_minute.get(state.code, state.timestamp):
            self.last_minute_prices[state.code] = last_price
            self._last_price_minute[state.code] = state.timestamp

        if second_bar is not None and self.on_second_data_complete:
            self.on_second_data_complete(second_bar)

    def _build_second_bar(self, state: _MinuteState) -> tuple[Optional[SecondBar], Optional[float]]:
        """
        由原始秒級資料建立前向填充後的秒級明細。

        缺秒只補 price（不含 underlying_price、volume）；若該分鐘第 0 秒缺失，
        使用上一分鐘最後價格（carry_price）填充。

        Returns:
            (SecondBar 或 None, 該分鐘最後價格或 None)
        """
        filtered_prices = {second: info for second, info in list(state.seconds.items()) if 0 <= second <= 59}

        save_data: Dict[str, dict] = {}
        last_price = None
        if 0 not in filtered_prices and state.carry_price is not None:
            last_price = state.carry_price

        for second in range(60):
            if second in filtered_prices:
                price_info = dict(filtered_prices[second])  # 複製，避免寫入時被後續遲到 tick 修改
                last_price = price_info["price"]
                save_data[str(second).zfill(2)] = price_info
            elif last_price is not None:
                save_data[str(second).zfill(2)] = {"price": last_price}

        if not save_data:
            return None, last_price

        second_bar = SecondBar(
            code=state.code,
            date=state.date.replace('-', ''),
            time=state.time,
            prices=save_data,
        )
        return second_bar, last_price

    # ========== 補寫 dirty bar ==========

    def flush_dirty_if_needed(self, force: bool = False) -> int:
        """
        補寫被遲到 tick 更新過的 bar。

        - 一般呼叫（force=False）：距離上次補寫超過間隔才執行，且只補寫分鐘結束後
          已過保留時間的 bar（最近幾分鐘還可能繼續被更新，先不寫）。
        - force=True（收盤 / 服務關閉）：立刻補寫全部。

        Returns:
            本次補寫的 bar 數量
        """
        now = now_taipei()
        if not force:
            if self.last_dirty_flush_at is not None and now - self.last_dirty_flush_at < self.dirty_flush_interval:
                return 0
            self.last_dirty_flush_at = now

        written = 0
        for key in sorted(list(self._dirty_keys), key=lambda k: k[1]):
            state = self.minute_states.get(key)
            if state is None:
                self._dirty_keys.discard(key)
                continue

            if not force and now < state.timestamp + timedelta(minutes=1) + self.dirty_hold:
                continue

            # 先清除標記再建立快照：補寫期間若又有遲到 tick，會重新標記並在下一輪補寫
            self._dirty_keys.discard(key)
            minute_dirty, seconds_dirty = state.minute_dirty, state.seconds_dirty
            state.minute_dirty = False
            state.seconds_dirty = False

            if minute_dirty and self.on_minute_update:
                self.on_minute_update(self._build_minute_bar(state))
                written += 1

            if seconds_dirty and self.on_second_data_update:
                second_bar, _ = self._build_second_bar(state)
                if second_bar is not None:
                    self.on_second_data_update(second_bar)
                    written += 1

        return written

    # ========== 定時維護 ==========

    def run_maintenance(self, delay_minutes: float = 1.5) -> None:
        """
        每秒由背景定時器呼叫：完成該結束的秒級明細、逾時保險 flush 分鐘 OHLC、補寫 dirty bar。
        """
        self.finalize_seconds_if_needed()
        self.auto_flush_if_needed(delay_minutes=delay_minutes)
        self.flush_dirty_if_needed()

    def should_flush(self, delay_minutes: float = 1.5) -> bool:
        """
        檢查是否應該執行 flush（當前時間超過最後一個 tick 的時間一定分鐘數）

        Args:
            delay_minutes: 延遲分鐘數，預設 1.5 分鐘

        Returns:
            是否需要 flush
        """
        if self.last_minute is None or not self.current_bars:
            return False

        now = now_taipei()
        time_diff = (now - self.last_minute).total_seconds() / 60.0
        return time_diff >= delay_minutes

    def auto_flush_if_needed(self, delay_minutes: float = 1.5) -> List[MinuteBar]:
        """
        如果需要則自動 flush 所有應完成的分鐘資料

        Args:
            delay_minutes: 延遲分鐘數，預設 1.5 分鐘

        Returns:
            完成的 MinuteBar 列表
        """
        if not self.should_flush(delay_minutes):
            return []

        now = now_taipei()
        completed_bars = []

        for key in list(self.current_bars.keys()):
            state = self.current_bars.get(key)
            if state is None:
                continue
            # 只 flush 明確已經過去的分鐘
            if (now - state.timestamp).total_seconds() >= delay_minutes * 60:
                print(f"⏰ 自動完成分鐘 {state.timestamp.strftime('%H:%M')} "
                      f"(共 {state.tick_count} 筆 Tick, 成交量: {state.volume})")
                completed_bars.append(self._emit_minute(state))

        return completed_bars

    def flush_all(self) -> List[MinuteBar]:
        """
        強制完成所有正在聚合的分鐘資料，並補寫所有被遲到 tick 更新過的 bar（用於收盤 / 程式結束時）

        同時會一併完成尚未寫出的秒級明細，避免關閉服務時遺失最後一分鐘的資料。

        Returns:
            本次新完成的 MinuteBar 列表（補寫的 bar 不在其中）
        """
        completed_bars = []
        for key in list(self.current_bars.keys()):
            state = self.current_bars.get(key)
            if state is not None:
                completed_bars.append(self._emit_minute(state))

        for state in sorted(list(self._open_seconds.values()), key=lambda s: s.timestamp):
            self._emit_seconds(state)

        self.flush_dirty_if_needed(force=True)

        return completed_bars

    # ========== 輔助 ==========

    def _bar_date(self, minute_timestamp: datetime, market_type: str) -> datetime:
        """夜盤跨日時（00:00-05:59）文件日期使用前一天"""
        if market_type == 'after_hours' and minute_timestamp.hour < 6:
            return minute_timestamp - timedelta(days=1)
        return minute_timestamp

    def _log_late(self, count: int, message: str) -> None:
        """遲到 tick 的 log 節流：第 1 筆與之後每 N 筆才印一行"""
        if count == 1 or count % LATE_TICK_LOG_EVERY == 0:
            print(f"⏪ {message}（累計 {count} 筆）")

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
        """判斷指定時間是否在交易時段內（含國定假日），用於過濾秒級明細"""
        return is_session_open(dt)
