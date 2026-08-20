import {
  subscribeToPttPosts,
  getPttReadState,
  savePttReadState,
  getPttWindowSize,
  savePttWindowSize,
} from './firestoreApi';
import type { PttPush } from '../types/pttChat';

const mockDoc = jest.fn((..._args: unknown[]) => 'fake-doc-ref');
const mockOnSnapshot = jest.fn();
const mockGetDoc = jest.fn();
const mockSetDoc = jest.fn();

jest.mock('firebase/firestore', () => ({
  collection: jest.fn(),
  query: jest.fn(),
  orderBy: jest.fn(),
  limit: jest.fn(),
  getDocs: jest.fn(),
  getDoc: (...args: unknown[]) => mockGetDoc(...args),
  setDoc: (...args: unknown[]) => mockSetDoc(...args),
  doc: (...args: unknown[]) => mockDoc(...args),
  onSnapshot: (...args: unknown[]) => mockOnSnapshot(...args),
}));

jest.mock('./firebase', () => ({
  db: {},
}));

describe('subscribeToPttPosts', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('用 {date}_{session} 組出文件路徑並訂閱', () => {
    mockOnSnapshot.mockReturnValue(() => {});

    subscribeToPttPosts('intraday', '20260806', jest.fn());

    expect(mockDoc).toHaveBeenCalledWith({}, 'pttPosts', '20260806_intraday');
    expect(mockOnSnapshot).toHaveBeenCalled();
  });

  it('收到新資料時，把 posts 陣列傳給 callback', () => {
    let snapshotHandler: (snap: { exists: () => boolean; data: () => { posts?: PttPush[] } | undefined }) => void =
      () => {};
    mockOnSnapshot.mockImplementation((_ref: unknown, handler: typeof snapshotHandler) => {
      snapshotHandler = handler;
      return () => {};
    });
    const callback = jest.fn();
    const posts: PttPush[] = [{ push_tag: '推', userid: 'a', content: 'hi', time: '08/06 13:31' }];

    subscribeToPttPosts('afterhours', '20260806', callback);
    snapshotHandler({ exists: () => true, data: () => ({ posts }) });

    expect(callback).toHaveBeenCalledWith(posts);
  });

  it('文件不存在時，callback 收到空陣列', () => {
    let snapshotHandler: (snap: { exists: () => boolean; data: () => { posts?: PttPush[] } | undefined }) => void =
      () => {};
    mockOnSnapshot.mockImplementation((_ref: unknown, handler: typeof snapshotHandler) => {
      snapshotHandler = handler;
      return () => {};
    });
    const callback = jest.fn();

    subscribeToPttPosts('intraday', '20260806', callback);
    snapshotHandler({ exists: () => false, data: () => undefined });

    expect(callback).toHaveBeenCalledWith([]);
  });
});

describe('getPttReadState', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('用 users/{uid}/setting/pttReadState 組出文件路徑（盤中盤後共用同一份文件）', async () => {
    mockGetDoc.mockResolvedValue({ exists: () => false });

    await getPttReadState('uid-1', 'intraday', '20260806');

    expect(mockDoc).toHaveBeenCalledWith({}, 'users', 'uid-1', 'setting', 'pttReadState');
  });

  it('對應 session 欄位存在且 date 相符時回傳 last_read_index', async () => {
    mockGetDoc.mockResolvedValue({
      exists: () => true,
      data: () => ({ afterhours: { date: '20260806', last_read_index: 12 } }),
    });

    await expect(getPttReadState('uid-1', 'afterhours', '20260806')).resolves.toBe(12);
  });

  it('對應 session 欄位的 date 是別天（舊資料）時回傳 -1', async () => {
    mockGetDoc.mockResolvedValue({
      exists: () => true,
      data: () => ({ afterhours: { date: '20260805', last_read_index: 12 } }),
    });

    await expect(getPttReadState('uid-1', 'afterhours', '20260806')).resolves.toBe(-1);
  });

  it('文件存在但對應 session 欄位不存在時回傳 -1', async () => {
    mockGetDoc.mockResolvedValue({
      exists: () => true,
      data: () => ({ intraday: { date: '20260806', last_read_index: 3 } }),
    });

    await expect(getPttReadState('uid-1', 'afterhours', '20260806')).resolves.toBe(-1);
  });

  it('文件不存在時回傳 -1', async () => {
    mockGetDoc.mockResolvedValue({ exists: () => false });

    await expect(getPttReadState('uid-1', 'intraday', '20260806')).resolves.toBe(-1);
  });

  it('讀取失敗時回傳 -1', async () => {
    mockGetDoc.mockRejectedValue(new Error('network error'));

    await expect(getPttReadState('uid-1', 'intraday', '20260806')).resolves.toBe(-1);
  });
});

describe('savePttReadState', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('用巢狀物件搭配 merge 局部更新對應 session 的欄位，不動到另一個 session 或視窗大小', async () => {
    mockSetDoc.mockResolvedValue(undefined);

    await savePttReadState('uid-1', 'intraday', '20260806', 5);

    expect(mockDoc).toHaveBeenCalledWith({}, 'users', 'uid-1', 'setting', 'pttReadState');
    expect(mockSetDoc).toHaveBeenCalledWith(
      'fake-doc-ref',
      { intraday: { date: '20260806', last_read_index: 5 } },
      { merge: true }
    );
  });

  it('寫入失敗時不拋出例外', async () => {
    mockSetDoc.mockRejectedValue(new Error('network error'));

    await expect(savePttReadState('uid-1', 'intraday', '20260806', 5)).resolves.toBeUndefined();
  });
});

describe('getPttWindowSize', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('用 users/{uid}/setting/pttReadState 組出文件路徑', async () => {
    mockGetDoc.mockResolvedValue({ exists: () => false });

    await getPttWindowSize('uid-1');

    expect(mockDoc).toHaveBeenCalledWith({}, 'users', 'uid-1', 'setting', 'pttReadState');
  });

  it('文件存在且 width/height 都是數字時回傳寬高', async () => {
    mockGetDoc.mockResolvedValue({ exists: () => true, data: () => ({ width: 640, height: 600 }) });

    await expect(getPttWindowSize('uid-1')).resolves.toEqual({ width: 640, height: 600 });
  });

  it('文件不存在時回傳 null', async () => {
    mockGetDoc.mockResolvedValue({ exists: () => false });

    await expect(getPttWindowSize('uid-1')).resolves.toBeNull();
  });

  it('沒有存過寬高時回傳 null', async () => {
    mockGetDoc.mockResolvedValue({ exists: () => true, data: () => ({ intraday: { date: '20260806', last_read_index: 1 } }) });

    await expect(getPttWindowSize('uid-1')).resolves.toBeNull();
  });

  it('讀取失敗時回傳 null', async () => {
    mockGetDoc.mockRejectedValue(new Error('network error'));

    await expect(getPttWindowSize('uid-1')).resolves.toBeNull();
  });
});

describe('savePttWindowSize', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('用 merge 寫入 width/height，不影響已讀位置欄位', async () => {
    mockSetDoc.mockResolvedValue(undefined);

    await savePttWindowSize('uid-1', 640, 600);

    expect(mockDoc).toHaveBeenCalledWith({}, 'users', 'uid-1', 'setting', 'pttReadState');
    expect(mockSetDoc).toHaveBeenCalledWith('fake-doc-ref', { width: 640, height: 600 }, { merge: true });
  });

  it('寫入失敗時不拋出例外', async () => {
    mockSetDoc.mockRejectedValue(new Error('network error'));

    await expect(savePttWindowSize('uid-1', 640, 600)).resolves.toBeUndefined();
  });
});
