import {
  getDaySessionDateKey,
  getDefaultMarketType,
  getNightSessionDateKey,
  getReferencePriceDates,
  getTaipeiClock,
  shouldSkipHistoryPolling,
  toCompactDateKey,
  type PollingGateInput,
} from './marketSession';

/** 以台北時間建立 Date，測試結果不受執行環境時區影響 */
const taipei = (isoLocal: string): Date => new Date(`${isoLocal}+08:00`);

// 2026-11-09 週一、2026-11-11 週三、2026-11-14 週六；2026-10-09（週五）為休市日

describe('getTaipeiClock', () => {
  it('以台北時區取得日期與分鐘數', () => {
    expect(getTaipeiClock(taipei('2026-11-11T14:50:00'))).toEqual({
      dateKey: '2026-11-11',
      totalMinutes: 14 * 60 + 50,
    });
  });

  it('UTC 日期與台北日期不同時以台北為準', () => {
    // UTC 11-10 20:30 = 台北 11-11 04:30
    expect(getTaipeiClock(new Date('2026-11-10T20:30:00Z'))).toEqual({
      dateKey: '2026-11-11',
      totalMinutes: 4 * 60 + 30,
    });
  });
});

describe('getDefaultMarketType', () => {
  it.each([
    ['08:44 早於日盤開始', '2026-11-11T08:44:00', 'after_hours'],
    ['08:45 日盤開始', '2026-11-11T08:45:00', 'regular'],
    ['13:47 日盤中', '2026-11-11T13:47:00', 'regular'],
    ['13:49 收盤後仍顯示日盤', '2026-11-11T13:49:00', 'regular'],
    ['14:00 收盤後仍顯示日盤', '2026-11-11T14:00:00', 'regular'],
    ['14:50 仍顯示日盤', '2026-11-11T14:50:59', 'regular'],
    ['14:51 切換到夜盤', '2026-11-11T14:51:00', 'after_hours'],
    ['15:30 夜盤', '2026-11-11T15:30:00', 'after_hours'],
    ['23:59 夜盤', '2026-11-11T23:59:00', 'after_hours'],
    ['凌晨 03:00 夜盤延續', '2026-11-11T03:00:00', 'after_hours'],
  ])('交易日 %s', (_label, iso, expected) => {
    expect(getDefaultMarketType(taipei(iso))).toBe(expected);
  });

  it('週六全天顯示夜盤', () => {
    expect(getDefaultMarketType(taipei('2026-11-14T10:00:00'))).toBe('after_hours');
  });

  it('國定假日（2026-10-09）白天顯示夜盤', () => {
    expect(getDefaultMarketType(taipei('2026-10-09T10:00:00'))).toBe('after_hours');
  });
});

describe('getNightSessionDateKey', () => {
  it('交易日 14:50（含）以前使用前一個交易日的夜盤', () => {
    expect(getNightSessionDateKey(taipei('2026-11-11T08:44:00'))).toBe('2026-11-10');
    expect(getNightSessionDateKey(taipei('2026-11-11T14:50:59'))).toBe('2026-11-10');
  });

  it('交易日 14:51 起使用當天夜盤', () => {
    expect(getNightSessionDateKey(taipei('2026-11-11T14:51:00'))).toBe('2026-11-11');
    expect(getNightSessionDateKey(taipei('2026-11-11T23:59:00'))).toBe('2026-11-11');
  });

  it('週一凌晨使用上週五夜盤', () => {
    expect(getNightSessionDateKey(taipei('2026-11-09T03:00:00'))).toBe('2026-11-06');
  });

  it('週六與週日使用上週五夜盤', () => {
    expect(getNightSessionDateKey(taipei('2026-11-14T03:00:00'))).toBe('2026-11-13');
    expect(getNightSessionDateKey(taipei('2026-11-14T16:00:00'))).toBe('2026-11-13');
    expect(getNightSessionDateKey(taipei('2026-11-15T16:00:00'))).toBe('2026-11-13');
  });

  it('休市日（2026-10-09）使用前一個交易日夜盤，下週一凌晨同樣如此', () => {
    expect(getNightSessionDateKey(taipei('2026-10-09T10:00:00'))).toBe('2026-10-08');
    expect(getNightSessionDateKey(taipei('2026-10-12T03:00:00'))).toBe('2026-10-08');
  });

  it('休市日前一晚的夜盤照常（2026-10-08 15:00 起為當天夜盤）', () => {
    expect(getNightSessionDateKey(taipei('2026-10-08T15:00:00'))).toBe('2026-10-08');
  });
});

describe('getDaySessionDateKey', () => {
  it('08:30 前使用前一個交易日，08:30 起使用當天', () => {
    expect(getDaySessionDateKey(taipei('2026-11-11T08:29:00'))).toBe('2026-11-10');
    expect(getDaySessionDateKey(taipei('2026-11-11T08:30:00'))).toBe('2026-11-11');
  });

  it('14:51 之後仍是當天日盤', () => {
    expect(getDaySessionDateKey(taipei('2026-11-11T16:00:00'))).toBe('2026-11-11');
  });

  it('週末與休市日使用最近的交易日', () => {
    expect(getDaySessionDateKey(taipei('2026-11-14T10:00:00'))).toBe('2026-11-13');
    expect(getDaySessionDateKey(taipei('2026-10-09T10:00:00'))).toBe('2026-10-08');
  });
});

describe('toCompactDateKey', () => {
  it('移除連字號', () => {
    expect(toCompactDateKey('2026-11-11')).toBe('20261111');
  });
});

describe('getReferencePriceDates', () => {
  it('14:50 以前：日盤參考價為前一交易日、夜盤參考價為前一交易日（上一個夜盤）', () => {
    expect(getReferencePriceDates(taipei('2026-11-11T10:00:00'))).toEqual({
      day: '20261110',
      night: '20261110',
    });
  });

  it('14:51 起：夜盤參考價換成當天日盤收盤', () => {
    expect(getReferencePriceDates(taipei('2026-11-11T14:51:00'))).toEqual({
      day: '20261110',
      night: '20261111',
    });
  });

  it('週一 08:30 起：日盤參考價為上週五', () => {
    expect(getReferencePriceDates(taipei('2026-11-09T08:30:00'))).toEqual({
      day: '20261106',
      night: '20261106',
    });
  });
});

describe('shouldSkipHistoryPolling', () => {
  const base: PollingGateInput = {
    wsConnected: true,
    isMarketTypeManuallySelected: false,
    inTradingHours: false,
    marketTypeSwitchPending: false,
    referenceDatesChanged: false,
  };

  it('WebSocket 連線、非交易時段、無待處理事項時略過', () => {
    expect(shouldSkipHistoryPolling(base)).toBe(true);
  });

  it('盤別需要切換時不可略過（14:51 切換到尚未開盤的夜盤）', () => {
    expect(shouldSkipHistoryPolling({ ...base, marketTypeSwitchPending: true })).toBe(false);
  });

  it('參考價日期已改變時不可略過', () => {
    expect(shouldSkipHistoryPolling({ ...base, referenceDatesChanged: true })).toBe(false);
  });

  it('交易時段、斷線或手動選盤別時不可略過', () => {
    expect(shouldSkipHistoryPolling({ ...base, inTradingHours: true })).toBe(false);
    expect(shouldSkipHistoryPolling({ ...base, wsConnected: false })).toBe(false);
    expect(shouldSkipHistoryPolling({ ...base, isMarketTypeManuallySelected: true })).toBe(false);
  });
});
