import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import PttChatWidget from './PttChatWidget';
import { useAuth } from '../lib/AuthContext';
import {
  subscribeToPttPosts,
  getPttReadState,
  savePttReadState,
  getPttWindowSize,
  savePttWindowSize,
} from '../lib/firestoreApi';
import { getCurrentPttSession, getPttSessionDate } from '../lib/pttSession';
import type { PttPush } from '../types/pttChat';

jest.mock('../lib/AuthContext', () => ({
  useAuth: jest.fn(),
}));

jest.mock('../lib/firestoreApi', () => ({
  subscribeToPttPosts: jest.fn(),
  getPttReadState: jest.fn(),
  savePttReadState: jest.fn(),
  getPttWindowSize: jest.fn(),
  savePttWindowSize: jest.fn(),
}));

jest.mock('../lib/pttSession', () => ({
  getCurrentPttSession: jest.fn(),
  getPttSessionDate: jest.fn(),
}));

const mockUseAuth = useAuth as jest.Mock;
const mockSubscribeToPttPosts = subscribeToPttPosts as jest.Mock;
const mockGetPttReadState = getPttReadState as jest.Mock;
const mockGetCurrentPttSession = getCurrentPttSession as jest.Mock;
const mockGetPttSessionDate = getPttSessionDate as jest.Mock;
const mockGetPttWindowSize = getPttWindowSize as jest.Mock;

const samplePosts: PttPush[] = [
  { push_tag: '推', userid: 'ruwjo12', content: '大家早安！', time: '08/06 08:30' },
  { push_tag: '推', userid: 'davie11333', content: '早安大爆崩', time: '08/06 08:30' },
];

function expandWidget() {
  fireEvent.click(screen.getByRole('button', { name: '展開 PTT 閒聊' }));
}

describe('PttChatWidget', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetCurrentPttSession.mockReturnValue('intraday');
    mockGetPttSessionDate.mockReturnValue('20260806');
    mockGetPttReadState.mockResolvedValue(-1);
    mockGetPttWindowSize.mockResolvedValue(null);
    mockSubscribeToPttPosts.mockImplementation((_session, _date, callback) => {
      callback(samplePosts);
      return jest.fn();
    });
  });

  it('未登入時不渲染任何內容', () => {
    mockUseAuth.mockReturnValue({ user: null });

    const { container } = render(<PttChatWidget />);

    expect(container).toBeEmptyDOMElement();
  });

  it('登入後預設收合，點擊展開按鈕才顯示訊息列表', async () => {
    mockUseAuth.mockReturnValue({ user: { uid: 'uid-1' } });

    render(<PttChatWidget />);

    expect(screen.getByRole('button', { name: '展開 PTT 閒聊' })).toBeInTheDocument();
    expect(screen.queryByText('大家早安！')).not.toBeInTheDocument();

    expandWidget();

    expect(await screen.findByText('大家早安！')).toBeInTheDocument();
    expect(screen.getByText('早安大爆崩')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '盤中閒聊' })).toBeInTheDocument();
  });

  it('登入後會讀取並套用使用者上次儲存的視窗大小', async () => {
    mockGetPttWindowSize.mockResolvedValue({ width: 500, height: 450 });
    mockUseAuth.mockReturnValue({ user: { uid: 'uid-1' } });

    render(<PttChatWidget />);
    expandWidget();
    await screen.findByText('大家早安！');

    const panel = screen.getByTestId('ptt-widget-panel');
    await waitFor(() => {
      expect(panel).toHaveStyle({ width: '500px', height: '450px' });
    });
  });

  it('儲存的視窗大小會 clamp 在螢幕可視範圍內', async () => {
    mockGetPttWindowSize.mockResolvedValue({ width: 99999, height: 99999 });
    mockUseAuth.mockReturnValue({ user: { uid: 'uid-1' } });

    render(<PttChatWidget />);
    expandWidget();
    await screen.findByText('大家早安！');

    const panel = screen.getByTestId('ptt-widget-panel');
    await waitFor(() => {
      expect(panel.style.width).toBe(`${window.innerWidth * 0.9}px`);
      expect(panel.style.height).toBe(`${window.innerHeight * 0.85}px`);
    });
  });

  it('拖曳調整大小後，停止調整 10 秒才會寫入視窗大小', async () => {
    jest.useFakeTimers({ doNotFake: ['queueMicrotask'] });
    mockUseAuth.mockReturnValue({ user: { uid: 'uid-1' } });

    try {
      render(<PttChatWidget />);
      expandWidget();
      await screen.findByText('大家早安！');

      const handle = screen.getByTestId('ptt-resize-handle');
      const maxWidth = window.innerWidth * 0.9;
      const maxHeight = window.innerHeight * 0.85;
      const expectedWidth = Math.min(maxWidth, 640 + 100);
      const expectedHeight = Math.min(maxHeight, 600 + 100);

      act(() => {
        fireEvent.mouseDown(handle, { clientX: 500, clientY: 500 });
        fireEvent.mouseMove(window, { clientX: 400, clientY: 400 });
        fireEvent.mouseUp(window);
      });

      expect(savePttWindowSize).not.toHaveBeenCalled();

      act(() => {
        jest.advanceTimersByTime(10000);
      });

      await waitFor(() => {
        expect(savePttWindowSize).toHaveBeenCalledWith('uid-1', expectedWidth, expectedHeight);
      });
    } finally {
      jest.useRealTimers();
    }
  });

  it('訊息內容有圖片連結時會顯示圖片預覽並附上可點連結', async () => {
    mockSubscribeToPttPosts.mockImplementation((_session: unknown, _date: unknown, callback: (posts: PttPush[]) => void) => {
      callback([{ push_tag: '推', userid: 'imgfan', content: '笑死 https://i.imgur.com/abc123.jpg', time: '08/06 08:30' }]);
      return jest.fn();
    });
    mockUseAuth.mockReturnValue({ user: { uid: 'uid-1' } });

    render(<PttChatWidget />);
    expandWidget();

    const link = await screen.findByRole('link', { name: 'https://i.imgur.com/abc123.jpg' });
    expect(link).toHaveAttribute('href', 'https://i.imgur.com/abc123.jpg');

    const image = screen.getByRole('img', { name: '推文圖片' });
    expect(image).toHaveAttribute('src', 'https://i.imgur.com/abc123.jpg');
  });

  it('展開時若有下一則未讀訊息，改用手動定位 scrollTop 而不是把已讀訊息整則捲入視野', async () => {
    mockGetPttReadState.mockResolvedValue(0); // 已讀到第 0 則，第 1 則是未讀
    mockUseAuth.mockReturnValue({ user: { uid: 'uid-1' } });
    const scrollIntoViewSpy = jest.spyOn(Element.prototype, 'scrollIntoView');

    render(<PttChatWidget />);
    expandWidget();
    await screen.findByText('大家早安！');
    await waitFor(() => expect(mockGetPttReadState).toHaveBeenCalled());

    expect(scrollIntoViewSpy).not.toHaveBeenCalled();

    scrollIntoViewSpy.mockRestore();
  });

  it('展開時若已讀到最新訊息（沒有未讀訊息），用 scrollIntoView 捲到該則', async () => {
    mockGetPttReadState.mockResolvedValue(samplePosts.length - 1);
    mockUseAuth.mockReturnValue({ user: { uid: 'uid-1' } });
    const scrollIntoViewSpy = jest.spyOn(Element.prototype, 'scrollIntoView');

    render(<PttChatWidget />);
    expandWidget();
    await screen.findByText('大家早安！');

    await waitFor(() => {
      expect(scrollIntoViewSpy).toHaveBeenCalled();
    });

    scrollIntoViewSpy.mockRestore();
  });

  it('點擊收合按鈕後變回浮動圖示按鈕', async () => {
    mockUseAuth.mockReturnValue({ user: { uid: 'uid-1' } });

    render(<PttChatWidget />);
    expandWidget();
    await screen.findByText('大家早安！');

    fireEvent.click(screen.getByRole('button', { name: '收合 PTT 閒聊' }));

    expect(screen.getByRole('button', { name: '展開 PTT 閒聊' })).toBeInTheDocument();
    expect(screen.queryByText('大家早安！')).not.toBeInTheDocument();
  });

  it('有未讀訊息時，收合按鈕會顯示提醒圖示', async () => {
    mockGetPttReadState.mockResolvedValue(-1);
    mockUseAuth.mockReturnValue({ user: { uid: 'uid-1' } });

    render(<PttChatWidget />);

    await waitFor(() => expect(mockGetPttReadState).toHaveBeenCalled());

    expect(screen.getByTestId('unread-indicator')).toBeInTheDocument();
  });

  it('已讀到最新訊息時，收合按鈕不顯示提醒圖示', async () => {
    mockGetPttReadState.mockResolvedValue(samplePosts.length - 1);
    mockUseAuth.mockReturnValue({ user: { uid: 'uid-1' } });

    render(<PttChatWidget />);

    await waitFor(() => expect(mockGetPttReadState).toHaveBeenCalled());

    expect(screen.queryByTestId('unread-indicator')).not.toBeInTheDocument();
  });

  it('用 IntersectionObserver 偵測到訊息捲入可視範圍時會標記為已讀並寫入', async () => {
    jest.useFakeTimers({ doNotFake: ['queueMicrotask'] });

    let capturedCallback: IntersectionObserverCallback = () => {};
    class MockObserver implements IntersectionObserver {
      readonly root: Element | Document | null = null;
      readonly rootMargin = '';
      readonly thresholds: ReadonlyArray<number> = [];
      constructor(callback: IntersectionObserverCallback) {
        capturedCallback = callback;
      }
      observe = jest.fn();
      unobserve = jest.fn();
      disconnect = jest.fn();
      takeRecords = jest.fn(() => []);
    }
    const originalIntersectionObserver = global.IntersectionObserver;
    global.IntersectionObserver = MockObserver;

    try {
      mockUseAuth.mockReturnValue({ user: { uid: 'uid-1' } });
      render(<PttChatWidget />);
      expandWidget();
      await screen.findByText('大家早安！');

      const secondPushEl = document.querySelector('[data-push-index="1"]') as HTMLElement;
      const fakeEntry = { isIntersecting: true, target: secondPushEl } as unknown as IntersectionObserverEntry;
      act(() => {
        capturedCallback([fakeEntry], {} as IntersectionObserver);
      });

      act(() => {
        jest.advanceTimersByTime(10000);
      });

      await waitFor(() => {
        expect(savePttReadState).toHaveBeenCalledWith('uid-1', 'intraday', '20260806', 1);
      });
    } finally {
      global.IntersectionObserver = originalIntersectionObserver;
      jest.useRealTimers();
    }
  });

  it('切換分頁時，前一個分頁尚未觸發的已讀位置寫入不會被取消', async () => {
    jest.useFakeTimers({ doNotFake: ['queueMicrotask'] });

    const capturedCallbacks: IntersectionObserverCallback[] = [];
    class MockObserver implements IntersectionObserver {
      readonly root: Element | Document | null = null;
      readonly rootMargin = '';
      readonly thresholds: ReadonlyArray<number> = [];
      constructor(callback: IntersectionObserverCallback) {
        capturedCallbacks.push(callback);
      }
      observe = jest.fn();
      unobserve = jest.fn();
      disconnect = jest.fn();
      takeRecords = jest.fn(() => []);
    }
    const originalIntersectionObserver = global.IntersectionObserver;
    global.IntersectionObserver = MockObserver;

    const afterhoursPosts: PttPush[] = [
      { push_tag: '推', userid: 'nightowl', content: '收盤閒聊', time: '08/06 14:00' },
      { push_tag: '推', userid: 'nightowl2', content: '再聊一句', time: '08/06 14:01' },
    ];
    mockSubscribeToPttPosts.mockImplementation(
      (requestedSession: string, _date: unknown, callback: (posts: PttPush[]) => void) => {
        callback(requestedSession === 'afterhours' ? afterhoursPosts : samplePosts);
        return jest.fn();
      }
    );

    try {
      mockUseAuth.mockReturnValue({ user: { uid: 'uid-1' } });
      render(<PttChatWidget />);
      expandWidget();
      await screen.findByText('大家早安！');

      // 在盤中閒聊捲到第 2 則，排一個 10 秒後要寫入的 debounce
      const intradayCallback = capturedCallbacks[capturedCallbacks.length - 1];
      const intradayTargetEl = document.querySelector('[data-push-index="1"]') as HTMLElement;
      act(() => {
        intradayCallback(
          [{ isIntersecting: true, target: intradayTargetEl } as unknown as IntersectionObserverEntry],
          {} as IntersectionObserver
        );
      });

      // 還沒到 10 秒就切到盤後閒聊
      act(() => {
        jest.advanceTimersByTime(5000);
      });
      fireEvent.click(screen.getByRole('button', { name: '盤後閒聊' }));
      await screen.findByText('收盤閒聊');

      // 在盤後閒聊也捲到第 2 則，排另一個 10 秒 debounce
      const afterhoursCallback = capturedCallbacks[capturedCallbacks.length - 1];
      const afterhoursTargetEl = document.querySelector('[data-push-index="1"]') as HTMLElement;
      act(() => {
        afterhoursCallback(
          [{ isIntersecting: true, target: afterhoursTargetEl } as unknown as IntersectionObserverEntry],
          {} as IntersectionObserver
        );
      });

      act(() => {
        jest.advanceTimersByTime(10000);
      });

      await waitFor(() => {
        expect(savePttReadState).toHaveBeenCalledWith('uid-1', 'intraday', '20260806', 1);
      });
      expect(savePttReadState).toHaveBeenCalledWith('uid-1', 'afterhours', '20260806', 1);
    } finally {
      global.IntersectionObserver = originalIntersectionObserver;
      jest.useRealTimers();
    }
  });

  it('切換分頁會用新的 session 重新訂閱', async () => {
    mockUseAuth.mockReturnValue({ user: { uid: 'uid-1' } });

    render(<PttChatWidget />);
    expandWidget();
    await screen.findByText('大家早安！');

    fireEvent.click(screen.getByRole('button', { name: '盤後閒聊' }));

    await waitFor(() => {
      expect(mockSubscribeToPttPosts).toHaveBeenCalledWith('afterhours', '20260806', expect.any(Function));
    });
  });
});
