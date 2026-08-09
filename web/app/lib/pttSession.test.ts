import { getCurrentPttSession, getPttSessionDate } from './pttSession';

// 2026-08-06 台北時間為週四，2026-08-07 為週五，2026-08-08/09 為週六/週日，2026-08-10 為週一

describe('getCurrentPttSession', () => {
  it('台北時間 02:00（凌晨）應判定為盤後閒聊', () => {
    expect(getCurrentPttSession(new Date('2026-08-06T18:00:00Z'))).toBe('afterhours');
  });

  it('台北時間 08:29 應判定為盤後閒聊（當天盤中閒聊還沒發文）', () => {
    expect(getCurrentPttSession(new Date('2026-08-06T00:29:00Z'))).toBe('afterhours');
  });

  it('台北時間 08:30 應判定為盤中閒聊', () => {
    expect(getCurrentPttSession(new Date('2026-08-06T00:30:00Z'))).toBe('intraday');
  });

  it('台北時間 13:59 應判定為盤中閒聊', () => {
    expect(getCurrentPttSession(new Date('2026-08-06T05:59:00Z'))).toBe('intraday');
  });

  it('台北時間 14:00 應判定為盤後閒聊', () => {
    expect(getCurrentPttSession(new Date('2026-08-06T06:00:00Z'))).toBe('afterhours');
  });

  it('台北時間 22:00 應判定為盤後閒聊', () => {
    expect(getCurrentPttSession(new Date('2026-08-06T14:00:00Z'))).toBe('afterhours');
  });

  it('假日（週六、週日）整天應判定為盤後閒聊', () => {
    // 台北時間 2026-08-08 週六 10:00
    expect(getCurrentPttSession(new Date('2026-08-08T02:00:00Z'))).toBe('afterhours');
    // 台北時間 2026-08-09 週日 20:00
    expect(getCurrentPttSession(new Date('2026-08-09T12:00:00Z'))).toBe('afterhours');
  });

  it('不受瀏覽器所在時區影響，恆以 Asia/Taipei 判斷', () => {
    const originalTZ = process.env.TZ;
    process.env.TZ = 'America/Los_Angeles';

    try {
      expect(getCurrentPttSession(new Date('2026-08-06T00:30:00Z'))).toBe('intraday');
    } finally {
      process.env.TZ = originalTZ;
    }
  });
});

describe('getPttSessionDate', () => {
  it('盤中分頁在 08:30 前應回傳前一天日期', () => {
    // 台北時間 2026-08-07 02:00
    expect(getPttSessionDate('intraday', new Date('2026-08-06T18:00:00Z'))).toBe('20260806');
  });

  it('盤中分頁在 08:30 後應回傳當天日期', () => {
    // 台北時間 2026-08-07 09:00
    expect(getPttSessionDate('intraday', new Date('2026-08-07T01:00:00Z'))).toBe('20260807');
  });

  it('盤後分頁在 14:00 前應回傳前一天日期（延續凌晨的盤後閒聊）', () => {
    // 台北時間 2026-08-07 02:00
    expect(getPttSessionDate('afterhours', new Date('2026-08-06T18:00:00Z'))).toBe('20260806');
  });

  it('盤後分頁在 14:00 後應回傳當天日期', () => {
    // 台北時間 2026-08-07 14:00
    expect(getPttSessionDate('afterhours', new Date('2026-08-07T06:00:00Z'))).toBe('20260807');
  });

  it('跨月時日期換算正確', () => {
    // 台北時間 2026-09-01 02:00，前一天應為 2026-08-31
    expect(getPttSessionDate('afterhours', new Date('2026-08-31T18:00:00Z'))).toBe('20260831');
  });

  it('週六白天手動查盤後閒聊，應該對應到最近的交易日（週五）', () => {
    // 台北時間 2026-08-08 週六 15:00
    expect(getPttSessionDate('afterhours', new Date('2026-08-08T07:00:00Z'))).toBe('20260807');
  });

  it('週五盤後閒聊應該一路延續到週一 08:30，凌晨仍要能查到週五的日期', () => {
    // 台北時間 2026-08-10 週一 02:00
    expect(getPttSessionDate('afterhours', new Date('2026-08-09T18:00:00Z'))).toBe('20260807');
  });
});
