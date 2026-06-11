'use client';

/**
 * 期貨資訊分析首頁
 * 顯示台指期即時走勢圖與報價資訊
 */

import { useState, useEffect } from 'react';
import FuturesChart from './components/FuturesChart';
import QuoteCard from './components/QuoteCard';
import { 
  generateInitialPriceData, 
  generateNewPricePoint,
  generateMockQuote 
} from './lib/mockData';
import type { PricePoint, TaifexQuote } from './types/futures';

export default function Home() {
  // 價格資料狀態
  const [priceData, setPriceData] = useState<PricePoint[]>([]);
  // 報價資料狀態
  const [quote, setQuote] = useState<TaifexQuote | null>(null);
  // 開盤價
  const openPrice = 21800;

  // 初始化資料
  useEffect(() => {
    const initialData = generateInitialPriceData(openPrice, 60);
    setPriceData(initialData);
    
    const lastPrice = initialData[initialData.length - 1].price;
    setQuote(generateMockQuote(lastPrice));
  }, []);

  // 即時更新資料（每 3 秒更新一次）
  useEffect(() => {
    if (priceData.length === 0) return;

    const interval = setInterval(() => {
      setPriceData(prevData => {
        // 產生新的價格點
        const lastPrice = prevData[prevData.length - 1].price;
        const newPoint = generateNewPricePoint(lastPrice);
        
        // 保持最多 60 個資料點
        const newData = [...prevData.slice(-59), newPoint];
        
        // 更新報價資訊
        setQuote(generateMockQuote(newPoint.price));
        
        return newData;
      });
    }, 3000); // 每 3 秒更新

    return () => clearInterval(interval);
  }, [priceData.length]);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* 頁面標題 */}
      <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            期貨資訊分析
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            台指期即時走勢與報價
          </p>
        </div>
      </header>

      {/* 主要內容 */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 左側：報價卡片 */}
          <div className="lg:col-span-1">
            {quote && <QuoteCard quote={quote} />}
          </div>

          {/* 右側：折線圖 */}
          <div className="lg:col-span-2">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                即時走勢圖
              </h2>
              <FuturesChart data={priceData} openPrice={openPrice} />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

