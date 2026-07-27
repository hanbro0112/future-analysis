const DEFAULT_WS_BASE_URL = 'ws://localhost:8001';
const PRICE_WS_PATH = '/ws/price';

/**
 * 將環境變數提供的 WebSocket 網址正規化為完整的報價端點網址。
 * 自動修正常見的設定失誤：http(s) 開頭未轉成 ws(s)、缺少 /ws/price 路徑、多餘的結尾斜線。
 */
export function resolveWsUrl(rawUrl: string | undefined): string {
  const base = (rawUrl || DEFAULT_WS_BASE_URL)
    .replace(/^http/, 'ws')
    .replace(/\/+$/, '');

  return base.endsWith(PRICE_WS_PATH) ? base : `${base}${PRICE_WS_PATH}`;
}
