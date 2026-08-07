const TAIPEI_TIME_FORMATTER = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Taipei',
  weekday: 'short',
  hour: 'numeric',
  minute: 'numeric',
  hourCycle: 'h23',
});

const WEEKDAY_INDEX: Record<string, number> = {
  Sun: 0,
  Mon: 1,
  Tue: 2,
  Wed: 3,
  Thu: 4,
  Fri: 5,
  Sat: 6,
};

/**
 * 判斷指定時間是否在交易時段，恆以 Asia/Taipei 時區判斷（不受瀏覽器所在時區影響），
 * 與後端 price-broadcaster 的 is_trading_hours() 判斷邏輯一致：
 * - 日盤：週一到週五 8:45-13:45
 * - 夜盤：週一到週五 15:00-次日 5:00（週五夜盤延續至週六凌晨 5:00，週六、週日無新夜盤開盤）
 *
 * @param now 要檢查的時間，預設為目前時間
 */
export const isInTradingHours = (now: Date = new Date()): boolean => {
  const parts = TAIPEI_TIME_FORMATTER.formatToParts(now);
  const part = (type: string) => parts.find((p) => p.type === type)?.value ?? '';

  const weekday = part('weekday'); // 'Mon' | 'Tue' | 'Wed' | 'Thu' | 'Fri' | 'Sat' | 'Sun'
  const weekdayIndex = WEEKDAY_INDEX[weekday] ?? 0; // 0=週日, ..., 6=週六
  const totalMinutes = Number(part('hour')) * 60 + Number(part('minute'));

  const daySessionStart = 8 * 60 + 45; // 08:45
  const daySessionEnd = 13 * 60 + 45; // 13:45
  const nightSessionStart = 15 * 60; // 15:00
  const nightSessionEnd = 5 * 60; // 05:00

  // 凌晨 0:00-5:00：若前一天是週一到週五，屬於該日夜盤的延續
  // （週五夜盤會延續到週六凌晨，因此週六 0:00-5:00 仍屬交易時段）
  if (totalMinutes <= nightSessionEnd) {
    const prevWeekdayIndex = (weekdayIndex + 6) % 7; // 前一天
    if (prevWeekdayIndex >= 1 && prevWeekdayIndex <= 5) {
      return true;
    }
  }

  // 週末（週六、週日）不會有新的日盤或夜盤開盤
  if (weekday === 'Sat' || weekday === 'Sun') {
    return false;
  }

  // 日盤：8:45-13:45
  if (totalMinutes >= daySessionStart && totalMinutes <= daySessionEnd) {
    return true;
  }

  // 夜盤開盤：15:00 之後
  if (totalMinutes >= nightSessionStart) {
    return true;
  }

  return false;
};
