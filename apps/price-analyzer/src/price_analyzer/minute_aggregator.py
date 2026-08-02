"""
分鐘級資料聚合器
收集每分鐘的 tick 資料並計算 OHLC 和統計資訊
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Callable, List
from collections import defaultdict
from zoneinfo import ZoneInfo

from .strategy import TickData

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


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


class MinuteAggregator:
    """分鐘級資料聚合器"""

    def __init__(
        self,
        on_minute_complete: Optional[Callable[[MinuteBar], None]] = None,
        on_second_data_complete: Optional[Callable[[SecondBar], None]] = None,
    ):
        """
        初始化聚合器

        Args:
            on_minute_complete: 分鐘 OHLC 完成時的回調函數
            on_second_data_complete: 秒級報價明細完成時的回調函數（原 price-broadcaster 職責）
        """
        self.on_minute_complete = on_minute_complete
        self.on_second_data_complete = on_second_data_complete

        # 當前正在聚合的分鐘資料
        # key: (code, minute_timestamp)
        self.current_bars: Dict[tuple, Dict] = {}

        # 記錄最後處理的時間
        self.last_minute: Optional[datetime] = None

        # 秒級報價明細（用於重建每分鐘 60 筆報價）
        # key: (code, minute_timestamp), value: {second: {price, underlying_price, volume}}
        self.second_prices: Dict[tuple, Dict[int, dict]] = defaultdict(dict)

        # 每個商品目前已知的最新報價快照，供每秒取樣使用
        self.latest_snapshot: Dict[str, dict] = {}

        # 每秒成交量累加器（每次取樣後重置，同一秒內多筆 tick 需累計）
        self.second_volume_acc: Dict[str, int] = defaultdict(int)

        # 保存每個商品最後一筆已知價格，供下一分鐘第 0 秒缺失時前向填充
        self.last_minute_prices: Dict[str, float] = {}

        # 秒級取樣目前所在的分鐘（wall clock），用於偵測分鐘邊界以觸發 finalize
        self.last_sampled_minute: Optional[datetime] = None
    
    def add_tick(self, tick: TickData) -> Optional[MinuteBar]:
        """
        添加一筆 tick 資料
        
        Args:
            tick: Tick 資料
            
        Returns:
            如果完成了上一分鐘的資料，返回 MinuteBar，否則返回 None
        """
        # 取得分鐘時間戳（對齊到分鐘）
        minute_timestamp = tick.datetime.replace(second=0, microsecond=0)
        
        # 檢查時間順序 - 如果時間倒退且該分鐘已經完成，跳過該 tick
        if self.last_minute is not None and minute_timestamp < self.last_minute:
            print(f"⚠️  時間倒退！上一分鐘: {self.last_minute.strftime('%H:%M')}, "
                  f"當前分鐘: {minute_timestamp.strftime('%H:%M')} "
                  f"(Tick時間: {tick.datetime.strftime('%H:%M:%S')}) - 跳過處理")
            return None  # 跳過該 tick
        
        # 判斷是否需要完成上一分鐘
        completed_bar = None
        if self.last_minute is not None and minute_timestamp > self.last_minute:
            # 完成所有上一分鐘的 bar
            for key in list(self.current_bars.keys()):
                _, bar_minute = key
                if bar_minute < minute_timestamp:
                    bar_data = self.current_bars.get(key)
                    tick_count = bar_data['tick_count'] if bar_data else 0
                    print(f"✅ 完成分鐘 {bar_minute.strftime('%H:%M')} "
                          f"(共 {tick_count} 筆 Tick, 成交量: {bar_data['volume'] if bar_data else 0})")
                    completed_bar = self._finalize_bar(key)
                    if self.on_minute_complete and completed_bar:
                        self.on_minute_complete(completed_bar)
        
        self.last_minute = minute_timestamp
        
        # 建立或更新當前分鐘的資料
        key = (tick.code, minute_timestamp)
        
        if key not in self.current_bars:
            # 決定日期：夜盤跨日時（00:00-05:00）使用前一天日期
            market_type = self._get_market_type(minute_timestamp)
            bar_date = minute_timestamp
            if market_type == 'after_hours' and minute_timestamp.hour < 6:
                # 夜盤且在 00:00-05:59，日期為前一天
                bar_date = minute_timestamp - timedelta(days=1)
            
            # 初始化新的分鐘資料
            self.current_bars[key] = {
                'code': tick.code,
                'timestamp': minute_timestamp,
                'date': bar_date.strftime('%Y-%m-%d'),
                'time': minute_timestamp.strftime('%H%M'),
                'market_type': market_type,
                'open': tick.close,
                'high': tick.close,
                'low': tick.close,
                'close': tick.close,
                'volume': 0,
                'buy_volume': 0,
                'sell_volume': 0,
                'total_amount': Decimal('0'),
                'tick_count': 0,
                'bid_total_vol': 0,
                'ask_total_vol': 0,
            }
        
        # 更新資料
        bar_data = self.current_bars[key]
        bar_data['close'] = tick.close
        bar_data['high'] = max(bar_data['high'], tick.close)
        bar_data['low'] = min(bar_data['low'], tick.close)
        bar_data['volume'] += tick.volume
        bar_data['total_amount'] += tick.amount
        bar_data['tick_count'] += 1
        bar_data['bid_total_vol'] = tick.bid_side_total_vol
        bar_data['ask_total_vol'] = tick.ask_side_total_vol
        
        # 內外盤統計
        if tick.tick_type == 1:  # 外盤 (買進)
            bar_data['buy_volume'] += tick.volume
        elif tick.tick_type == 2:  # 內盤 (賣出)
            bar_data['sell_volume'] += tick.volume
        
        return completed_bar
    
    def _finalize_bar(self, key: tuple) -> Optional[MinuteBar]:
        """
        完成一個分鐘 bar 並返回
        
        Args:
            key: (code, minute_timestamp)
            
        Returns:
            完成的 MinuteBar
        """
        if key not in self.current_bars:
            return None
        
        bar_data = self.current_bars.pop(key)
        
        # 計算平均價
        avg_price = Decimal('0')
        if bar_data['volume'] > 0 and bar_data['total_amount'] > 0:
            avg_price = bar_data['total_amount'] / Decimal(bar_data['volume'])
        
        return MinuteBar(
            code=bar_data['code'],
            timestamp=bar_data['timestamp'],
            date=bar_data['date'],
            time=bar_data['time'],
            market_type=bar_data['market_type'],
            open=bar_data['open'],
            high=bar_data['high'],
            low=bar_data['low'],
            close=bar_data['close'],
            volume=bar_data['volume'],
            buy_volume=bar_data['buy_volume'],
            sell_volume=bar_data['sell_volume'],
            avg_price=avg_price,
            tick_count=bar_data['tick_count'],
            bid_total_vol=bar_data['bid_total_vol'],
            ask_total_vol=bar_data['ask_total_vol'],
        )
    
    def record_tick_price(self, code: str, price: float, underlying_price: float, volume: int) -> None:
        """
        記錄一筆 tick 的報價（原 price-broadcaster 的每秒報價收集邏輯）

        同一秒內可能有多筆 tick，成交量需要累加，價格則取最新一筆；
        實際落盤到哪一秒是由 sample_current_second() 每秒取樣決定。

        Args:
            code: 商品代碼
            price: 成交價
            underlying_price: 加權指數（現貨標的指數）
            volume: 該筆 tick 的成交量
        """
        self.second_volume_acc[code] += volume
        self.latest_snapshot[code] = {
            "price": price,
            "underlying_price": underlying_price,
            "volume": self.second_volume_acc[code],
        }

    def sample_current_second(self) -> None:
        """
        每秒呼叫一次：將目前已知的最新報價存入當前分鐘的秒級明細。

        偵測到 wall clock 進入新的一分鐘時，會先完成（finalize）上一分鐘所有商品的
        秒級資料，避免跟分鐘 OHLC 的 tick 驅動 finalize 用不同的時間基準互相干擾。
        """
        now = now_taipei()
        minute_timestamp = now.replace(second=0, microsecond=0)

        if self.last_sampled_minute is not None and minute_timestamp > self.last_sampled_minute:
            for code in list(self.latest_snapshot.keys()):
                self._finalize_second_bar((code, self.last_sampled_minute))

        self.last_sampled_minute = minute_timestamp

        if not self.latest_snapshot:
            return

        current_second = now.second
        for code, snapshot in self.latest_snapshot.items():
            key = (code, minute_timestamp)
            self.second_prices[key][current_second] = snapshot

        # 重置每秒成交量累加器，下一秒重新累計
        self.second_volume_acc.clear()

    def _finalize_second_bar(self, key: tuple) -> None:
        """
        完成單一商品在指定分鐘的秒級明細：前向填充缺秒後透過回調交出。

        缺秒只補 price（不含 underlying_price、volume）；若該分鐘第 0 秒缺失，
        使用上一分鐘最後價格填充；非交易時段的資料不寫出（沿用原 price-broadcaster 行為）。

        Args:
            key: (code, minute_timestamp)
        """
        code, minute_timestamp = key
        prices = self.second_prices.pop(key, None)
        if not prices:
            return

        if not self._is_in_trading_hours(minute_timestamp):
            return

        filtered_prices = {second: info for second, info in prices.items() if 0 <= second <= 59}

        save_data: Dict[str, dict] = {}
        last_price = None
        if 0 not in filtered_prices and code in self.last_minute_prices:
            last_price = self.last_minute_prices[code]

        for second in range(60):
            if second in filtered_prices:
                price_info = filtered_prices[second]
                last_price = price_info["price"]
                save_data[str(second).zfill(2)] = price_info
            elif last_price is not None:
                save_data[str(second).zfill(2)] = {"price": last_price}

        if last_price is not None:
            self.last_minute_prices[code] = last_price

        if not save_data:
            return

        # 夜盤跨日時（00:00-05:59）文件日期使用前一天，與分鐘 OHLC 的規則一致
        market_type = self._get_market_type(minute_timestamp)
        bar_date = minute_timestamp
        if market_type == 'after_hours' and minute_timestamp.hour < 6:
            bar_date = minute_timestamp - timedelta(days=1)

        second_bar = SecondBar(
            code=code,
            date=bar_date.strftime('%Y%m%d'),
            time=minute_timestamp.strftime('%H%M'),
            prices=save_data,
        )

        if self.on_second_data_complete:
            self.on_second_data_complete(second_bar)

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
        判斷指定時間是否在交易時段內（原 price-broadcaster 邏輯，用於過濾秒級明細）

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

        day_session_start = 8 * 60 + 45  # 08:45
        day_session_end = 13 * 60 + 45   # 13:45
        night_session_start = 15 * 60    # 15:00
        night_session_end = 5 * 60       # 05:00

        # 週六：只有 00:00-05:00 算是週五夜盤的延續
        if day == 5:
            return time_in_minutes < night_session_end

        # 週日：只有夜盤（15:00 開始）
        if day == 6:
            return time_in_minutes >= night_session_start

        # 週一至週五
        if day_session_start <= time_in_minutes <= day_session_end:
            return True
        if time_in_minutes >= night_session_start or time_in_minutes < night_session_end:
            return True

        return False

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
            _, bar_minute = key
            # 只 flush 明確已經過去的分鐘
            if (now - bar_minute).total_seconds() >= delay_minutes * 60:
                bar_data = self.current_bars.get(key)
                tick_count = bar_data['tick_count'] if bar_data else 0
                print(f"⏰ 自動完成分鐘 {bar_minute.strftime('%H:%M')} "
                      f"(共 {tick_count} 筆 Tick, 成交量: {bar_data['volume'] if bar_data else 0})")
                bar = self._finalize_bar(key)
                if bar:
                    completed_bars.append(bar)
                    if self.on_minute_complete:
                        self.on_minute_complete(bar)
        
        return completed_bars
    
    def flush_all(self) -> List[MinuteBar]:
        """
        強制完成所有正在聚合的分鐘資料（用於程式結束時）

        同時會一併完成尚未寫出的秒級明細，避免關閉服務時遺失最後一分鐘的資料。

        Returns:
            所有完成的 MinuteBar 列表
        """
        completed_bars = []
        for key in list(self.current_bars.keys()):
            bar = self._finalize_bar(key)
            if bar:
                completed_bars.append(bar)
                if self.on_minute_complete:
                    self.on_minute_complete(bar)

        for key in list(self.second_prices.keys()):
            self._finalize_second_bar(key)

        return completed_bars
