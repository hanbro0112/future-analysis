import { renderHook, act } from '@testing-library/react';
import { useWebSocket } from './useWebSocket';

let mockInTradingHours = true;

jest.mock('./tradingHours', () => ({
  isInTradingHours: () => mockInTradingHours,
}));

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close() {
    this.onclose?.({ code: 1000 });
  }
}

const RECONNECT_INTERVAL_MS = 10000;
const OFF_HOURS_CHECK_INTERVAL_MS = 30000;

const advance = async (ms: number) => {
  await act(async () => {
    await jest.advanceTimersByTimeAsync(ms);
  });
};

const latest = () => FakeWebSocket.instances[FakeWebSocket.instances.length - 1];

const openLatest = async () => {
  await act(async () => {
    latest().onopen?.();
  });
};

const closeLatest = async (code: number) => {
  await act(async () => {
    latest().onclose?.({ code });
  });
};

describe('useWebSocket 重連策略', () => {
  const originalWebSocket = global.WebSocket;
  const getUrl = jest.fn().mockResolvedValue('ws://example.com/ws/price?token=abc');

  const setVisibility = (state: 'visible' | 'hidden') => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state });
  };

  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    getUrl.mockResolvedValue('ws://example.com/ws/price?token=abc');
    mockInTradingHours = true;
    FakeWebSocket.instances = [];
    // @ts-expect-error 測試用假的 WebSocket 實作，型別不需完全對齊瀏覽器原生 WebSocket
    global.WebSocket = FakeWebSocket;
    setVisibility('visible');
  });

  afterEach(() => {
    jest.useRealTimers();
    global.WebSocket = originalWebSocket;
  });

  it('曾經連上的連線斷線時立即重連，不等計時器', async () => {
    renderHook(() => useWebSocket(getUrl));
    await advance(0);
    expect(FakeWebSocket.instances).toHaveLength(1);
    await openLatest();

    await closeLatest(1006);
    await advance(0);

    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it('連線本身失敗（從未連上）時，等重連間隔才重試，避免無限快速重試', async () => {
    renderHook(() => useWebSocket(getUrl));
    await advance(0);

    await closeLatest(1006);
    await advance(RECONNECT_INTERVAL_MS - 1);
    expect(FakeWebSocket.instances).toHaveLength(1);

    await advance(1);
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it('收盤被 4403 中斷後不立即重連，離開交易時段仍持續檢查，下個時段開始後自動重連', async () => {
    renderHook(() => useWebSocket(getUrl));
    await advance(0);
    await openLatest();

    // 收盤：後端中斷連線，前端仍認為在交易時段（邊界差異）
    await closeLatest(4403);
    await advance(0);
    expect(FakeWebSocket.instances).toHaveLength(1);

    // 30 秒後再試一次，仍被後端拒絕
    await advance(OFF_HOURS_CHECK_INTERVAL_MS);
    expect(FakeWebSocket.instances).toHaveLength(2);
    mockInTradingHours = false;
    await closeLatest(4403);

    // 離開交易時段後，每 30 秒檢查一次但不連線
    await advance(OFF_HOURS_CHECK_INTERVAL_MS * 3);
    expect(FakeWebSocket.instances).toHaveLength(2);

    // 下個時段開始：下一次檢查就會連線
    mockInTradingHours = true;
    await advance(OFF_HOURS_CHECK_INTERVAL_MS);
    expect(FakeWebSocket.instances).toHaveLength(3);
  });

  it('網路恢復（online）時，若尚未連線就立即重連', async () => {
    renderHook(() => useWebSocket(getUrl));
    await advance(0);
    await closeLatest(1006);
    expect(FakeWebSocket.instances).toHaveLength(1);

    await act(async () => {
      window.dispatchEvent(new Event('online'));
    });
    await advance(0);

    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it('分頁轉為可見時，若尚未連線就立即重連；仍是隱藏則不動作', async () => {
    renderHook(() => useWebSocket(getUrl));
    await advance(0);
    await closeLatest(1006);

    setVisibility('hidden');
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await advance(0);
    expect(FakeWebSocket.instances).toHaveLength(1);

    setVisibility('visible');
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await advance(0);
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it('已連線時收到 online／可見事件不會重複建立連線', async () => {
    renderHook(() => useWebSocket(getUrl));
    await advance(0);
    await openLatest();

    await act(async () => {
      window.dispatchEvent(new Event('online'));
      window.dispatchEvent(new Event('pageshow'));
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await advance(0);

    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it('連線建立中（等待 Token）再收到事件，不會同時建立多條連線', async () => {
    let resolveUrl: (url: string) => void = () => {};
    getUrl.mockImplementationOnce(
      () => new Promise<string>((resolve) => { resolveUrl = resolve; })
    );

    renderHook(() => useWebSocket(getUrl));
    await act(async () => {
      window.dispatchEvent(new Event('online'));
      window.dispatchEvent(new Event('online'));
    });
    expect(getUrl).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveUrl('ws://example.com/ws/price?token=abc');
    });
    await advance(0);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it('舊連線遲到的 onclose 不會影響新連線，也不會多開連線', async () => {
    const { result } = renderHook(() => useWebSocket(getUrl));
    await advance(0);
    await openLatest();
    const first = latest();

    await closeLatest(1006);
    await advance(0);
    expect(FakeWebSocket.instances).toHaveLength(2);
    await openLatest();
    expect(result.current.isConnected).toBe(true);

    // 舊連線又觸發一次 onclose（例如瀏覽器事件遲到）
    await act(async () => {
      first.onclose?.({ code: 1006 });
    });
    await advance(RECONNECT_INTERVAL_MS);

    expect(result.current.isConnected).toBe(true);
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it('autoReconnect 為 false 時，斷線與事件都不會重連', async () => {
    renderHook(() => useWebSocket(getUrl, false));
    await advance(0);
    await openLatest();

    await closeLatest(1006);
    await act(async () => {
      window.dispatchEvent(new Event('online'));
    });
    await advance(RECONNECT_INTERVAL_MS * 3);

    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it('unmount 後清除計時器與事件監聽，不再建立連線', async () => {
    const { unmount } = renderHook(() => useWebSocket(getUrl));
    await advance(0);
    await closeLatest(1006);

    unmount();
    await act(async () => {
      window.dispatchEvent(new Event('online'));
    });
    await advance(RECONNECT_INTERVAL_MS * 3);

    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it('連續失敗時重連間隔指數退避（10 → 20 → 40 → 60 秒），上限 60 秒', async () => {
    renderHook(() => useWebSocket(getUrl));
    await advance(0);
    expect(FakeWebSocket.instances).toHaveLength(1);

    // 第 1 次失敗：10 秒後重試
    await closeLatest(1006);
    await advance(10000 - 1);
    expect(FakeWebSocket.instances).toHaveLength(1);
    await advance(1);
    expect(FakeWebSocket.instances).toHaveLength(2);

    // 第 2 次失敗：20 秒後重試
    await closeLatest(1006);
    await advance(20000 - 1);
    expect(FakeWebSocket.instances).toHaveLength(2);
    await advance(1);
    expect(FakeWebSocket.instances).toHaveLength(3);

    // 第 3 次失敗：40 秒後重試
    await closeLatest(1006);
    await advance(40000 - 1);
    expect(FakeWebSocket.instances).toHaveLength(3);
    await advance(1);
    expect(FakeWebSocket.instances).toHaveLength(4);

    // 第 4 次、第 5 次失敗：都封頂在 60 秒
    await closeLatest(1006);
    await advance(60000 - 1);
    expect(FakeWebSocket.instances).toHaveLength(4);
    await advance(1);
    expect(FakeWebSocket.instances).toHaveLength(5);

    await closeLatest(1006);
    await advance(60000 - 1);
    expect(FakeWebSocket.instances).toHaveLength(5);
    await advance(1);
    expect(FakeWebSocket.instances).toHaveLength(6);
  });

  it('連上之後退避重置，之後再失敗又從最短間隔開始', async () => {
    renderHook(() => useWebSocket(getUrl));
    await advance(0);

    // 連續失敗兩次，間隔已拉長到 20 秒
    await closeLatest(1006);
    await advance(10000);
    await closeLatest(1006);
    await advance(20000);
    expect(FakeWebSocket.instances).toHaveLength(3);

    // 這次連上了，之後斷線會立即重連，且這次新連線再失敗時回到 10 秒
    await openLatest();
    await closeLatest(1006);
    await advance(0);
    expect(FakeWebSocket.instances).toHaveLength(4);

    await closeLatest(1006);
    await advance(10000 - 1);
    expect(FakeWebSocket.instances).toHaveLength(4);
    await advance(1);
    expect(FakeWebSocket.instances).toHaveLength(5);
  });

  it('取不到連線網址（Token 失敗）時同樣退避', async () => {
    getUrl.mockResolvedValue(null);
    renderHook(() => useWebSocket(getUrl));
    await advance(0);
    expect(getUrl).toHaveBeenCalledTimes(1);

    await advance(10000);
    expect(getUrl).toHaveBeenCalledTimes(2);

    // 第 2 次失敗後間隔變 20 秒
    await advance(20000 - 1);
    expect(getUrl).toHaveBeenCalledTimes(2);
    await advance(1);
    expect(getUrl).toHaveBeenCalledTimes(3);
  });

  it('online／可見事件會重置退避，立即重連後再失敗從最短間隔開始', async () => {
    renderHook(() => useWebSocket(getUrl));
    await advance(0);

    // 連續失敗兩次，間隔已拉長到 20 秒
    await closeLatest(1006);
    await advance(10000);
    await closeLatest(1006);
    expect(FakeWebSocket.instances).toHaveLength(2);

    await act(async () => {
      window.dispatchEvent(new Event('online'));
    });
    await advance(0);
    expect(FakeWebSocket.instances).toHaveLength(3);

    await closeLatest(1006);
    await advance(10000);
    expect(FakeWebSocket.instances).toHaveLength(4);
  });
});
