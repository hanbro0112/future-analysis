const TAIPEI_TIME_FORMATTER = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Taipei',
  weekday: 'short',
  hour: 'numeric',
  minute: 'numeric',
  hourCycle: 'h23',
});

/**
 * 判斷指定時間是否在交易時段，恆以 Asia/Taipei 時區判斷（不受瀏覽器所在時區影響），
 * 與後端 price-broadcaster 的 is_trading_hours() 判斷邏輯一致：
 * - 日盤：週一到週五 8:45-13:45
 * - 夜盤：週一到週四 15:00-次日 5:00，週五 15:00-23:59
 *
 * @param now 要檢查的時間，預設為目前時間
 */
export const isInTradingHours = (now: Date = new Date()): boolean => {
  const parts = TAIPEI_TIME_FORMATTER.formatToParts(now);
  const part = (type: string) => parts.find((p) => p.type === type)?.value ?? '';

  const weekday = part('weekday'); // 'Mon' | 'Tue' | 'Wed' | 'Thu' | 'Fri' | 'Sat' | 'Sun'
  const totalMinutes = Number(part('hour')) * 60 + Number(part('minute'));

  // 週末不交易
  if (weekday === 'Sat' || weekday === 'Sun') {
    return false;
  }

  const daySessionStart = 8 * 60 + 45; // 08:45
  const daySessionEnd = 13 * 60 + 45; // 13:45
  const nightSessionStart = 15 * 60; // 15:00
  const nightSessionEnd = 5 * 60; // 05:00

  // 日盤：8:45-13:45
  if (totalMinutes >= daySessionStart && totalMinutes <= daySessionEnd) {
    return true;
  }

  // 夜盤：15:00-次日 5:00
  // 週一到週四的夜盤可以延續到次日（週二到週五凌晨）
  if (weekday === 'Mon' || weekday === 'Tue' || weekday === 'Wed' || weekday === 'Thu') {
    if (totalMinutes >= nightSessionStart || totalMinutes <= nightSessionEnd) {
      return true;
    }
  }

  // 週五處理：
  // - 凌晨 0:00-5:00：週四夜盤的延續
  // - 日盤時段：已在上面處理
  // - 15:00-23:59：週五夜盤（不延續到週六）
  if (weekday === 'Fri') {
    if (totalMinutes <= nightSessionEnd || totalMinutes >= nightSessionStart) {
      return true;
    }
  }

  return false;
};
