/**
 * 台指期資料結構型別定義
 */

/** 價格資料點 */
export interface PricePoint {
  /** 時間戳記 */
  timestamp: Date;
  /** 價格 */
  price: number;
}

/** 台指期即時報價 */
export interface TaifexQuote {
  /** 商品代碼 */
  symbol: string;
  /** 商品名稱 */
  name: string;
  /** 最新價 */
  lastPrice: number;
  /** 開盤價 */
  openPrice: number;
  /** 最高價 */
  highPrice: number;
  /** 最低價 */
  lowPrice: number;
  /** 成交量 */
  volume: number;
  /** 漲跌 */
  change: number;
  /** 漲跌幅 (%) */
  changePercent: number;
  /** 更新時間 */
  updateTime: Date;
}

/** 歷史價格資料 */
export interface HistoricalData {
  /** 商品代碼 */
  symbol: string;
  /** 價格序列 */
  priceData: PricePoint[];
}
