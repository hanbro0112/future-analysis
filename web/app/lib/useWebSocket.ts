import { useEffect, useState } from 'react';
import { isInTradingHours } from './tradingHours';

/**
 * 即時報價資料結構
 */
export interface RealtimePrice {
  /** 商品代碼 */
  code: string;
  /** 價格 */
  price: number;
  /** 加權指數（現貨價格） */
  underlying_price?: number;
  /** 每秒成交量 */
  volume?: number;
}

/**
 * WebSocket 連線狀態
 */
export interface UseWebSocketResult {
  /** 最新報價資料 (key: 商品代碼) */
  prices: Record<string, RealtimePrice>;
  /** 是否已連線 */
  isConnected: boolean;
  /** 連線錯誤訊息 */
  error: string | null;
}

/** 後端推送的單一商品報價 */
interface PriceMessageEntry {
  price: number;
  underlying_price?: number;
  volume?: number;
}

/** WebSocket 因驗證失敗（Token 過期或無效）而關閉時，後端回傳的 close code */
const AUTH_FAILURE_CLOSE_CODE = 4401;

/** WebSocket 因非交易時段（收盤中斷或拒絕連線）而關閉時，後端回傳的 close code */
const NOT_TRADING_HOURS_CLOSE_CODE = 4403;

/** 非交易時段（或被後端以 4403 拒絕）時，再次檢查是否可以連線的間隔 */
const OFF_HOURS_CHECK_INTERVAL_MS = 30000;

/** 連續連線失敗時，重連間隔指數退避的上限 */
const MAX_RECONNECT_INTERVAL_MS = 60000;

/**
 * WebSocket Hook 用於接收即時報價
 * @param getUrl 取得 WebSocket 連線網址（含最新驗證 Token）的函數；傳入 null 時不建立連線（例如尚未登入）。
 *   每次連線（含重連）都會呼叫一次，確保使用的是未過期的 Token；
 *   當上一次連線因驗證失敗而關閉時，會以 forceRefresh=true 呼叫，要求呼叫端強制換發新 Token。
 * @param autoReconnect 是否自動重連 (預設: true)
 * @param reconnectInterval 連線失敗後的首次重連間隔 (ms, 預設: 10000)；連續失敗時每次加倍，上限 60 秒，連上後重置
 *
 * 重連策略：
 * - 曾經連上的連線斷線時立即重連一次（不經過計時器，避免背景分頁的計時器被瀏覽器節流而拖慢）。
 * - 連線失敗則依 reconnectInterval 起算、連續失敗時指數退避（上限 60 秒）重試；
 *   收到 4403 或不在交易時段則每 30 秒檢查一次，所以收盤中斷後，下個時段開始時會自動恢復連線。
 * - 網路恢復（online）、分頁轉為可見、從往返快取還原（pageshow）時，若尚未連線會立即重連並重置退避。
 */
export function useWebSocket(
  getUrl: ((forceRefresh: boolean) => Promise<string | null>) | null,
  autoReconnect: boolean = true,
  reconnectInterval: number = 10000
): UseWebSocketResult {
  const [prices, setPrices] = useState<Record<string, RealtimePrice>>({});
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // 尚未取得連線位址（例如尚未登入）時不連線
    if (!getUrl) {
      setIsConnected(false);
      return;
    }
    const resolveUrl = getUrl;

    // 以下狀態只屬於這一次 effect 執行：依賴變動時舊的連線與延遲中的工作不會影響新的
    let active = true;
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let isConnecting = false;
    // 連續連線失敗（從未連上）的次數，用來計算退避間隔；連上後歸零
    let consecutiveFailures = 0;
    // 上一次連線是否因驗證失敗而關閉；若是，下一次連線需強制換發新 Token
    let forceRefreshNextConnect = false;

    function clearReconnectTimer(): void {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    }

    function scheduleReconnect(delay: number): void {
      if (!autoReconnect || !active) return;
      clearReconnectTimer();
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        void connect();
      }, delay);
    }

    // 連線失敗後排程重試：間隔從 reconnectInterval 起算，每連續失敗一次加倍，上限 60 秒
    function scheduleRetryAfterFailure(): void {
      consecutiveFailures += 1;
      const maxDelay = Math.max(MAX_RECONNECT_INTERVAL_MS, reconnectInterval);
      const delay = Math.min(reconnectInterval * 2 ** (consecutiveFailures - 1), maxDelay);
      scheduleReconnect(delay);
    }

    function handleMessage(data: unknown): void {
      try {
        const message = JSON.parse(String(data));

        // 處理報價資料更新
        // 預期格式: { type: "price", data: { "MXF": { "price": 23450, "underlying_price": 23440, "volume": 150 } }, timestamp: "..." }
        if (message.type === 'price' && typeof message.data === 'object' && message.data !== null) {
          const updatedPrices = Object.entries(message.data).reduce((acc, [code, priceData]) => {
            if (typeof priceData === 'object' && priceData !== null) {
              const entry = priceData as PriceMessageEntry;
              acc[code] = {
                code,
                price: entry.price,
                underlying_price: entry.underlying_price,
                volume: entry.volume,
              };
            }
            return acc;
          }, {} as Record<string, RealtimePrice>);

          // 只在價格真的改變時才更新狀態，避免不必要的重新渲染
          setPrices((prev) => {
            let hasChanges = false;

            // 檢查是否有實際的變化
            for (const [code, newPrice] of Object.entries(updatedPrices)) {
              const oldPrice = prev[code];
              if (!oldPrice ||
                  oldPrice.price !== newPrice.price ||
                  oldPrice.underlying_price !== newPrice.underlying_price ||
                  oldPrice.volume !== newPrice.volume) {
                hasChanges = true;
                break;
              }
            }

            // 如果沒有變化，返回舊的狀態物件，避免重新渲染
            if (!hasChanges) {
              return prev;
            }

            // 有變化時才創建新物件
            return {
              ...prev,
              ...updatedPrices
            };
          });
        }
      } catch {
        // 靜默處理解析錯誤
      }
    }

    function openSocket(url: string): void {
      let socket: WebSocket;
      try {
        socket = new WebSocket(url);
      } catch {
        // 靜默處理連線失敗
        setIsConnected(false);
        scheduleRetryAfterFailure();
        return;
      }

      ws = socket;
      let hasOpened = false;

      // 所有事件處理器都先確認自己仍是目前的連線，避免舊連線遲到的事件清掉新連線或重複重連
      socket.onopen = () => {
        if (ws !== socket) return;
        hasOpened = true;
        consecutiveFailures = 0;
        setIsConnected(true);
        setError(null);
      };

      socket.onmessage = (event) => {
        if (ws !== socket) return;
        handleMessage(event.data);
      };

      socket.onerror = () => {
        if (ws !== socket) return;
        // 靜默處理錯誤，避免控制台報錯
        setIsConnected(false);
      };

      socket.onclose = (event) => {
        if (ws !== socket) return;
        ws = null;
        setIsConnected(false);

        // 因驗證失敗關閉時，下次重連需強制換發新 Token，避免用同一個過期 Token 無限重試
        if (event.code === AUTH_FAILURE_CLOSE_CODE) {
          forceRefreshNextConnect = true;
        }

        if (!autoReconnect) return;

        // 收盤中斷（或被拒絕）：改為定期檢查，下個時段開始後自動恢復
        if (event.code === NOT_TRADING_HOURS_CLOSE_CODE) {
          scheduleReconnect(OFF_HOURS_CHECK_INTERVAL_MS);
          return;
        }

        // 曾經連上的連線斷線：立即重連一次，不經過計時器（背景分頁的計時器會被瀏覽器節流）
        if (hasOpened) {
          void connect();
          return;
        }

        // 連線本身就失敗：依退避間隔重試
        scheduleRetryAfterFailure();
      };
    }

    async function connect(): Promise<void> {
      if (!active || isConnecting) return;

      // 僅在交易時段建立連線；不在時段內則定期再檢查，不會中斷重連流程
      if (!isInTradingHours()) {
        setIsConnected(false);
        scheduleReconnect(OFF_HOURS_CHECK_INTERVAL_MS);
        return;
      }

      // 理論上此時沒有連線，若殘留舊連線先收掉
      if (ws) {
        const stale = ws;
        ws = null;
        stale.close();
      }

      isConnecting = true;
      const forceRefresh = forceRefreshNextConnect;
      forceRefreshNextConnect = false;

      let url: string | null;
      try {
        url = await resolveUrl(forceRefresh);
      } catch {
        // 取得 Token 失敗，靜默處理並排程重試
        url = null;
      }
      isConnecting = false;

      if (!active) return;

      if (!url) {
        setIsConnected(false);
        scheduleRetryAfterFailure();
        return;
      }

      openSocket(url);
    }

    // 網路恢復、分頁轉為可見、從往返快取還原時，若尚未連線就立即重連
    function reconnectNow(): void {
      if (!active || !autoReconnect) return;
      if (ws || isConnecting) return;
      clearReconnectTimer();
      consecutiveFailures = 0;
      void connect();
    }

    function handleVisibilityChange(): void {
      if (document.visibilityState === 'visible') {
        reconnectNow();
      }
    }

    window.addEventListener('online', reconnectNow);
    window.addEventListener('pageshow', reconnectNow);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    void connect();

    // 清理函數
    return () => {
      active = false;
      clearReconnectTimer();
      window.removeEventListener('online', reconnectNow);
      window.removeEventListener('pageshow', reconnectNow);
      document.removeEventListener('visibilitychange', handleVisibilityChange);

      const current = ws;
      ws = null;
      if (current) {
        current.close();
      }
    };
  }, [getUrl, autoReconnect, reconnectInterval]);

  return { prices, isConnected, error };
}
