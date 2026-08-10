import { isInTradingHours } from './tradingHours';

describe('isInTradingHours', () => {
  it('日盤中（週一 台北時間 10:30）應判定為交易時段', () => {
    // 2026-07-27 為週一
    expect(isInTradingHours(new Date('2026-07-27T02:30:00Z'))).toBe(true);
  });

  it('夜盤中（週一 台北時間 16:30）應判定為交易時段', () => {
    expect(isInTradingHours(new Date('2026-07-27T08:30:00Z'))).toBe(true);
  });

  it('盤前休市（週一 台北時間 07:00）應判定為非交易時段', () => {
    expect(isInTradingHours(new Date('2026-07-26T23:00:00Z'))).toBe(false);
  });

  it('週六（台北時間 12:00）應判定為非交易時段', () => {
    // 2026-08-01 為週六
    expect(isInTradingHours(new Date('2026-08-01T04:00:00Z'))).toBe(false);
  });

  it('週五夜盤延續到週六凌晨，週六凌晨（台北時間 02:00）應判定為交易時段', () => {
    expect(isInTradingHours(new Date('2026-07-31T18:00:00Z'))).toBe(true);
  });

  it('週五夜盤延續結束後，週六（台北時間 05:01）應判定為非交易時段', () => {
    expect(isInTradingHours(new Date('2026-07-31T21:01:00Z'))).toBe(false);
  });

  it('週日全天不會有新夜盤開盤，週日（台北時間 16:30）應判定為非交易時段', () => {
    // 2026-08-02 為週日
    expect(isInTradingHours(new Date('2026-08-02T08:30:00Z'))).toBe(false);
  });

  it('日盤收盤邊界：台北時間 13:45 為交易時段、13:46 起為非交易時段（與後端一致，無緩衝）', () => {
    expect(isInTradingHours(new Date('2026-07-27T05:45:00Z'))).toBe(true);
    expect(isInTradingHours(new Date('2026-07-27T05:46:00Z'))).toBe(false);
  });

  it('夜盤收盤邊界：台北時間 05:00 為交易時段、05:01 起為非交易時段（與後端一致，無緩衝）', () => {
    // 2026-07-28 為週二，凌晨延續自週一夜盤
    expect(isInTradingHours(new Date('2026-07-27T21:00:00Z'))).toBe(true);
    expect(isInTradingHours(new Date('2026-07-27T21:01:00Z'))).toBe(false);
  });

  it('不受瀏覽器所在時區影響，恆以 Asia/Taipei 判斷', () => {
    const originalTZ = process.env.TZ;
    process.env.TZ = 'America/Los_Angeles';

    try {
      // 台北時間週一 10:30（日盤中）
      expect(isInTradingHours(new Date('2026-07-27T02:30:00Z'))).toBe(true);
    } finally {
      process.env.TZ = originalTZ;
    }
  });
});
