import { renderHook, waitFor, act } from '@testing-library/react';
import { useWebSocket } from './useWebSocket';

jest.mock('./tradingHours', () => ({
  isInTradingHours: () => true,
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

describe('useWebSocket', () => {
  const originalWebSocket = global.WebSocket;

  beforeEach(() => {
    FakeWebSocket.instances = [];
    // @ts-expect-error 測試用假的 WebSocket 實作，型別不需完全對齊瀏覽器原生 WebSocket
    global.WebSocket = FakeWebSocket;
  });

  afterEach(() => {
    global.WebSocket = originalWebSocket;
  });

  it('getUrl 為 null 時不建立連線', async () => {
    renderHook(() => useWebSocket(null));
    await Promise.resolve();
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it('建立連線時會以 forceRefresh=false 呼叫 getUrl', async () => {
    const getUrl = jest.fn().mockResolvedValue('ws://example.com/ws/price?token=abc');

    const { unmount } = renderHook(() => useWebSocket(getUrl));

    await waitFor(() => {
      expect(getUrl).toHaveBeenCalledTimes(1);
    });
    expect(getUrl).toHaveBeenCalledWith(false);

    unmount();
  });

  it('連線因驗證失敗 (close code 4401) 關閉後，重連時會以 forceRefresh=true 要求換發新 Token', async () => {
    const getUrl = jest.fn().mockResolvedValue('ws://example.com/ws/price?token=abc');

    const { unmount } = renderHook(() => useWebSocket(getUrl, true, 10));

    await waitFor(() => {
      expect(FakeWebSocket.instances).toHaveLength(1);
    });

    act(() => {
      FakeWebSocket.instances[0].onclose?.({ code: 4401 });
    });

    await waitFor(() => {
      expect(getUrl).toHaveBeenCalledTimes(2);
    });
    expect(getUrl).toHaveBeenNthCalledWith(2, true);

    unmount();
  });

  it('連線因一般原因關閉後，重連不會強制刷新 Token', async () => {
    const getUrl = jest.fn().mockResolvedValue('ws://example.com/ws/price?token=abc');

    const { unmount } = renderHook(() => useWebSocket(getUrl, true, 10));

    await waitFor(() => {
      expect(FakeWebSocket.instances).toHaveLength(1);
    });

    act(() => {
      FakeWebSocket.instances[0].onclose?.({ code: 1000 });
    });

    await waitFor(() => {
      expect(getUrl).toHaveBeenCalledTimes(2);
    });
    expect(getUrl).toHaveBeenNthCalledWith(2, false);

    unmount();
  });
});
