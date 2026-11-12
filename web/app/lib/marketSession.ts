/**
 * 盤別（日盤／夜盤）顯示規則
 *
 * 一律以 Asia/Taipei 時區判斷（不受瀏覽器所在時區影響），交易日含國定假日：
 * - 交易日 08:45 ≤ 時間 ≤ 14:50：顯示「當天日盤」
 * - 交易日 08:45 前：顯示「前一個交易日的夜盤」
 * - 交易日 14:50 後：顯示「當天夜盤」（尚未開盤、沒有資料也照樣顯示空盤）
 * - 週末與國定假日：顯示「前一個交易日的夜盤」
 *   （「沒有資料的盤改顯示前一個交易日」只發生在休市日，由日期推算而來）
 */
import {
  getLastTradingDateKey,
  getPreviousDateKey,
  getPreviousTradingDateKey,
  isTradingDateKey,
} from './tradingCalendar';

export type MarketType = 'regular' | 'after_hours';

/** 日盤開始：08:45 */
export const DAY_SESSION_START_MINUTES = 8 * 60 + 45;
/** 日盤畫面顯示的最後一分鐘：14:50（含），14:51 起改顯示當天夜盤 */
export const DAY_SESSION_LAST_MINUTES = 14 * 60 + 50;
/** 日盤日期換日點：08:30 前仍使用前一個交易日 */
const DAY_SESSION_DATE_ROLLOVER_MINUTES = 8 * 60 + 30;

const TAIPEI_TIME_FORMATTER = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Taipei',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: 'numeric',
  minute: 'numeric',
  hourCycle: 'h23',
});

export interface TaipeiClock {
  /** 台北時區的日期 YYYY-MM-DD */
  dateKey: string;
  /** 台北時區當天經過的分鐘數（0-1439） */
  totalMinutes: number;
}

/** 取得指定時間在台北時區的日期與當天分鐘數 */
export const getTaipeiClock = (now: Date = new Date()): TaipeiClock => {
  const parts = TAIPEI_TIME_FORMATTER.formatToParts(now);
  const part = (type: string): string => parts.find((p) => p.type === type)?.value ?? '';

  return {
    dateKey: `${part('year')}-${part('month')}-${part('day')}`,
    totalMinutes: Number(part('hour')) * 60 + Number(part('minute')),
  };
};

/** 目前應顯示的預設盤別 */
export const getDefaultMarketType = (now: Date = new Date()): MarketType => {
  const { dateKey, totalMinutes } = getTaipeiClock(now);

  if (!isTradingDateKey(dateKey)) {
    return 'after_hours';
  }

  return totalMinutes >= DAY_SESSION_START_MINUTES && totalMinutes <= DAY_SESSION_LAST_MINUTES
    ? 'regular'
    : 'after_hours';
};

/** 日盤對應的交易日（YYYY-MM-DD）：08:30 前使用前一個交易日，休市日使用最近交易日 */
export const getDaySessionDateKey = (now: Date = new Date()): string => {
  const { dateKey, totalMinutes } = getTaipeiClock(now);
  const base = totalMinutes < DAY_SESSION_DATE_ROLLOVER_MINUTES ? getPreviousDateKey(dateKey) : dateKey;
  return getLastTradingDateKey(base);
};

/**
 * 夜盤對應的交易日（YYYY-MM-DD）：
 * - 14:50（含）以前使用前一個交易日的夜盤
 * - 14:51 起使用當天的夜盤；休市日使用最近交易日的夜盤
 */
export const getNightSessionDateKey = (now: Date = new Date()): string => {
  const { dateKey, totalMinutes } = getTaipeiClock(now);
  const base = totalMinutes <= DAY_SESSION_LAST_MINUTES ? getPreviousDateKey(dateKey) : dateKey;
  return getLastTradingDateKey(base);
};

/** YYYY-MM-DD 轉成 Firestore 集合使用的 YYYYMMDD */
export const toCompactDateKey = (dateKey: string): string => dateKey.replace(/-/g, '');

export interface ReferencePriceDates {
  /** 日盤參考價：前一個交易日日盤收盤（YYYYMMDD） */
  day: string;
  /** 夜盤參考價：夜盤所屬交易日當天的日盤收盤（YYYYMMDD） */
  night: string;
}

/** 目前日盤／夜盤各自參考價要讀取的日期，換日或換盤時會跟著改變 */
export const getReferencePriceDates = (now: Date = new Date()): ReferencePriceDates => ({
  day: toCompactDateKey(getPreviousTradingDateKey(getDaySessionDateKey(now))),
  night: toCompactDateKey(getNightSessionDateKey(now)),
});

export interface PollingGateInput {
  /** WebSocket 是否連線中 */
  wsConnected: boolean;
  /** 使用者是否手動選擇過盤別 */
  isMarketTypeManuallySelected: boolean;
  /** 目前是否在交易時段 */
  inTradingHours: boolean;
  /** 畫面上的盤別是否與預設盤別不同（需要切換） */
  marketTypeSwitchPending: boolean;
  /** 參考價日期是否已改變（需要重新取得） */
  referenceDatesChanged: boolean;
}

/**
 * 歷史資料輪詢是否可以略過：
 * WebSocket 連線正常、沒手動選盤別且不在交易時段時有即時資料可用，不必輪詢；
 * 但盤別需要切換或參考價日期已改變時（例如 14:50 切到尚未開盤的夜盤）仍必須執行一次。
 */
export const shouldSkipHistoryPolling = ({
  wsConnected,
  isMarketTypeManuallySelected,
  inTradingHours,
  marketTypeSwitchPending,
  referenceDatesChanged,
}: PollingGateInput): boolean =>
  wsConnected &&
  !isMarketTypeManuallySelected &&
  !inTradingHours &&
  !marketTypeSwitchPending &&
  !referenceDatesChanged;
