"""
分鐘級資料聚合器
收集每分鐘的 tick 資料並計算 OHLC 和統計資訊
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Callable, List
from collections import defaultdict

from .strategy import TickData


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


class MinuteAggregator:
    """分鐘級資料聚合器"""
    
    def __init__(self, on_minute_complete: Optional[Callable[[MinuteBar], None]] = None):
        """
        初始化聚合器
        
        Args:
            on_minute_complete: 分鐘完成時的回調函數
        """
        self.on_minute_complete = on_minute_complete
        
        # 當前正在聚合的分鐘資料
        # key: (code, minute_timestamp)
        self.current_bars: Dict[tuple, Dict] = {}
        
        # 記錄最後處理的時間
        self.last_minute: Optional[datetime] = None
    
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
            # 初始化新的分鐘資料
            self.current_bars[key] = {
                'code': tick.code,
                'timestamp': minute_timestamp,
                'date': minute_timestamp.strftime('%Y-%m-%d'),
                'time': minute_timestamp.strftime('%H%M'),
                'market_type': self._get_market_type(minute_timestamp),
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
    
    def flush_all(self) -> List[MinuteBar]:
        """
        強制完成所有正在聚合的分鐘資料（用於程式結束時）
        
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
        return completed_bars
