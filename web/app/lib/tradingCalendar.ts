/**
 * 台指期交易日判斷（含國定假日）
 *
 * 邏輯與後端 apps/libs/trading-calendar 的 is_trading_day 一致：
 * 週一到週五且非休市日。休市日（國定假日、補假、春節與例外檔）由後端匯出為
 * tradingCalendar.data.json，每年年初請重新執行匯出：
 *   cd apps/libs/trading-calendar
 *   uv run python -m trading_calendar.export_calendar --output ../../../web/app/lib/tradingCalendar.data.json
 */

interface TradingCalendarData {
  startYear: number;
  endYear: number;
  closedDays: string[];
}

/**
 * 讀取後端匯出的休市日資料。
 * 本機開發可能忘了執行匯出，檔案缺失時不讓整個前端壞掉，改為只判斷週末並提示。
 */
const loadCalendarData = (): TradingCalendarData | null => {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('./tradingCalendar.data.json') as TradingCalendarData;
  } catch {
    console.warn(
      '⚠️ 找不到 tradingCalendar.data.json，國定假日會被當成交易日，請在 web/ 執行 npm run export:calendar'
    );
    return null;
  }
};

const calendarData = loadCalendarData();
const CLOSED_DAYS: ReadonlySet<string> = new Set(calendarData?.closedDays ?? []);

/** 往前找交易日的安全上限（最長連假約 9 天） */
const MAX_LOOKBACK_DAYS = 31;

let hasWarnedOutOfRange = false;

const warnOutOfRange = (year: number): void => {
  if (hasWarnedOutOfRange) return;
  hasWarnedOutOfRange = true;
  console.warn(
    `⚠️ 交易日曆資料只涵蓋 ${calendarData?.startYear}-${calendarData?.endYear}，${year} 年僅能判斷週末，請重新匯出 tradingCalendar.data.json`
  );
};

/** 將 Date 轉成瀏覽器本地時區的 YYYY-MM-DD */
export const toDateKey = (date: Date): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

/**
 * 以 YYYY-MM-DD 判斷是否為交易日：週一到週五且非休市日。
 * 資料缺失或年度超出範圍時只能判斷週末（寧可多顯示，不要把交易日當成休市日）。
 */
export const isTradingDateKey = (dateKey: string): boolean => {
  const [year, month, day] = dateKey.split('-').map(Number);
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay(); // 0=週日, 6=週六
  if (weekday === 0 || weekday === 6) {
    return false;
  }

  // 沒有資料（檔案缺失）時只能判斷週末，載入時已提示過
  if (!calendarData) {
    return true;
  }

  if (year < calendarData.startYear || year > calendarData.endYear) {
    warnOutOfRange(year);
    return true;
  }

  return !CLOSED_DAYS.has(dateKey);
};

/** 是否為交易日（以瀏覽器本地時區的日期判斷） */
export const isTradingDay = (date: Date): boolean => isTradingDateKey(toDateKey(date));

/**
 * 獲取最近的交易日（含傳入當天）
 * @param date 基準日期
 * @returns 最近的交易日（保留原本的時分秒）
 */
export const getLastTradingDay = (date: Date): Date => {
  const result = new Date(date);
  for (let i = 0; i < MAX_LOOKBACK_DAYS && !isTradingDay(result); i += 1) {
    result.setDate(result.getDate() - 1);
  }
  return result;
};

/**
 * 從指定日期往前推算 N 個交易日（略過週末與國定假日）
 * @param date 基準日期
 * @param daysBack 往前的交易日數
 */
export const getDateOffsetTradingDays = (date: Date, daysBack: number): Date => {
  const result = new Date(date);
  let remaining = daysBack;
  while (remaining > 0) {
    result.setDate(result.getDate() - 1);
    if (isTradingDay(result)) {
      remaining -= 1;
    }
  }
  return result;
};
