import {
  getDateOffsetTradingDays,
  getLastTradingDay,
  isTradingDateKey,
  isTradingDay,
  toDateKey,
} from './tradingCalendar';

describe('isTradingDateKey', () => {
  it('一般平日為交易日', () => {
    expect(isTradingDateKey('2026-07-27')).toBe(true); // 週一
    expect(isTradingDateKey('2026-07-31')).toBe(true); // 週五
  });

  it('週六、週日不是交易日', () => {
    expect(isTradingDateKey('2026-08-01')).toBe(false);
    expect(isTradingDateKey('2026-08-02')).toBe(false);
  });

  it('國定假日與補假不是交易日', () => {
    expect(isTradingDateKey('2026-10-09')).toBe(false); // 國慶日補假（週五）
    expect(isTradingDateKey('2026-02-17')).toBe(false); // 春節（週二）
    expect(isTradingDateKey('2026-01-01')).toBe(false); // 元旦
  });

  it('軍人節等非放假日仍是交易日', () => {
    expect(isTradingDateKey('2026-09-03')).toBe(true);
  });

  it('假日隔天的第一個平日為交易日', () => {
    expect(isTradingDateKey('2026-10-12')).toBe(true);
    expect(isTradingDateKey('2026-02-23')).toBe(true);
  });

  it('超出資料範圍的年度只判斷週末並提示一次', () => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => undefined);

    expect(isTradingDateKey('2035-01-01')).toBe(true); // 週一，無資料時視為交易日
    expect(isTradingDateKey('2035-01-06')).toBe(false); // 週六
    expect(warn).toHaveBeenCalledTimes(1);

    warn.mockRestore();
  });
});

describe('isTradingDay', () => {
  it('以本地日期判斷（與時分秒無關）', () => {
    expect(isTradingDay(new Date(2026, 9, 9, 23, 59))).toBe(false);
    expect(isTradingDay(new Date(2026, 9, 12, 0, 0))).toBe(true);
  });
});

describe('toDateKey', () => {
  it('格式化為 YYYY-MM-DD 並補零', () => {
    expect(toDateKey(new Date(2026, 0, 5))).toBe('2026-01-05');
  });
});

describe('getLastTradingDay', () => {
  it('交易日回傳原日期並保留時間', () => {
    const result = getLastTradingDay(new Date(2026, 6, 29, 10, 30));
    expect(toDateKey(result)).toBe('2026-07-29');
    expect(result.getHours()).toBe(10);
  });

  it('週六、週日往前推到週五', () => {
    expect(toDateKey(getLastTradingDay(new Date(2026, 6, 25)))).toBe('2026-07-24');
    expect(toDateKey(getLastTradingDay(new Date(2026, 6, 26)))).toBe('2026-07-24');
  });

  it('國定假日補假往前推到前一個交易日', () => {
    // 2026-10-09 週五補假、10-10 週六、10-11 週日 → 10-08 週四
    expect(toDateKey(getLastTradingDay(new Date(2026, 9, 9)))).toBe('2026-10-08');
    expect(toDateKey(getLastTradingDay(new Date(2026, 9, 11)))).toBe('2026-10-08');
  });

  it('春節連假往前推到連假前最後一個交易日', () => {
    // 2026-02-14 至 02-22 連續休市，往前為 2026-02-13（週五）
    expect(toDateKey(getLastTradingDay(new Date(2026, 1, 18)))).toBe('2026-02-13');
  });

  it('不會修改傳入的 Date', () => {
    const input = new Date(2026, 9, 9);
    getLastTradingDay(input);
    expect(toDateKey(input)).toBe('2026-10-09');
  });
});

describe('getDateOffsetTradingDays', () => {
  it('daysBack 為 0 時回傳同一天', () => {
    expect(toDateKey(getDateOffsetTradingDays(new Date(2026, 6, 29), 0))).toBe('2026-07-29');
  });

  it('略過週末', () => {
    // 2026-07-27（週一）往前 1 個交易日 → 07-24（週五）
    expect(toDateKey(getDateOffsetTradingDays(new Date(2026, 6, 27), 1))).toBe('2026-07-24');
  });

  it('略過國定假日', () => {
    // 2026-10-12（週一）往前 1 個交易日 → 補假的 10-09 與週末都略過 → 10-08
    expect(toDateKey(getDateOffsetTradingDays(new Date(2026, 9, 12), 1))).toBe('2026-10-08');
    expect(toDateKey(getDateOffsetTradingDays(new Date(2026, 9, 12), 2))).toBe('2026-10-07');
  });
});

describe('休市日資料檔缺失', () => {
  afterEach(() => {
    jest.dontMock('./tradingCalendar.data.json');
    jest.resetModules();
  });

  it('找不到資料檔時不丟錯，只判斷週末並提示執行匯出', () => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => undefined);
    jest.resetModules();
    jest.doMock('./tradingCalendar.data.json', () => {
      throw new Error("Cannot find module './tradingCalendar.data.json'");
    });

    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const calendar = require('./tradingCalendar') as typeof import('./tradingCalendar');

    expect(calendar.isTradingDateKey('2026-10-09')).toBe(true); // 缺資料時國定假日無法判斷
    expect(calendar.isTradingDateKey('2026-10-10')).toBe(false); // 週六仍排除
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn.mock.calls[0][0]).toContain('npm run export:calendar');

    warn.mockRestore();
  });
});
