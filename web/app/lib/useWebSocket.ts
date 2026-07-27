import { useEffect, useState, useRef } from 'react';
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

/** WebSocket 因驗證失敗（Token 過期或無效）而關閉時，後端回傳的 close code */
const AUTH_FAILURE_CLOSE_CODE = 4401;

/**
 * WebSocket Hook 用於接收即時報價
 * @param getUrl 取得 WebSocket 連線網址（含最新驗證 Token）的函數；傳入 null 時不建立連線（例如尚未登入）。
 *   每次連線（含重連）都會呼叫一次，確保使用的是未過期的 Token；
 *   當上一次連線因驗證失敗而關閉時，會以 forceRefresh=true 呼叫，要求呼叫端強制換發新 Token。
 * @param autoReconnect 是否自動重連 (預設: true)
 * @param reconnectInterval 重連間隔 (ms, 預設: 10000)
 */
export function useWebSocket(
  getUrl: ((forceRefresh: boolean) => Promise<string | null>) | null,
  autoReconnect: boolean = true,
  reconnectInterval: number = 10000
): UseWebSocketResult {
  const [prices, setPrices] = useState<Record<string, RealtimePrice>>({});
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    // 上一次連線是否因驗證失敗而關閉；若是，下一次連線需強制換發新 Token
    let forceRefreshNextConnect = false;

    async function connect() {
      // 尚未取得連線位址（例如尚未登入）時不連線
      if (!getUrl) {
        setIsConnected(false);
        return;
      }

      // 僅在交易時段建立連線
      if (!isInTradingHours()) {
        setIsConnected(false);
        // 非交易時段，等待一段時間後再檢查
        if (autoReconnect && isMountedRef.current) {
          reconnectTimeoutRef.current = setTimeout(() => {
            if (isMountedRef.current) {
              connect();
            }
          }, 60000); // 1 分鐘後再檢查
        }
        return;
      }

      // 清除舊連線
      if (wsRef.current) {
        wsRef.current.close();
      }

      const forceRefresh = forceRefreshNextConnect;
      forceRefreshNextConnect = false;

      let url: string | null;
      try {
        url = await getUrl(forceRefresh);
      } catch (err) {
        // 取得 Token 失敗，靜默處理並排程重試
        url = null;
      }

      if (!isMountedRef.current) return;

      if (!url) {
        setIsConnected(false);
        if (autoReconnect && isMountedRef.current) {
          reconnectTimeoutRef.current = setTimeout(() => {
            if (isMountedRef.current) {
              connect();
            }
          }, reconnectInterval);
        }
        return;
      }

      try {
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
          if (!isMountedRef.current) return;
          setIsConnected(true);
          setError(null);
        };

        ws.onmessage = (event) => {
          if (!isMountedRef.current) return;

          try {
            const message = JSON.parse(event.data);
            
            // 處理報價資料更新
            // 預期格式: { type: "price", data: { "MXF": { "price": 23450, "underlying_price": 23440, "volume": 150 } }, timestamp: "..." }
            if (message.type === 'price' && typeof message.data === 'object' && message.data !== null) {
              const pricesData = message.data;
              const updatedPrices = Object.entries(pricesData).reduce((acc, [code, priceData]) => {
                if (typeof priceData === 'object' && priceData !== null) {
                  acc[code] = {
                    code,
                    price: (priceData as any).price,
                    underlying_price: (priceData as any).underlying_price,
                    volume: (priceData as any).volume,
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
          } catch (err) {
            // 靜默處理解析錯誤
          }
        };

        ws.onerror = () => {
          if (!isMountedRef.current) return;
          // 靜默處理錯誤，避免控制台報錯
          setIsConnected(false);
        };

        ws.onclose = (event) => {
          if (!isMountedRef.current) return;
          setIsConnected(false);
          wsRef.current = null;

          // 因驗證失敗關閉時，下次重連需強制換發新 Token，避免用同一個過期 Token 無限重試
          if (event.code === AUTH_FAILURE_CLOSE_CODE) {
            forceRefreshNextConnect = true;
          }

          // 僅在交易時段自動重連
          if (autoReconnect && isMountedRef.current && isInTradingHours()) {
            reconnectTimeoutRef.current = setTimeout(() => {
              if (isMountedRef.current && isInTradingHours()) {
                connect();
              }
            }, reconnectInterval);
          }
        };
      } catch (err) {
        // 靜默處理連線失敗
        setIsConnected(false);

        // 僅在交易時段自動重連
        if (autoReconnect && isMountedRef.current && isInTradingHours()) {
          reconnectTimeoutRef.current = setTimeout(() => {
            if (isMountedRef.current && isInTradingHours()) {
              connect();
            }
          }, reconnectInterval);
        }
      }
    }

    connect();

    // 清理函數
    return () => {
      isMountedRef.current = false;
      
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [getUrl, autoReconnect, reconnectInterval]);

  return { prices, isConnected, error };
}
