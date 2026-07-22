/**
 * 判斷當前是否在交易時段
 */
export const isInTradingHours = (): boolean => {
  const now = new Date();
  const day = now.getDay(); // 0 = 週日, 1 = 週一, ..., 6 = 週六
  const hours = now.getHours();
  const minutes = now.getMinutes();
  const totalMinutes = hours * 60 + minutes;

  // 時段定義
  const daySessionStart = 8 * 60 + 45; // 08:45 (525 分鐘)
  const daySessionEnd = 13 * 60 + 48; // 13:48 (828 分鐘) - 延後 3 分鐘以更新最後一筆
  const nightSessionStart = 15 * 60; // 15:00 (900 分鐘)
  const nightSessionEnd = 5 * 60 + 3; // 05:03 (303 分鐘) - 延後 3 分鐘以更新最後一筆

  // 週六：只有 00:00-05:03 算是週五夜盤的延續
  if (day === 6) {
    return totalMinutes < nightSessionEnd;
  }

  // 週日：只有夜盤（15:00 開始）
  if (day === 0) {
    return totalMinutes >= nightSessionStart;
  }

  // 週一至週五
  // 判斷是否在交易時段
  if (totalMinutes >= daySessionStart && totalMinutes <= daySessionEnd) {
    // 日盤時段
    return true;
  } else if (totalMinutes >= nightSessionStart || totalMinutes < nightSessionEnd) {
    // 夜盤時段（15:00 之後或 05:03 之前）
    return true;
  }

  // 其他時間不在交易時段
  return false;
};
