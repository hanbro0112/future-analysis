"""
多空比分析策略
基於成交量、成交價、期現價差進行多空判斷
"""
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional
from collections import deque


@dataclass
class TickData:
    """Tick 資料結構"""
    code: str
    datetime: datetime
    open: Decimal
    underlying_price: Decimal  # 現貨價格
    bid_side_total_vol: int
    ask_side_total_vol: int
    avg_price: Decimal
    close: Decimal  # 期貨價格
    high: Decimal
    low: Decimal
    amount: Decimal
    total_amount: Decimal
    volume: int
    total_volume: int
    tick_type: int  # 1: 外盤(買進), 2: 內盤(賣出), 0: 無法判定
    chg_type: int
    price_chg: Decimal
    pct_chg: Decimal
    simtrade: bool


@dataclass
class TimeWindowStats:
    """時間區間統計資料"""
    duration_minutes: int
    buy_volume: int = 0  # 外盤成交量 (主動買進)
    sell_volume: int = 0  # 內盤成交量 (主動賣出)
    total_volume: int = 0
    buy_amount: Decimal = Decimal('0')
    sell_amount: Decimal = Decimal('0')
    high_price: Optional[Decimal] = None
    low_price: Optional[Decimal] = None
    open_price: Optional[Decimal] = None
    close_price: Optional[Decimal] = None
    tick_count: int = 0
    
    def add_tick(self, tick: TickData):
        """添加一筆 Tick 資料"""
        self.total_volume += tick.volume
        self.tick_count += 1
        
        # 記錄開盤價
        if self.open_price is None:
            self.open_price = tick.close
        
        # 更新收盤價
        prev_close = self.close_price
        self.close_price = tick.close
        
        # 更新最高最低價
        if self.high_price is None or tick.close > self.high_price:
            self.high_price = tick.close
        if self.low_price is None or tick.close < self.low_price:
            self.low_price = tick.close
        
        # 判斷內外盤
        tick_type = tick.tick_type
        
        # 當 tick_type 為 0（無法判定）時，根據價格變動推測
        if tick_type == 0 and prev_close is not None:
            if tick.close > prev_close:
                tick_type = 1  # 價格上漲，推測為外盤（買進）
            elif tick.close < prev_close:
                tick_type = 2  # 價格下跌，推測為內盤（賣出）
            else:
                # 價格不變，均分到買賣雙方
                self.buy_volume += tick.volume // 2
                self.sell_volume += tick.volume - (tick.volume // 2)
                self.buy_amount += tick.amount / 2
                self.sell_amount += tick.amount / 2
                return
        
        # 根據判定的內外盤分類
        if tick_type == 1:  # 外盤 (買進)
            self.buy_volume += tick.volume
            self.buy_amount += tick.amount
        elif tick_type == 2:  # 內盤 (賣出)
            self.sell_volume += tick.volume
            self.sell_amount += tick.amount
        else:
            # 仍無法判定，均分
            self.buy_volume += tick.volume // 2
            self.sell_volume += tick.volume - (tick.volume // 2)
            self.buy_amount += tick.amount / 2
            self.sell_amount += tick.amount / 2
    
    @property
    def buy_sell_ratio(self) -> float:
        """買賣量比例 (外盤/內盤)"""
        if self.sell_volume == 0:
            return float('inf') if self.buy_volume > 0 else 1.0
        return self.buy_volume / self.sell_volume
    
    @property
    def net_volume(self) -> int:
        """淨成交量 (外盤 - 內盤)"""
        return self.buy_volume - self.sell_volume
    
    @property
    def price_change_pct(self) -> Optional[float]:
        """價格變動百分比"""
        if self.open_price is None or self.close_price is None or self.open_price == 0:
            return None
        return float((self.close_price - self.open_price) / self.open_price * 100)


@dataclass
class VolumeExplosionIndicator:
    """成交量爆量指標"""
    current_volume: int
    avg_volume_today: float
    explosion_ratio: float  # 爆量比率 (當前/平均)
    is_explosion: bool  # 是否爆量 (超過平均 1.5 倍)
    
    @property
    def explosion_level(self) -> str:
        """爆量等級"""
        if self.explosion_ratio >= 3.0:
            return "極度爆量"
        elif self.explosion_ratio >= 2.0:
            return "嚴重爆量"
        elif self.explosion_ratio >= 1.5:
            return "爆量"
        elif self.explosion_ratio >= 1.2:
            return "放量"
        else:
            return "正常"


@dataclass
class BasisAnalysis:
    """期現價差分析"""
    futures_price: Decimal  # 期貨價格
    spot_price: Decimal  # 現貨價格
    basis: Decimal  # 價差 (期貨 - 現貨)
    basis_pct: float  # 價差百分比
    
    @property
    def is_contango(self) -> bool:
        """是否正價差 (期貨 > 現貨)"""
        return self.basis > 0
    
    @property
    def trend_signal(self) -> str:
        """價差信號"""
        if abs(float(self.basis_pct)) < 0.1:
            return "中性"
        elif self.is_contango:
            if self.basis_pct > 0.5:
                return "強勢正價差"
            return "正價差"
        else:
            if self.basis_pct < -0.5:
                return "強勢逆價差"
            return "逆價差"


@dataclass
class SentimentIndicator:
    """市場情緒指標"""
    bid_ask_ratio: float  # 委買委賣比 (委買量/委賣量)
    continuous_direction: int  # 連續方向 (正數=連續外盤, 負數=連續內盤)
    momentum_score: float  # 動能分數 (0-100, 50為中性)
    volatility_level: str  # 波動程度: "極低", "低", "正常", "高", "極高"
    volatility: int  # 波動率 (0-100)，改良自 Choppiness Index：100 * log10(路徑總長/價格範圍) / log10(步數)，不受 tick 數量影響
    sentiment_score: float  # 綜合情緒分數 (0-100, >60貪婪, <40恐慌)
    sentiment_label: str  # 情緒標籤
    
    @property
    def is_bullish(self) -> bool:
        """是否偏多情緒"""
        return self.sentiment_score >= 60
    
    @property
    def is_bearish(self) -> bool:
        """是否偏空情緒"""
        return self.sentiment_score <= 40
    
    @property
    def bid_ask_signal(self) -> str:
        """委買委賣信號"""
        if self.bid_ask_ratio > 1.3:
            return "委買強勢"
        elif self.bid_ask_ratio > 1.1:
            return "委買優勢"
        elif self.bid_ask_ratio < 0.7:
            return "委賣強勢"
        elif self.bid_ask_ratio < 0.9:
            return "委賣優勢"
        else:
            return "均衡"


@dataclass
class LongShortRatio:
    """多空比分析結果"""
    timestamp: datetime
    
    # 各時間區間統計
    window_1min: TimeWindowStats
    window_5min: TimeWindowStats
    window_30min: TimeWindowStats
    
    # 成交量指標
    volume_indicator: VolumeExplosionIndicator
    
    # 期現價差
    basis_analysis: BasisAnalysis
    
    # 市場情緒指標
    sentiment_indicator: SentimentIndicator
    
    # 綜合多空比
    long_ratio: float  # 多方比例 (0-100)
    short_ratio: float  # 空方比例 (0-100)
    signal: str  # 信號: "強多", "偏多", "中性", "偏空", "強空"
    confidence: float  # 信心水準 (0-100)


@dataclass
class _WindowEntry:
    """滑動視窗內的一筆 tick，以及它目前對買賣量的貢獻"""
    tick: TickData
    seq: int
    buy_volume: int
    sell_volume: int
    buy_amount: Decimal
    sell_amount: Decimal


def _split_evenly(tick: TickData) -> tuple[int, int, Decimal, Decimal]:
    """無法判定內外盤時，成交量與金額均分到買賣雙方"""
    buy_volume = tick.volume // 2
    return buy_volume, tick.volume - buy_volume, tick.amount / 2, tick.amount / 2


def _classify_tick(tick: TickData, prev_close: Optional[Decimal]) -> tuple[int, int, Decimal, Decimal]:
    """
    判定單筆 tick 的內外盤，回傳 (買量, 賣量, 買金額, 賣金額)。

    規則與 TimeWindowStats.add_tick 完全一致：tick_type 為 0（無法判定）時，
    用視窗內前一筆的收盤價推測；視窗第一筆沒有前一筆（prev_close 為 None）就均分。
    """
    tick_type = tick.tick_type

    if tick_type == 0 and prev_close is not None:
        if tick.close > prev_close:
            tick_type = 1  # 價格上漲，推測為外盤（買進）
        elif tick.close < prev_close:
            tick_type = 2  # 價格下跌，推測為內盤（賣出）
        else:
            return _split_evenly(tick)  # 價格不變，均分到買賣雙方

    if tick_type == 1:  # 外盤 (買進)
        return tick.volume, 0, tick.amount, Decimal('0')
    if tick_type == 2:  # 內盤 (賣出)
        return 0, tick.volume, Decimal('0'), tick.amount

    return _split_evenly(tick)  # 仍無法判定，均分


class SlidingWindow:
    """
    增量維護的時間滑動視窗。

    每筆 tick 進入視窗時把貢獻加進累計值，過期時扣掉，
    因此新增與取得統計都是 O(1)（均攤），不需要每筆 tick 重新掃描整個視窗。
    累計值包含 TimeWindowStats 的所有欄位，以及波動率與連續內外盤所需的資料。

    視窗內的 tick 必須依時間遞增加入（呼叫端負責排除遲到的 tick）。
    """

    def __init__(self, duration_minutes: int):
        self.duration_minutes = duration_minutes
        self._duration = timedelta(minutes=duration_minutes)
        self._entries: deque[_WindowEntry] = deque()
        self._seq = 0

        self._total_volume = 0
        self._buy_volume = 0
        self._sell_volume = 0
        self._buy_amount = Decimal('0')
        self._sell_amount = Decimal('0')

        # 逐筆變動絕對值加總（Decimal 精確運算，加減不會累積誤差）
        self._path_length = Decimal('0')

        # 單調佇列：頭端永遠是視窗內的最高 / 最低收盤價，元素為 (seq, close)
        self._max_closes: deque[tuple[int, Decimal]] = deque()
        self._min_closes: deque[tuple[int, Decimal]] = deque()

        # 內外盤連續區段（只計 tick_type 1 / 2）：[tick_type, 連續筆數]
        self._runs: deque[list[int]] = deque()

    def __len__(self) -> int:
        return len(self._entries)

    def add(self, tick: TickData) -> None:
        """加入一筆 tick（尚未清理過期資料，請接著呼叫 expire）"""
        prev_close = self._entries[-1].tick.close if self._entries else None
        buy_volume, sell_volume, buy_amount, sell_amount = _classify_tick(tick, prev_close)

        self._seq += 1
        entry = _WindowEntry(tick, self._seq, buy_volume, sell_volume, buy_amount, sell_amount)
        self._entries.append(entry)

        self._total_volume += tick.volume
        self._add_contribution(entry)

        if prev_close is not None:
            self._path_length += abs(tick.close - prev_close)

        while self._max_closes and self._max_closes[-1][1] <= tick.close:
            self._max_closes.pop()
        self._max_closes.append((entry.seq, tick.close))

        while self._min_closes and self._min_closes[-1][1] >= tick.close:
            self._min_closes.pop()
        self._min_closes.append((entry.seq, tick.close))

        if tick.tick_type in (1, 2):
            if self._runs and self._runs[-1][0] == tick.tick_type:
                self._runs[-1][1] += 1
            else:
                self._runs.append([tick.tick_type, 1])

    def expire(self, current_time: datetime) -> None:
        """移除比 current_time - 視窗長度 更早的 tick"""
        cutoff = current_time - self._duration

        expired_any = False
        while self._entries and self._entries[0].tick.datetime < cutoff:
            self._pop_head()
            expired_any = True

        # 新的第一筆沒有前一筆可比較，內外盤推測要改用「視窗第一筆」的規則重算
        if expired_any and self._entries:
            self._reclassify_head()

    def snapshot(self) -> TimeWindowStats:
        """產生目前視窗的統計快照（獨立物件，不會隨後續 tick 變動）"""
        stats = TimeWindowStats(
            duration_minutes=self.duration_minutes,
            buy_volume=self._buy_volume,
            sell_volume=self._sell_volume,
            total_volume=self._total_volume,
            buy_amount=self._buy_amount,
            sell_amount=self._sell_amount,
            tick_count=len(self._entries),
        )
        if self._entries:
            stats.open_price = self._entries[0].tick.close
            stats.close_price = self._entries[-1].tick.close
            stats.high_price = self._max_closes[0][1]
            stats.low_price = self._min_closes[0][1]
        return stats

    def continuous_direction(self) -> int:
        """
        從最新一筆往回算的連續內外盤方向（正數=連續外盤，負數=連續內盤）。

        tick_type 不是 1 / 2 的 tick 不中斷連續區段；視窗內少於 2 筆回傳 0。
        """
        if len(self._entries) < 2 or not self._runs:
            return 0

        tick_type, count = self._runs[-1]
        return count if tick_type == 1 else -count

    def choppiness_index(self) -> float:
        """
        計算波動率：改良自 Choppiness Index（震盪指標，E.W. Dreiss 提出的經典技術指標）

        CI = 100 * log10(路徑總長 / 價格範圍) / log10(tick 步數)

        「路徑總長」是逐筆變動絕對值加總，「價格範圍」是視窗內最高減最低。
        兩者相除代表「這段路徑來回走了幾倍的實際範圍」：完全單向移動時路徑總長等於
        範圍，比值為 1；來回震盪越多次，比值越大。

        這個比值本身也會隨 tick 數線性成長而失真（詳見先前 PER 版本的問題：路徑總長
        隨取樣頻率近似線性發散），所以用 log10(步數) 當分母去抵銷，而不是用 sqrt(n)
        這種只在特定雜訊分布假設下成立的近似修正。log10 成長極慢，效果是讓比值不會
        單純因為 tick 變多而持續墊高分數，真正反映的是「相對於這一分鐘走過的範圍，
        來回折返了多少次」，也就是數值本身的波動程度，而不是取樣密度。

        Returns:
            波動率 (0~100)；步數不足 2 或價格沒有波動時為 0
        """
        steps = len(self._entries) - 1
        if steps < 2:
            return 0.0

        path_length = float(self._path_length)
        price_range = float(self._max_closes[0][1] - self._min_closes[0][1])

        if price_range == 0 or path_length == 0:
            return 0.0

        ci = 100 * math.log10(path_length / price_range) / math.log10(steps)
        return max(0.0, min(ci, 100.0))

    def _add_contribution(self, entry: _WindowEntry) -> None:
        self._buy_volume += entry.buy_volume
        self._sell_volume += entry.sell_volume
        self._buy_amount += entry.buy_amount
        self._sell_amount += entry.sell_amount

    def _remove_contribution(self, entry: _WindowEntry) -> None:
        self._buy_volume -= entry.buy_volume
        self._sell_volume -= entry.sell_volume
        self._buy_amount -= entry.buy_amount
        self._sell_amount -= entry.sell_amount

    def _pop_head(self) -> None:
        """移除視窗第一筆，並把它的貢獻從所有累計值扣掉"""
        entry = self._entries.popleft()

        self._total_volume -= entry.tick.volume
        self._remove_contribution(entry)

        if self._entries:
            self._path_length -= abs(self._entries[0].tick.close - entry.tick.close)
        else:
            self._path_length = Decimal('0')

        if self._max_closes and self._max_closes[0][0] == entry.seq:
            self._max_closes.popleft()
        if self._min_closes and self._min_closes[0][0] == entry.seq:
            self._min_closes.popleft()

        if entry.tick.tick_type in (1, 2) and self._runs:
            self._runs[0][1] -= 1
            if self._runs[0][1] <= 0:
                self._runs.popleft()

    def _reclassify_head(self) -> None:
        """視窗第一筆改變後，用「沒有前一筆」的規則重算它的買賣量貢獻"""
        head = self._entries[0]
        buy_volume, sell_volume, buy_amount, sell_amount = _classify_tick(head.tick, None)

        self._remove_contribution(head)
        head.buy_volume = buy_volume
        head.sell_volume = sell_volume
        head.buy_amount = buy_amount
        head.sell_amount = sell_amount
        self._add_contribution(head)


class LongShortAnalyzer:
    """多空比分析器"""

    def __init__(self):
        # 增量維護不同時間視窗的統計（每筆 tick 的處理成本不隨視窗大小增加）
        self._window_1min = SlidingWindow(1)
        self._window_5min = SlidingWindow(5)
        self._window_30min = SlidingWindow(30)

        # 當天累計資料 (用於計算平均成交量，只存累計值，不保留每筆 tick)
        self.current_date: Optional[datetime] = None
        self.today_tick_count = 0
        self.today_total_volume = 0
        self.today_first_time: Optional[datetime] = None
        self.today_last_time: Optional[datetime] = None

        # 目前已處理的最新 tick 時間，用來排除遲到的 tick
        self.last_tick_time: Optional[datetime] = None

        # 儲存最新的分析結果
        self.latest_analysis: Optional[LongShortRatio] = None

    def add_tick(self, tick: TickData) -> bool:
        """
        添加新的 Tick 資料

        視窗統計依賴 tick 依時間遞增加入；時間早於已處理最新 tick 的遲到 tick
        不納入分析（它們仍會由分鐘聚合器補進對應分鐘的資料）。

        Returns:
            True 代表已納入分析，False 代表是遲到的 tick 而被略過
        """
        if self.last_tick_time is not None and tick.datetime < self.last_tick_time:
            return False
        self.last_tick_time = tick.datetime

        # 檢查是否跨日，若是則重置當天資料
        if self.current_date is None or tick.datetime.date() != self.current_date:
            self.current_date = tick.datetime.date()
            self.today_tick_count = 0
            self.today_total_volume = 0
            self.today_first_time = None

        self.today_tick_count += 1
        self.today_total_volume += tick.volume
        if self.today_first_time is None:
            self.today_first_time = tick.datetime
        self.today_last_time = tick.datetime

        # 添加到各時間視窗並移除過期資料
        for window in (self._window_1min, self._window_5min, self._window_30min):
            window.add(tick)
            window.expire(tick.datetime)

        return True

    def _calculate_volume_indicator(self, current_volume: int) -> VolumeExplosionIndicator:
        """計算成交量爆量指標"""
        # 計算當天平均成交量 (每分鐘)
        if self.today_tick_count < 2 or self.today_first_time is None or self.today_last_time is None:
            avg_volume = current_volume
        else:
            # 計算時間範圍
            time_span = (self.today_last_time - self.today_first_time).total_seconds() / 60
            if time_span < 1:
                time_span = 1

            # 總成交量 / 時間 = 每分鐘平均成交量
            avg_volume = self.today_total_volume / time_span

        # 計算爆量比率
        explosion_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        is_explosion = explosion_ratio >= 1.5

        return VolumeExplosionIndicator(
            current_volume=current_volume,
            avg_volume_today=avg_volume,
            explosion_ratio=explosion_ratio,
            is_explosion=is_explosion
        )

    def _calculate_basis(self, tick: TickData) -> BasisAnalysis:
        """計算期現價差"""
        basis = tick.close - tick.underlying_price
        
        # 防止除以零
        if tick.underlying_price == 0:
            basis_pct = 0.0
        else:
            basis_pct = float(basis / tick.underlying_price * 100)
        
        return BasisAnalysis(
            futures_price=tick.close,
            spot_price=tick.underlying_price,
            basis=basis,
            basis_pct=basis_pct
        )
    
    def _calculate_sentiment(
        self,
        latest_tick: TickData,
        window_1min: TimeWindowStats,
        window_5min: TimeWindowStats
    ) -> SentimentIndicator:
        """計算市場情緒指標"""
        
        # 1. 委買委賣比
        bid_ask_ratio = 1.0
        if latest_tick.ask_side_total_vol > 0:
            bid_ask_ratio = latest_tick.bid_side_total_vol / latest_tick.ask_side_total_vol
        
        # 2. 連續內外盤方向
        continuous_direction = self._window_1min.continuous_direction()

        # 3. 動能分數 (結合價格變動和成交量)
        momentum_score = 50.0  # 中性
        if window_5min.price_change_pct is not None and window_5min.total_volume > 0:
            # 價格動能
            price_momentum = window_5min.price_change_pct * 10  # 放大10倍
            
            # 成交量強度 (買賣比)
            if window_5min.total_volume > 0:
                volume_strength = (window_5min.buy_volume / window_5min.total_volume - 0.5) * 100
            else:
                volume_strength = 0
            
            # 綜合動能 (價格60% + 成交量40%)
            momentum_score = 50 + (price_momentum * 0.6 + volume_strength * 0.4)
            momentum_score = max(0, min(100, momentum_score))  # 限制在 0-100
        
        # 4. 波動程度 (根據1分鐘高低價差)
        volatility_level = "正常"
        if window_1min.high_price and window_1min.low_price and window_1min.open_price:
            volatility_pct = float((window_1min.high_price - window_1min.low_price) / window_1min.open_price * 100)
            if volatility_pct >= 0.5:
                volatility_level = "極高"
            elif volatility_pct >= 0.3:
                volatility_level = "高"
            elif volatility_pct >= 0.15:
                volatility_level = "正常"
            elif volatility_pct >= 0.08:
                volatility_level = "低"
            else:
                volatility_level = "極低"

        # 4-1. 波動率 (Choppiness Index，同樣使用 1 分鐘視窗的 tick 序列)
        volatility = round(self._window_1min.choppiness_index())

        # 5. 綜合情緒分數
        scores = []
        
        # 委買委賣貢獻 (30%)
        if bid_ask_ratio > 1.3:
            scores.append((70, 0.30))
        elif bid_ask_ratio > 1.1:
            scores.append((60, 0.30))
        elif bid_ask_ratio < 0.7:
            scores.append((30, 0.30))
        elif bid_ask_ratio < 0.9:
            scores.append((40, 0.30))
        else:
            scores.append((50, 0.30))
        
        # 連續方向貢獻 (25%)
        if continuous_direction >= 5:
            scores.append((75, 0.25))
        elif continuous_direction >= 3:
            scores.append((65, 0.25))
        elif continuous_direction >= 1:
            scores.append((55, 0.25))
        elif continuous_direction <= -5:
            scores.append((25, 0.25))
        elif continuous_direction <= -3:
            scores.append((35, 0.25))
        elif continuous_direction <= -1:
            scores.append((45, 0.25))
        else:
            scores.append((50, 0.25))
        
        # 動能分數貢獻 (35%)
        scores.append((momentum_score, 0.35))
        
        # 波動率影響 (10%) - 高波動降低信心，讓分數往中性靠攏
        volatility_adjustment = 1.0
        if volatility_level in ["極高", "高"]:
            volatility_adjustment = 0.9
            scores.append((50, 0.10))  # 拉向中性
        else:
            scores.append((momentum_score, 0.10))  # 追隨動能
        
        # 計算加權平均
        sentiment_score = sum(s * w for s, w in scores) / sum(w for _, w in scores)
        
        # 情緒標籤
        if sentiment_score >= 75:
            sentiment_label = "極度貪婪"
        elif sentiment_score >= 60:
            sentiment_label = "貪婪"
        elif sentiment_score >= 55:
            sentiment_label = "偏貪婪"
        elif sentiment_score >= 45:
            sentiment_label = "一般"
        elif sentiment_score >= 40:
            sentiment_label = "偏恐慌"
        elif sentiment_score >= 25:
            sentiment_label = "恐慌"
        else:
            sentiment_label = "極度恐慌"
        
        return SentimentIndicator(
            bid_ask_ratio=bid_ask_ratio,
            continuous_direction=continuous_direction,
            momentum_score=momentum_score,
            volatility_level=volatility_level,
            volatility=volatility,
            sentiment_score=sentiment_score,
            sentiment_label=sentiment_label
        )
    
    def _calculate_long_short_ratio(
        self,
        window_1min: TimeWindowStats,
        window_5min: TimeWindowStats,
        window_30min: TimeWindowStats,
        volume_indicator: VolumeExplosionIndicator,
        basis_analysis: BasisAnalysis
    ) -> tuple[float, float, str, float]:
        """
        計算綜合多空比
        
        Returns:
            (long_ratio, short_ratio, signal, confidence)
        """
        scores = []
        weights = []
        
        # 1. 短期價量分析 (1分鐘) - 權重 25%
        if window_1min.total_volume > 0:
            buy_ratio_1m = window_1min.buy_volume / window_1min.total_volume
            price_momentum_1m = window_1min.price_change_pct or 0
            
            # 價量配合度
            if buy_ratio_1m > 0.6 and price_momentum_1m > 0:
                scores.append(75)  # 強多
            elif buy_ratio_1m > 0.55:
                scores.append(60)  # 偏多
            elif buy_ratio_1m < 0.4 and price_momentum_1m < 0:
                scores.append(25)  # 強空
            elif buy_ratio_1m < 0.45:
                scores.append(40)  # 偏空
            else:
                scores.append(50)  # 中性
            
            weights.append(0.25)
        
        # 2. 中期趨勢分析 (5分鐘) - 權重 30%
        if window_5min.total_volume > 0:
            buy_ratio_5m = window_5min.buy_volume / window_5min.total_volume
            price_momentum_5m = window_5min.price_change_pct or 0
            
            if buy_ratio_5m > 0.58 and price_momentum_5m > 0:
                scores.append(70)
            elif buy_ratio_5m > 0.53:
                scores.append(60)
            elif buy_ratio_5m < 0.42 and price_momentum_5m < 0:
                scores.append(30)
            elif buy_ratio_5m < 0.47:
                scores.append(40)
            else:
                scores.append(50)
            
            weights.append(0.30)
        
        # 3. 長期趨勢分析 (30分鐘) - 權重 20%
        if window_30min.total_volume > 0:
            buy_ratio_30m = window_30min.buy_volume / window_30min.total_volume
            
            if buy_ratio_30m > 0.55:
                scores.append(65)
            elif buy_ratio_30m > 0.52:
                scores.append(55)
            elif buy_ratio_30m < 0.45:
                scores.append(35)
            elif buy_ratio_30m < 0.48:
                scores.append(45)
            else:
                scores.append(50)
            
            weights.append(0.20)
        
        # 4. 爆量指標 - 權重 15%
        if volume_indicator.is_explosion:
            # 爆量時，看短期買賣方向
            if window_1min.total_volume > 0:
                if window_1min.buy_volume > window_1min.sell_volume:
                    scores.append(75)  # 爆量上攻
                else:
                    scores.append(25)  # 爆量下殺
            else:
                scores.append(50)
        else:
            scores.append(50)  # 正常量不加分
        
        weights.append(0.15)
        
        # 5. 期現價差 - 權重 10%
        if basis_analysis.is_contango:
            if basis_analysis.basis_pct > 0.5:
                scores.append(70)  # 強勢正價差
            elif basis_analysis.basis_pct > 0.2:
                scores.append(60)  # 正價差
            else:
                scores.append(55)
        else:
            if basis_analysis.basis_pct < -0.5:
                scores.append(30)  # 強勢逆價差
            elif basis_analysis.basis_pct < -0.2:
                scores.append(40)  # 逆價差
            else:
                scores.append(45)
        
        weights.append(0.10)
        
        # 計算加權平均分數
        if not scores:
            return 50.0, 50.0, "中性", 0.0
        
        weighted_score = sum(s * w for s, w in zip(scores, weights)) / sum(weights)
        
        # 轉換為多空比
        long_ratio = weighted_score
        short_ratio = 100 - weighted_score
        
        # 判定信號
        if long_ratio >= 70:
            signal = "強多"
        elif long_ratio >= 58:
            signal = "偏多"
        elif long_ratio <= 30:
            signal = "強空"
        elif long_ratio <= 42:
            signal = "偏空"
        else:
            signal = "中性"
        
        # 計算信心水準 (基於資料量)
        data_quality = min(100, (window_5min.tick_count / 50) * 100)  # 假設50筆為充分資料
        confidence = data_quality
        
        return long_ratio, short_ratio, signal, confidence
    
    def analyze(self, latest_tick: TickData) -> Optional[LongShortRatio]:
        """
        執行多空比分析
        
        Args:
            latest_tick: 最新的 Tick 資料
        
        Returns:
            LongShortRatio 分析結果；遲到的 tick 不納入分析，直接回傳上一次的結果
        """
        # 添加最新資料（遲到的 tick 略過，視窗統計依賴 tick 依時間遞增）
        if not self.add_tick(latest_tick):
            return self.latest_analysis

        # 取得各時間視窗統計快照（O(1)，累計值已在 add_tick 時增量更新）
        window_1min = self._window_1min.snapshot()
        window_5min = self._window_5min.snapshot()
        window_30min = self._window_30min.snapshot()
        
        # 計算爆量指標 (使用1分鐘視窗)
        volume_indicator = self._calculate_volume_indicator(window_1min.total_volume)
        
        # 計算期現價差
        basis_analysis = self._calculate_basis(latest_tick)
        
        # 計算市場情緒指標
        sentiment_indicator = self._calculate_sentiment(latest_tick, window_1min, window_5min)
        
        # 計算綜合多空比
        long_ratio, short_ratio, signal, confidence = self._calculate_long_short_ratio(
            window_1min, window_5min, window_30min,
            volume_indicator, basis_analysis
        )
        
        # 建立分析結果
        result = LongShortRatio(
            timestamp=latest_tick.datetime,
            window_1min=window_1min,
            window_5min=window_5min,
            window_30min=window_30min,
            volume_indicator=volume_indicator,
            basis_analysis=basis_analysis,
            sentiment_indicator=sentiment_indicator,
            long_ratio=long_ratio,
            short_ratio=short_ratio,
            signal=signal,
            confidence=confidence
        )
        
        # 儲存最新的分析結果
        self.latest_analysis = result
        
        return result
    
    def get_latest_analysis(self) -> Optional[LongShortRatio]:
        """取得最新的分析結果"""
        return self.latest_analysis
    
    def format_analysis(self, result: LongShortRatio) -> str:
        """格式化分析結果為可讀文字"""
        lines = [
            f"📊 多空比分析 ({result.timestamp.strftime('%Y-%m-%d %H:%M:%S')})",
            "=" * 60,
            "",
            f"🎯 綜合判斷: {result.signal}",
            f"   多方: {result.long_ratio:.1f}% | 空方: {result.short_ratio:.1f}%",
            f"   信心水準: {result.confidence:.0f}%",
            "",
            "📈 時間區間分析:",
            f"   1分鐘  → 買:{result.window_1min.buy_volume:>5} 賣:{result.window_1min.sell_volume:>5} "
            f"(比例 {result.window_1min.buy_sell_ratio:.2f}) "
            f"漲跌:{result.window_1min.price_change_pct:>+6.2f}%" if result.window_1min.price_change_pct else "",
            f"   5分鐘  → 買:{result.window_5min.buy_volume:>5} 賣:{result.window_5min.sell_volume:>5} "
            f"(比例 {result.window_5min.buy_sell_ratio:.2f}) "
            f"漲跌:{result.window_5min.price_change_pct:>+6.2f}%" if result.window_5min.price_change_pct else "",
            f"   30分鐘 → 買:{result.window_30min.buy_volume:>5} 賣:{result.window_30min.sell_volume:>5} "
            f"(比例 {result.window_30min.buy_sell_ratio:.2f}) "
            f"漲跌:{result.window_30min.price_change_pct:>+6.2f}%" if result.window_30min.price_change_pct else "",
            "",
            "💥 成交量指標:",
            f"   當前1分鐘量: {result.volume_indicator.current_volume:>6} 口",
            f"   今日平均量:   {result.volume_indicator.avg_volume_today:>6.1f} 口/分",
            f"   爆量比率:     {result.volume_indicator.explosion_ratio:>6.2f}x ({result.volume_indicator.explosion_level})",
            "",
            "📐 期現價差:",
            f"   期貨價: {result.basis_analysis.futures_price}",
            f"   現貨價: {result.basis_analysis.spot_price}",
            f"   價差:   {result.basis_analysis.basis:>+8} ({result.basis_analysis.basis_pct:>+6.2f}%)",
            f"   信號:   {result.basis_analysis.trend_signal}",
            "",
            "😊 市場情緒:",
            f"   綜合情緒: {result.sentiment_indicator.sentiment_label} ({result.sentiment_indicator.sentiment_score:.1f}分)",
            f"   波動程度: {result.sentiment_indicator.volatility_level}",
            "=" * 60,
        ]
        return "\n".join(line for line in lines if line is not None)


__all__ = [
    "TickData",
    "TimeWindowStats",
    "VolumeExplosionIndicator",
    "BasisAnalysis",
    "SentimentIndicator",
    "LongShortRatio",
    "LongShortAnalyzer",
]
