import { resolveWsUrl } from './wsUrl';

describe('resolveWsUrl', () => {
  it('未提供環境變數時，回傳本機開發預設網址', () => {
    expect(resolveWsUrl(undefined)).toBe('ws://localhost:8001/ws/price');
  });

  it('補上缺少的 /ws/price 路徑，並將 https 轉為 wss', () => {
    expect(resolveWsUrl('https://price-broadcaster-xxx.run.app')).toBe(
      'wss://price-broadcaster-xxx.run.app/ws/price'
    );
  });

  it('移除結尾多餘的斜線後再補上路徑', () => {
    expect(resolveWsUrl('https://price-broadcaster-xxx.run.app/')).toBe(
      'wss://price-broadcaster-xxx.run.app/ws/price'
    );
  });

  it('http 轉為 ws', () => {
    expect(resolveWsUrl('http://localhost:8001')).toBe('ws://localhost:8001/ws/price');
  });

  it('已包含 /ws/price 路徑時維持不變', () => {
    expect(resolveWsUrl('wss://price-broadcaster-xxx.run.app/ws/price')).toBe(
      'wss://price-broadcaster-xxx.run.app/ws/price'
    );
  });
});
