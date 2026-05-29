"""
多空比分析策略
基於成交量、成交價、期現價差進行多空判斷
"""
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
        self.close_price = tick.close
        
        # 更新最高最低價
        if self.high_price is None or tick.close > self.high_price:
            self.high_price = tick.close
        if self.low_price is None or tick.close < self.low_price:
            self.low_price = tick.close
        
        # 根據內外盤分類
        if tick.tick_type == 1:  # 外盤 (買進)
            self.buy_volume += tick.volume
            self.buy_amount += tick.amount
        elif tick.tick_type == 2:  # 內盤 (賣出)
            self.sell_volume += tick.volume
            self.sell_amount += tick.amount
    
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
                return "強勢正價差 (偏多)"
            return "正價差 (偏多)"
        else:
            if self.basis_pct < -0.5:
                return "強勢逆價差 (偏空)"
            return "逆價差 (偏空)"


@dataclass
class SentimentIndicator:
    """市場情緒指標"""
    bid_ask_ratio: float  # 委買委賣比 (委買量/委賣量)
    continuous_direction: int  # 連續方向 (正數=連續外盤, 負數=連續內盤)
    momentum_score: float  # 動能分數 (0-100, 50為中性)
    volatility_level: str  # 波動程度: "極低", "低", "正常", "高", "極高"
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


class LongShortAnalyzer:
    """多空比分析器"""
    
    def __init__(self):
        # 維護不同時間視窗的資料
        self.ticks_1min: deque = deque()
        self.ticks_5min: deque = deque()
        self.ticks_30min: deque = deque()
        
        # 當天所有 Tick (用於計算平均)
        self.today_ticks: List[TickData] = []
        self.current_date: Optional[datetime] = None
    
    def add_tick(self, tick: TickData):
        """添加新的 Tick 資料"""
        # 檢查是否跨日，若是則重置當天資料
        if self.current_date is None or tick.datetime.date() != self.current_date:
            self.today_ticks.clear()
            self.current_date = tick.datetime.date()
        
        self.today_ticks.append(tick)
        
        # 添加到各時間視窗
        self.ticks_1min.append(tick)
        self.ticks_5min.append(tick)
        self.ticks_30min.append(tick)
        
        # 移除過期資料
        self._cleanup_expired_ticks(tick.datetime)
    
    def _cleanup_expired_ticks(self, current_time: datetime):
        """清理過期的 Tick 資料"""
        # 1分鐘視窗
        cutoff_1min = current_time - timedelta(minutes=1)
        while self.ticks_1min and self.ticks_1min[0].datetime < cutoff_1min:
            self.ticks_1min.popleft()
        
        # 5分鐘視窗
        cutoff_5min = current_time - timedelta(minutes=5)
        while self.ticks_5min and self.ticks_5min[0].datetime < cutoff_5min:
            self.ticks_5min.popleft()
        
        # 30分鐘視窗
        cutoff_30min = current_time - timedelta(minutes=30)
        while self.ticks_30min and self.ticks_30min[0].datetime < cutoff_30min:
            self.ticks_30min.popleft()
    
    def _calculate_window_stats(self, ticks: deque, duration_minutes: int) -> TimeWindowStats:
        """計算時間視窗統計資料"""
        stats = TimeWindowStats(duration_minutes=duration_minutes)
        for tick in ticks:
            stats.add_tick(tick)
        return stats
    
    def _calculate_volume_indicator(self, current_volume: int) -> VolumeExplosionIndicator:
        """計算成交量爆量指標"""
        # 計算當天平均成交量 (每分鐘)
        if not self.today_ticks or len(self.today_ticks) < 2:
            avg_volume = current_volume
        else:
            # 計算時間範圍
            time_span = (self.today_ticks[-1].datetime - self.today_ticks[0].datetime).total_seconds() / 60
            if time_span < 1:
                time_span = 1
            
            # 總成交量 / 時間 = 每分鐘平均成交量
            total_vol = sum(tick.volume for tick in self.today_ticks)
            avg_volume = total_vol / time_span
        
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
        continuous_direction = 0
        if len(self.ticks_1min) >= 2:
            direction = 0
            for tick in reversed(self.ticks_1min):
                if tick.tick_type == 1:  # 外盤
                    if direction >= 0:
                        direction += 1
                    else:
                        break
                elif tick.tick_type == 2:  # 內盤
                    if direction <= 0:
                        direction -= 1
                    else:
                        break
            continuous_direction = direction
        
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
            LongShortRatio 分析結果
        """
        # 添加最新資料
        self.add_tick(latest_tick)
        
        # 計算各時間視窗統計
        window_1min = self._calculate_window_stats(self.ticks_1min, 1)
        window_5min = self._calculate_window_stats(self.ticks_5min, 5)
        window_30min = self._calculate_window_stats(self.ticks_30min, 30)
        
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
        
        return LongShortRatio(
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
