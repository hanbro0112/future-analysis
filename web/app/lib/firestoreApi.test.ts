import {
  subscribeToPttPosts,
  getPttReadState,
  savePttReadState,
  getPttWindowSize,
  savePttWindowSize,
} from './firestoreApi';
import type { PttPush } from '../types/pttChat';

const mockDoc = jest.fn((..._args: unknown[]) => 'fake-doc-ref');
const mockCollection = jest.fn((..._args: unknown[]) => 'fake-collection');
const mockQuery = jest.fn((..._args: unknown[]) => 'fake-query');
const mockWhere = jest.fn((..._args: unknown[]) => 'fake-where');
const mockOnSnapshot = jest.fn();
const mockGetDoc = jest.fn();
const mockSetDoc = jest.fn();

jest.mock('firebase/firestore', () => ({
  collection: (...args: unknown[]) => mockCollection(...args),
  query: (...args: unknown[]) => mockQuery(...args),
  where: (...args: unknown[]) => mockWhere(...args),
  documentId: () => 'DOC_ID_FIELD',
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

  type FakeDocs = { id: string; data: () => { posts?: PttPush[] } }[];
  type SnapshotHandler = (snap: { docs: FakeDocs }) => void;

  function captureHandler(): { get: () => SnapshotHandler } {
    let handler: SnapshotHandler = () => {};
    mockOnSnapshot.mockImplementation((_query: unknown, next: SnapshotHandler) => {
      handler = next;
      return () => {};
    });
    return { get: () => handler };
  }

  const makePush = (userid: string): PttPush => ({ push_tag: '推', userid, content: 'hi', time: '08/06 13:31' });

  it('用文件 ID 前綴範圍查詢 {date}_{session} 與其所有分片', () => {
    mockOnSnapshot.mockReturnValue(() => {});

    subscribeToPttPosts('intraday', '20260806', jest.fn());

    expect(mockCollection).toHaveBeenCalledWith({}, 'pttPosts');
    expect(mockWhere).toHaveBeenCalledWith('DOC_ID_FIELD', '>=', '20260806_intraday');
    expect(mockWhere).toHaveBeenCalledWith('DOC_ID_FIELD', '<=', '20260806_intraday');
    expect(mockOnSnapshot).toHaveBeenCalled();
  });

  it('收到新資料時，把 posts 陣列傳給 callback', () => {
    const { get } = captureHandler();
    const callback = jest.fn();
    const posts = [makePush('a')];

    subscribeToPttPosts('afterhours', '20260806', callback);
    get()({ docs: [{ id: '20260806_afterhours', data: () => ({ posts }) }] });

    expect(callback).toHaveBeenCalledWith(posts);
  });

  it('沒有任何文件時，callback 收到空陣列', () => {
    const { get } = captureHandler();
    const callback = jest.fn();

    subscribeToPttPosts('intraday', '20260806', callback);
    get()({ docs: [] });

    expect(callback).toHaveBeenCalledWith([]);
  });

  it('多個分片依分片序號（數字順序，p10 在 p2 之後）串接成同一個陣列', () => {
    const { get } = captureHandler();
    const callback = jest.fn();

    subscribeToPttPosts('afterhours', '20260806', callback);
    get()({
      docs: [
        { id: '20260806_afterhours_p10', data: () => ({ posts: [makePush('p10')] }) },
        { id: '20260806_afterhours_p2', data: () => ({ posts: [makePush('p2')] }) },
        { id: '20260806_afterhours', data: () => ({ posts: [makePush('p1')] }) },
      ],
    });

    expect(callback).toHaveBeenCalledWith([makePush('p1'), makePush('p2'), makePush('p10')]);
  });

  it('忽略同前綴但格式不符的文件', () => {
    const { get } = captureHandler();
    const callback = jest.fn();

    subscribeToPttPosts('afterhours', '20260806', callback);
    get()({
      docs: [
        { id: '20260806_afterhours', data: () => ({ posts: [makePush('p1')] }) },
        { id: '20260806_afterhours_backup', data: () => ({ posts: [makePush('bad')] }) },
      ],
    });

    expect(callback).toHaveBeenCalledWith([makePush('p1')]);
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

describe('PTT 設定文件讀取共用', () => {
  const settingDoc = {
    exists: () => true,
    data: () => ({ width: 640, height: 600, intraday: { date: '20260806', last_read_index: 3 } }),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('已讀位置與視窗大小同時讀取時只讀一次文件', async () => {
    mockGetDoc.mockResolvedValue(settingDoc);

    const [readIndex, size] = await Promise.all([
      getPttReadState('uid-1', 'intraday', '20260806'),
      getPttWindowSize('uid-1'),
    ]);

    expect(mockGetDoc).toHaveBeenCalledTimes(1);
    expect(readIndex).toBe(3);
    expect(size).toEqual({ width: 640, height: 600 });
  });

  it('前一次讀取完成後再讀取會重新讀文件（不保留快取，維持跨裝置同步）', async () => {
    mockGetDoc.mockResolvedValue(settingDoc);

    await getPttReadState('uid-1', 'intraday', '20260806');
    await getPttReadState('uid-1', 'intraday', '20260806');

    expect(mockGetDoc).toHaveBeenCalledTimes(2);
  });

  it('不同使用者不共用讀取', async () => {
    mockGetDoc.mockResolvedValue(settingDoc);

    await Promise.all([getPttWindowSize('uid-1'), getPttWindowSize('uid-2')]);

    expect(mockGetDoc).toHaveBeenCalledTimes(2);
  });

  it('共用的讀取失敗時，兩者各自回傳預設值', async () => {
    mockGetDoc.mockRejectedValue(new Error('network error'));

    const [readIndex, size] = await Promise.all([
      getPttReadState('uid-1', 'intraday', '20260806'),
      getPttWindowSize('uid-1'),
    ]);

    expect(mockGetDoc).toHaveBeenCalledTimes(1);
    expect(readIndex).toBe(-1);
    expect(size).toBeNull();
  });
});
