/**
 * 分鐘級資料類型定義
 */

/**
 * 分析結果
 */
export interface AnalysisResult {
  signal: string // 多空信號: "強多", "偏多", "中性", "偏空", "強空"
  long_ratio: number // 多方比例
  short_ratio: number // 空方比例
  confidence: number // 信心水準
  volume_explosion_level: string // 爆量等級
  sentiment_label: string // 市場情緒標籤
  sentiment_score: number // 市場情緒分數
  basis: number // 期現價差
  basis_pct: number // 期現價差百分比
}

/**
 * 分鐘級資料
 */
export interface MinuteBar {
  code: string // 商品代碼
  timestamp: string // 時間戳記
  date: string // 日期 YYYY-MM-DD
  time: string // 時間 HH:mm
  market_type: 'regular' | 'after_hours' // 市場類型
  open: number // 開盤價
  high: number // 最高價
  low: number // 最低價
  close: number // 收盤價
  volume: number // 成交量
  buy_volume: number // 買方成交量
  sell_volume: number // 賣方成交量
  avg_price: number // 平均價格
  tick_count: number // tick 數量
  bid_total: number // 委買總量
  ask_total: number // 委賣總量
  analysis?: AnalysisResult // 分析結果（可選）
}

/**
 * 圖表資料點（用於繪圖）
 */
export interface MinuteChartPoint {
  time: string // 時間 HH:mm
  avg_price: number // 平均價格（主線）
  high: number // 最高價
  low: number // 最低價
  volume: number // 成交量
  buy_volume: number // 買方成交量
  sell_volume: number // 賣方成交量
  taiex?: number // 加權指數（從期現價差計算，僅日盤）
}
