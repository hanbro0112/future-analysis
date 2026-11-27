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
  where: jest.fn(),
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

  type SnapHandler = (snap: { data: () => { posts?: PttPush[]; is_full?: boolean } | undefined }) => void;

  /** 依 doc() 傳入的文件 ID 記錄各分片的 onSnapshot handler 與取消函數 */
  function captureHandlers() {
    const handlers = new Map<string, SnapHandler>();
    const unsubscribers = new Map<string, jest.Mock>();
    const errorHandlers = new Map<string, (error: Error) => void>();
    mockDoc.mockImplementation((...args: unknown[]) => args[args.length - 1] as string);
    mockOnSnapshot.mockImplementation((docId: string, handler: SnapHandler, onError: (error: Error) => void) => {
      handlers.set(docId, handler);
      errorHandlers.set(docId, onError);
      const unsubscribe = jest.fn();
      unsubscribers.set(docId, unsubscribe);
      return unsubscribe;
    });
    return { handlers, unsubscribers, errorHandlers };
  }

  const makePush = (userid: string): PttPush => ({ push_tag: '推', userid, content: 'hi', time: '08/06 13:31' });

  afterEach(() => {
    mockDoc.mockImplementation(() => 'fake-doc-ref');
  });

  it('用 {date}_{session} 組出第 1 片文件路徑並訂閱', () => {
    const { handlers } = captureHandlers();

    subscribeToPttPosts('intraday', '20260806', jest.fn());

    expect(mockDoc).toHaveBeenCalledWith({}, 'pttPosts', '20260806_intraday');
    expect([...handlers.keys()]).toEqual(['20260806_intraday']);
  });

  it('收到新資料時，把 posts 陣列傳給 callback', () => {
    const { handlers } = captureHandlers();
    const callback = jest.fn();
    const posts = [makePush('a')];

    subscribeToPttPosts('afterhours', '20260806', callback);
    handlers.get('20260806_afterhours')!({ data: () => ({ posts }) });

    expect(callback).toHaveBeenCalledWith(posts);
  });

  it('文件不存在時，callback 收到空陣列', () => {
    const { handlers } = captureHandlers();
    const callback = jest.fn();

    subscribeToPttPosts('intraday', '20260806', callback);
    handlers.get('20260806_intraday')!({ data: () => undefined });

    expect(callback).toHaveBeenCalledWith([]);
  });

  it('沒有 is_full 標記時不會訂閱下一片', () => {
    const { handlers } = captureHandlers();

    subscribeToPttPosts('intraday', '20260806', jest.fn());
    handlers.get('20260806_intraday')!({ data: () => ({ posts: [makePush('a')] }) });

    expect([...handlers.keys()]).toEqual(['20260806_intraday']);
  });

  it('看到 is_full 就訂閱下一片（與則數無關），所有分片快照到齊後才回呼並依序串接', () => {
    const { handlers } = captureHandlers();
    const callback = jest.fn();

    subscribeToPttPosts('afterhours', '20260806', callback);
    handlers.get('20260806_afterhours')!({ data: () => ({ posts: [makePush('p1')], is_full: true }) });

    expect([...handlers.keys()]).toEqual(['20260806_afterhours', '20260806_afterhours_p2']);
    expect(callback).not.toHaveBeenCalled();

    handlers.get('20260806_afterhours_p2')!({ data: () => ({ posts: [makePush('p2')] }) });

    expect(callback).toHaveBeenCalledTimes(1);
    expect(callback).toHaveBeenCalledWith([makePush('p1'), makePush('p2')]);
  });

  it('分片即時被標記 is_full 後，會接著訂閱尚未存在的下一片並於寫入時更新', () => {
    const { handlers } = captureHandlers();
    const callback = jest.fn();

    subscribeToPttPosts('afterhours', '20260806', callback);
    handlers.get('20260806_afterhours')!({ data: () => ({ posts: [makePush('p1')] }) });
    handlers.get('20260806_afterhours')!({ data: () => ({ posts: [makePush('p1')], is_full: true }) });
    handlers.get('20260806_afterhours_p2')!({ data: () => undefined });
    handlers.get('20260806_afterhours_p2')!({ data: () => ({ posts: [makePush('p2')] }) });

    expect(callback).toHaveBeenLastCalledWith([makePush('p1'), makePush('p2')]);
  });

  it('下一片監聽失敗時，仍回呼已取得的分片', () => {
    const { handlers, errorHandlers } = captureHandlers();
    const callback = jest.fn();
    const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

    subscribeToPttPosts('afterhours', '20260806', callback);
    handlers.get('20260806_afterhours')!({ data: () => ({ posts: [makePush('p1')], is_full: true }) });
    errorHandlers.get('20260806_afterhours_p2')!(new Error('permission-denied'));

    expect(callback).toHaveBeenCalledWith([makePush('p1')]);
    expect(errorSpy).toHaveBeenCalled();
    errorSpy.mockRestore();
  });

  it('取消訂閱時會取消所有分片的監聽，且之後不再回呼', () => {
    const { handlers, unsubscribers } = captureHandlers();
    const callback = jest.fn();

    const unsubscribe = subscribeToPttPosts('afterhours', '20260806', callback);
    handlers.get('20260806_afterhours')!({ data: () => ({ posts: [makePush('p1')], is_full: true }) });
    unsubscribe();
    handlers.get('20260806_afterhours_p2')!({ data: () => ({ posts: [makePush('late')] }) });

    expect(unsubscribers.get('20260806_afterhours')).toHaveBeenCalled();
    expect(unsubscribers.get('20260806_afterhours_p2')).toHaveBeenCalled();
    expect(callback).not.toHaveBeenCalled();
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
