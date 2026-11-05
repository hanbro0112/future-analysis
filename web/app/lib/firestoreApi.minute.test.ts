import {
  getMinuteData,
  getMinuteDataAfter,
  getTodayMinuteData,
  getDaySessionClosePrice,
  getLatestBarTimestamp,
  mergeMinuteBars,
  sortMinuteBars,
  timestampToDate,
} from './firestoreApi';
import type { MinuteBar } from '../types/minuteData';

const mockCollection = jest.fn((..._args: unknown[]) => 'fake-collection');
const mockQuery = jest.fn((...args: unknown[]) => ({ queryArgs: args }));
const mockWhere = jest.fn((...args: unknown[]) => ({ where: args }));
const mockOrderBy = jest.fn((...args: unknown[]) => ({ orderBy: args }));
const mockGetDocs = jest.fn();
const mockDoc = jest.fn((..._args: unknown[]) => 'fake-doc-ref');
const mockGetDoc = jest.fn();

jest.mock('firebase/firestore', () => ({
  collection: (...args: unknown[]) => mockCollection(...args),
  query: (...args: unknown[]) => mockQuery(...args),
  where: (...args: unknown[]) => mockWhere(...args),
  orderBy: (...args: unknown[]) => mockOrderBy(...args),
  limit: jest.fn(),
  getDocs: (...args: unknown[]) => mockGetDocs(...args),
  getDoc: (...args: unknown[]) => mockGetDoc(...args),
  setDoc: jest.fn(),
  doc: (...args: unknown[]) => mockDoc(...args),
  onSnapshot: jest.fn(),
}));

jest.mock('./firebase', () => ({
  db: {},
}));

const makeBar = (overrides: Partial<MinuteBar>): MinuteBar => ({
  code: 'MXF',
  timestamp: '',
  date: '2026-10-14',
  time: '0845',
  market_type: 'regular',
  open: 1,
  high: 1,
  low: 1,
  close: 1,
  volume: 1,
  buy_volume: 0,
  sell_volume: 0,
  avg_price: 1,
  tick_count: 1,
  bid_total: 0,
  ask_total: 0,
  ...overrides,
});

const makeSnapshot = (docs: Array<{ id: string; data: Record<string, unknown> }>) => ({
  forEach: (cb: (d: { id: string; data: () => Record<string, unknown> }) => void) =>
    docs.forEach((d) => cb({ id: d.id, data: () => d.data })),
});

describe('sortMinuteBars / mergeMinuteBars', () => {
  it('夜盤凌晨（00:00-05:59）排在 15:00-23:59 之後，日盤在夜盤之前', () => {
    const sorted = sortMinuteBars([
      makeBar({ market_type: 'after_hours', time: '0030' }),
      makeBar({ market_type: 'after_hours', time: '1500' }),
      makeBar({ market_type: 'regular', time: '0846' }),
      makeBar({ market_type: 'after_hours', time: '2359' }),
      makeBar({ market_type: 'regular', time: '0845' }),
    ]);

    expect(sorted.map((b) => b.time)).toEqual(['0845', '0846', '1500', '2359', '0030']);
  });

  it('相同盤別與 time 的 K 棒以新資料覆蓋，新時間則附加', () => {
    const existing = [
      makeBar({ market_type: 'after_hours', time: '2358', close: 10 }),
      makeBar({ market_type: 'after_hours', time: '2359', close: 11 }),
    ];
    const incoming = [
      makeBar({ market_type: 'after_hours', time: '2359', close: 12 }),
      makeBar({ market_type: 'after_hours', time: '0000', close: 13 }),
    ];

    const merged = mergeMinuteBars(existing, incoming);

    expect(merged.map((b) => [b.time, b.close])).toEqual([
      ['2358', 10],
      ['2359', 12],
      ['0000', 13],
    ]);
  });
});

describe('timestampToDate / getLatestBarTimestamp', () => {
  it('支援 Firestore Timestamp（toDate）、Date、ISO 字串，無法辨識回傳 null', () => {
    const date = new Date('2026-10-14T01:00:00Z');

    expect(timestampToDate({ toDate: () => date })).toBe(date);
    expect(timestampToDate(date)).toBe(date);
    expect(timestampToDate('2026-10-14T01:00:00Z')?.getTime()).toBe(date.getTime());
    expect(timestampToDate(undefined)).toBeNull();
    expect(timestampToDate('not-a-date')).toBeNull();
  });

  it('取最大的 timestamp 當游標，跨午夜的夜盤凌晨 K 棒（time 較小）仍視為最新', () => {
    const bars = [
      makeBar({ market_type: 'after_hours', time: '2359', timestamp: { toDate: () => new Date('2026-10-14T15:59:00Z') } as unknown as string }),
      makeBar({ market_type: 'after_hours', time: '0001', timestamp: { toDate: () => new Date('2026-10-14T16:01:00Z') } as unknown as string }),
    ];

    expect(getLatestBarTimestamp(bars)?.toISOString()).toBe('2026-10-14T16:01:00.000Z');
  });

  it('沒有可用 timestamp 時回傳 null', () => {
    expect(getLatestBarTimestamp([makeBar({ timestamp: '' })])).toBeNull();
    expect(getLatestBarTimestamp([])).toBeNull();
  });
});

describe('getMinuteData', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('指定盤別時用 market_type 等值條件，且不搭配 orderBy', async () => {
    mockGetDocs.mockResolvedValue(makeSnapshot([]));

    await getMinuteData('MXF', '20261014', 'regular');

    expect(mockCollection).toHaveBeenCalledWith({}, 'market/MXF/20261014');
    expect(mockWhere).toHaveBeenCalledWith('market_type', '==', 'regular');
    expect(mockOrderBy).not.toHaveBeenCalled();
  });

  it('未指定盤別時整集合依 time 排序', async () => {
    mockGetDocs.mockResolvedValue(makeSnapshot([]));

    await getMinuteData('MXF', '20261014');

    expect(mockWhere).not.toHaveBeenCalled();
    expect(mockOrderBy).toHaveBeenCalledWith('time', 'asc');
  });

  it('讀取失敗時回傳空陣列', async () => {
    mockGetDocs.mockRejectedValue(new Error('network error'));

    await expect(getMinuteData('MXF', '20261014', 'regular')).resolves.toEqual([]);
  });
});

describe('getMinuteDataAfter', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('以 timestamp >= 游標查詢並依 timestamp 升序', async () => {
    mockGetDocs.mockResolvedValue(makeSnapshot([]));
    const cursor = new Date('2026-10-14T05:44:00Z');

    await getMinuteDataAfter('MXF', '20261014', cursor, 'regular');

    expect(mockCollection).toHaveBeenCalledWith({}, 'market/MXF/20261014');
    expect(mockWhere).toHaveBeenCalledWith('timestamp', '>=', cursor);
    expect(mockOrderBy).toHaveBeenCalledWith('timestamp', 'asc');
  });

  it('依盤別在前端過濾回傳的文件', async () => {
    mockGetDocs.mockResolvedValue(
      makeSnapshot([
        { id: '1344', data: { market_type: 'regular', time: '1344', close: 100 } },
        { id: '1500', data: { market_type: 'after_hours', time: '1500', close: 101 } },
      ])
    );

    const result = await getMinuteDataAfter('MXF', '20261014', new Date(), 'after_hours');

    expect(result.map((b) => b.time)).toEqual(['1500']);
  });

  it('讀取失敗時回傳空陣列', async () => {
    mockGetDocs.mockRejectedValue(new Error('network error'));

    await expect(getMinuteDataAfter('MXF', '20261014', new Date())).resolves.toEqual([]);
  });
});

describe('getTodayMinuteData', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('14:50 之後日盤與夜盤同一天，只讀一次集合再切分', async () => {
    jest.setSystemTime(new Date(2026, 9, 14, 16, 0, 0)); // 2026-10-14（週三）16:00
    mockGetDocs.mockResolvedValue(
      makeSnapshot([
        { id: '1500', data: { market_type: 'after_hours', time: '1500' } },
        { id: '0845', data: { market_type: 'regular', time: '0845' } },
      ])
    );

    const result = await getTodayMinuteData('MXF');

    expect(mockGetDocs).toHaveBeenCalledTimes(1);
    expect(mockCollection).toHaveBeenCalledWith({}, 'market/MXF/20261014');
    expect(result.map((b) => b.time)).toEqual(['0845', '1500']);
  });

  it('14:50 之前日盤用今天、夜盤用前一天，各自只讀對應盤別', async () => {
    jest.setSystemTime(new Date(2026, 9, 14, 10, 0, 0)); // 2026-10-14（週三）10:00
    mockGetDocs.mockResolvedValue(makeSnapshot([]));

    await getTodayMinuteData('MXF');

    expect(mockGetDocs).toHaveBeenCalledTimes(2);
    expect(mockCollection).toHaveBeenCalledWith({}, 'market/MXF/20261014');
    expect(mockCollection).toHaveBeenCalledWith({}, 'market/MXF/20261013');
    expect(mockWhere).toHaveBeenCalledWith('market_type', '==', 'regular');
    expect(mockWhere).toHaveBeenCalledWith('market_type', '==', 'after_hours');
  });
});

describe('getDaySessionClosePrice', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('1344 存在時只讀這一筆並回傳 close', async () => {
    mockGetDoc.mockResolvedValue({ exists: () => true, data: () => ({ close: 23456 }) });

    await expect(getDaySessionClosePrice('MXF', '20261013')).resolves.toBe(23456);

    expect(mockDoc).toHaveBeenCalledWith({}, 'market/MXF/20261013/1344');
    expect(mockGetDoc).toHaveBeenCalledTimes(1);
  });

  it('1344 不存在（結算日）時改取 1329', async () => {
    mockGetDoc
      .mockResolvedValueOnce({ exists: () => false })
      .mockResolvedValueOnce({ exists: () => true, data: () => ({ close: 23400 }) });

    await expect(getDaySessionClosePrice('MXF', '20261013')).resolves.toBe(23400);

    expect(mockDoc).toHaveBeenNthCalledWith(1, {}, 'market/MXF/20261013/1344');
    expect(mockDoc).toHaveBeenNthCalledWith(2, {}, 'market/MXF/20261013/1329');
  });

  it('1344 讀取失敗時也改取 1329', async () => {
    mockGetDoc
      .mockRejectedValueOnce(new Error('network error'))
      .mockResolvedValueOnce({ exists: () => true, data: () => ({ close: 23400 }) });

    await expect(getDaySessionClosePrice('MXF', '20261013')).resolves.toBe(23400);
  });

  it('兩筆都讀不到時回傳 null', async () => {
    mockGetDoc.mockResolvedValue({ exists: () => false });

    await expect(getDaySessionClosePrice('MXF', '20261013')).resolves.toBeNull();
    expect(mockGetDoc).toHaveBeenCalledTimes(2);
  });
});
