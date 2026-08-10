import type { PttSession } from '../types/pttChat';

const TAIPEI_TIME_FORMATTER = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Taipei',
  weekday: 'short',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: 'numeric',
  minute: 'numeric',
  hourCycle: 'h23',
});

// 台股現股時段時間，與後端 ptt_chat.py 的常數一致
const CASH_MARKET_OPEN_MINUTES = 8 * 60 + 30; // 08:30，盤中閒聊開始
const CASH_MARKET_CLOSE_MINUTES = 14 * 60; // 14:00，盤後閒聊開始

interface TaipeiNow {
  year: number;
  month: number;
  day: number;
  weekday: string; // 'Mon' | 'Tue' | 'Wed' | 'Thu' | 'Fri' | 'Sat' | 'Sun'
  totalMinutes: number;
}

const getTaipeiNow = (now: Date): TaipeiNow => {
  const parts = TAIPEI_TIME_FORMATTER.formatToParts(now);
  const part = (type: string) => parts.find((p) => p.type === type)?.value ?? '';

  return {
    year: Number(part('year')),
    month: Number(part('month')),
    day: Number(part('day')),
    weekday: part('weekday'),
    totalMinutes: Number(part('hour')) * 60 + Number(part('minute')),
  };
};

const shiftDate = (taipeiNow: TaipeiNow, dayOffset: number): Date =>
  // 用 UTC 建構日期避免瀏覽器本地時區在日期加減時受 DST 影響
  new Date(Date.UTC(taipeiNow.year, taipeiNow.month - 1, taipeiNow.day + dayOffset));

/** 若日期落在週末，往前推到最近的週五（不含國定假日判斷） */
const toLastTradingDay = (date: Date): Date => {
  const weekday = date.getUTCDay(); // 0=Sun ... 6=Sat
  if (weekday === 6) {
    return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() - 1));
  }
  if (weekday === 0) {
    return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() - 2));
  }
  return date;
};

const formatYYYYMMDD = (date: Date): string => {
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, '0');
  const day = String(date.getUTCDate()).padStart(2, '0');
  return `${year}${month}${day}`;
};

/**
 * 依現在時間判斷目前預設要顯示盤中還是盤後閒聊，恆以 Asia/Taipei 時區判斷
 * - 週六、週日：整天延續盤後閒聊（假日沒有盤中閒聊）
 * - 平日 00:00-08:29（凌晨，延續前一天的盤後閒聊，因為當天盤中閒聊還沒發文）=> afterhours
 * - 平日 08:30-13:59 => intraday
 * - 平日 14:00-23:59 => afterhours
 * @param now 要檢查的時間，預設為目前時間
 */
export const getCurrentPttSession = (now: Date = new Date()): PttSession => {
  const taipeiNow = getTaipeiNow(now);

  if (taipeiNow.weekday === 'Sat' || taipeiNow.weekday === 'Sun') {
    return 'afterhours';
  }
  if (taipeiNow.totalMinutes < CASH_MARKET_OPEN_MINUTES) {
    return 'afterhours';
  }
  return taipeiNow.totalMinutes < CASH_MARKET_CLOSE_MINUTES ? 'intraday' : 'afterhours';
};

/**
 * 依現在時間與指定分頁，判斷該分頁對應的閒聊日期（YYYYMMDD），恆以 Asia/Taipei 時區判斷
 * 兩個分頁各自的「今天文章還沒發文」判斷時間點不同（盤中 08:30 / 盤後 14:00），
 * 未到發文時間前延續前一天的日期；算出來的日期若落在週末，再往前推到最近的交易日（週五），
 * 所以週五盤後閒聊會一路延續到週一 08:30
 * @param session 'intraday' | 'afterhours'
 * @param now 要檢查的時間，預設為目前時間
 */
export const getPttSessionDate = (session: PttSession, now: Date = new Date()): string => {
  const taipeiNow = getTaipeiNow(now);
  const cutoffMinutes = session === 'intraday' ? CASH_MARKET_OPEN_MINUTES : CASH_MARKET_CLOSE_MINUTES;
  const dayOffset = taipeiNow.totalMinutes < cutoffMinutes ? -1 : 0;

  return formatYYYYMMDD(toLastTradingDay(shiftDate(taipeiNow, dayOffset)));
};
