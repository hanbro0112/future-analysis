/**
 * 模擬台指期資料生成器
 * 用於在 Firestore 資料結構確定前進行開發測試
 */

import type { PricePoint, TaifexQuote } from '../types/futures';

/**
 * 產生初始價格資料點陣列
 * @param basePrice - 基礎價格
 * @param dataPoints - 資料點數量
 * @returns 價格資料點陣列
 */
export function generateInitialPriceData(
  basePrice: number = 21800,
  dataPoints: number = 60
): PricePoint[] {
  const data: PricePoint[] = [];
  const now = new Date();
  let currentPrice = basePrice;

  for (let i = dataPoints; i > 0; i--) {
    const timestamp = new Date(now.getTime() - i * 60 * 1000); // 每分鐘一個資料點
    
    // 模擬價格波動 (-50 到 +50)
    const priceChange = (Math.random() - 0.5) * 100;
    currentPrice = Math.max(basePrice - 200, Math.min(basePrice + 200, currentPrice + priceChange));
    
    data.push({
      timestamp,
      price: Math.round(currentPrice)
    });
  }

  return data;
}

/**
 * 產生新的價格資料點
 * @param lastPrice - 最後一個價格
 * @returns 新的價格資料點
 */
export function generateNewPricePoint(lastPrice: number): PricePoint {
  // 模擬價格波動 (-30 到 +30)
  const priceChange = (Math.random() - 0.5) * 60;
  const newPrice = Math.round(lastPrice + priceChange);
  
  return {
    timestamp: new Date(),
    price: newPrice
  };
}

/**
 * 產生模擬台指期報價
 * @param currentPrice - 當前價格
 * @returns 台指期報價資料
 */
export function generateMockQuote(currentPrice: number): TaifexQuote {
  const openPrice = 21800;
  const change = currentPrice - openPrice;
  const changePercent = (change / openPrice) * 100;
  
  return {
    symbol: 'TXFR1',
    name: '台指期(近月)',
    lastPrice: currentPrice,
    openPrice,
    highPrice: Math.max(currentPrice, openPrice + 100),
    lowPrice: Math.min(currentPrice, openPrice - 100),
    volume: Math.floor(Math.random() * 100000) + 50000,
    change,
    changePercent,
    updateTime: new Date()
  };
}
