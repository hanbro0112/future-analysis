import { isTradingDateKey } from './tradingCalendar';

const TAIPEI_TIME_FORMATTER = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Taipei',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: 'numeric',
  minute: 'numeric',
  hourCycle: 'h23',
});

/** 取得 YYYY-MM-DD 前一天的 YYYY-MM-DD（純日期運算，不受瀏覽器時區影響） */
const getPreviousDateKey = (dateKey: string): string => {
  const [year, month, day] = dateKey.split('-').map(Number);
  const previous = new Date(Date.UTC(year, month - 1, day - 1));
  const mm = String(previous.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(previous.getUTCDate()).padStart(2, '0');
  return `${previous.getUTCFullYear()}-${mm}-${dd}`;
};

/**
 * 判斷指定時間是否在交易時段，恆以 Asia/Taipei 時區判斷（不受瀏覽器所在時區影響），
 * 與後端 trading_calendar 的 is_session_open() 判斷邏輯一致（含國定假日）：
 * - 日盤：交易日 8:45-13:45
 * - 夜盤：交易日 15:00-次日 5:00（凌晨延續段是否開盤，取決於「前一天」是否為交易日，
 *   因此週五夜盤延續至週六凌晨 5:00，休市日前一晚的夜盤也照常，休市日當天則不開盤）
 *
 * 交易日 = 週一到週五且非休市日（休市日資料見 tradingCalendar）
 *
 * @param now 要檢查的時間，預設為目前時間
 */
export const isInTradingHours = (now: Date = new Date()): boolean => {
  const parts = TAIPEI_TIME_FORMATTER.formatToParts(now);
  const part = (type: string) => parts.find((p) => p.type === type)?.value ?? '';

  const dateKey = `${part('year')}-${part('month')}-${part('day')}`;
  const totalMinutes = Number(part('hour')) * 60 + Number(part('minute'));

  const daySessionStart = 8 * 60 + 45; // 08:45
  const daySessionEnd = 13 * 60 + 45; // 13:45
  const nightSessionStart = 15 * 60; // 15:00
  const nightSessionEnd = 5 * 60; // 05:00

  // 凌晨 0:00-5:00：若前一天是交易日，屬於該日夜盤的延續
  // （週五夜盤會延續到週六凌晨，因此週六 0:00-5:00 仍屬交易時段）
  if (totalMinutes <= nightSessionEnd && isTradingDateKey(getPreviousDateKey(dateKey))) {
    return true;
  }

  // 休市日（週末與國定假日）不會有新的日盤或夜盤開盤
  if (!isTradingDateKey(dateKey)) {
    return false;
  }

  // 日盤：8:45-13:45
  if (totalMinutes >= daySessionStart && totalMinutes <= daySessionEnd) {
    return true;
  }

  // 夜盤開盤：15:00 之後
  return totalMinutes >= nightSessionStart;
};
