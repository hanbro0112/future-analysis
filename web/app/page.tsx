'use client';

/**
 * 期貨資訊分析首頁
 * 顯示台指期分鐘級走勢圖與報價資訊
 */

import { useState, useEffect } from 'react';
import QuoteCard from './components/QuoteCard';
import MinuteChart from './components/MinuteChart';
import AnalysisTable from './components/AnalysisTable';
import { getTodayMinuteData } from './lib/firestoreApi';
import type { TaifexQuote } from './types/futures';
import type { MinuteBar, MinuteChartPoint, AnalysisResult } from './types/minuteData';

export default function Home() {
  // 分鐘級資料狀態
  const [allMinuteData, setAllMinuteData] = useState<MinuteBar[]>([]); // 所有資料
  const [minuteData, setMinuteData] = useState<MinuteBar[]>([]); // 當前顯示的資料
  const [chartData, setChartData] = useState<MinuteChartPoint[]>([]);
  const [quote, setQuote] = useState<TaifexQuote | null>(null);
  const [latestAnalysis, setLatestAnalysis] = useState<AnalysisResult | null>(null);
  const [latestTime, setLatestTime] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [marketType, setMarketType] = useState<'regular' | 'after_hours'>('regular'); // 當前選擇的市場類型

  // 從分鐘資料生成報價資訊
  const generateQuoteFromMinuteData = (data: MinuteBar[]): TaifexQuote | null => {
    if (data.length === 0) return null;

    const openPrice = data[0].open;
    const lastBar = data[data.length - 1];
    const lastPrice = lastBar.close;
    const highPrice = Math.max(...data.map(bar => bar.high));
    const lowPrice = Math.min(...data.map(bar => bar.low));
    const volume = data.reduce((sum, bar) => sum + bar.volume, 0);
    const change = lastPrice - openPrice;
    const changePercent = (change / openPrice) * 100;

    // 修復日期解析：確保正確格式
    let updateTime: Date;
    try {
      // 嘗試多種解析方式
      if (lastBar.date && lastBar.time) {
        let timeStr = lastBar.time;
        
        // 處理 HHMM 格式（沒有冒號）
        if (!timeStr.includes(':')) {
          // 將 '1117' 轉換為 '11:17'
          if (timeStr.length === 4) {
            timeStr = `${timeStr.slice(0, 2)}:${timeStr.slice(2)}`;
          } else if (timeStr.length === 3) {
            // 處理 '917' -> '09:17'
            timeStr = `0${timeStr.slice(0, 1)}:${timeStr.slice(1)}`;
          }
        }
        
        // 方法1：標準 ISO 格式
        const dateTimeStr = `${lastBar.date}T${timeStr}:00`;
        updateTime = new Date(dateTimeStr);
        
        // 如果解析失敗，嘗試其他方式
        if (isNaN(updateTime.getTime())) {
          // 方法2：分別解析日期和時間
          const [year, month, day] = lastBar.date.split('-').map(Number);
          const [hour, minute] = timeStr.split(':').map(Number);
          updateTime = new Date(year, month - 1, day, hour, minute);
        }
      } else {
        // 如果資料不完整，使用當前時間
        updateTime = new Date();
      }
      
      // 最後檢查：如果還是無效，使用當前時間
      if (isNaN(updateTime.getTime())) {
        updateTime = new Date();
      }
    } catch (error) {
      updateTime = new Date();
    }

    return {
      symbol: 'MXF',
      name: '台指期',
      lastPrice,
      openPrice,
      highPrice,
      lowPrice,
      volume,
      change,
      changePercent,
      updateTime
    };
  };

  // 載入分鐘級資料（首次載入全部資料）
  useEffect(() => {
    async function loadMinuteData() {
      setIsLoading(true);
      console.log('🚀 開始載入分鐘資料...');
      
      try {
        const data = await getTodayMinuteData('MXF'); // 台指期商品代碼
        console.log('✅ 載入分鐘資料:', data.length, '筆');
        
        if (data.length > 0) {
          setAllMinuteData(data); // 儲存所有資料
          
          // 判斷市場類型（從最新資料）
          const latestMarketType = data[data.length - 1].market_type;
          setMarketType(latestMarketType);
          
          // 根據市場類型過濾資料
          const filteredData = data.filter(bar => bar.market_type === latestMarketType);
          setMinuteData(filteredData);
          
          // 轉換為圖表資料
          const chartPoints: MinuteChartPoint[] = filteredData.map(bar => ({
            time: bar.time,
            avg_price: bar.avg_price,
            high: bar.high,
            low: bar.low,
            volume: bar.volume,
            buy_volume: bar.buy_volume,
            sell_volume: bar.sell_volume
          }));
          setChartData(chartPoints);
          
          // 更新報價資訊
          const quoteData = generateQuoteFromMinuteData(data);
          setQuote(quoteData);
          
          // 取得最新的分析結果
          const latest = filteredData[filteredData.length - 1];
          if (latest?.analysis) {
            setLatestAnalysis(latest.analysis);
            setLatestTime(`${latest.date} ${latest.time}`);
            console.log('📊 最新分析:', latest.analysis);
          } else {
            console.log('⚠️ 最新資料無分析結果');
          }
        } else {
          console.log('⚠️ 無資料可載入');
        }
      } catch (error) {
        console.error('❌ 載入分鐘資料失敗:', error);
        if (error instanceof Error) {
          console.error('錯誤詳情:', error.message);
          console.error('錯誤堆疊:', error.stack);
        }
      } finally {
        setIsLoading(false);
        console.log('✨ 載入完成');
      }
    }
    
    loadMinuteData();
  }, []);

  // 定期更新分鐘級資料（每分鐘03秒更新一次）
  useEffect(() => {
    if (minuteData.length === 0) return;

    // 計算下一次更新時間（每分鐘的03秒）
    function getNextUpdateDelay() {
      const now = new Date();
      const currentSeconds = now.getSeconds();
      const currentMs = now.getMilliseconds();
      
      // 如果當前秒數小於3秒，等到03秒
      if (currentSeconds < 3) {
        return (3 - currentSeconds) * 1000 - currentMs;
      }
      // 否則等到下一分鐘的03秒
      return (63 - currentSeconds) * 1000 - currentMs;
    }

    // 更新資料函數
    async function updateData() {
      try {
        const data = await getTodayMinuteData('MXF');
        
        if (data.length > minuteData.length) {
          // 有新資料
          setMinuteData(data);
          
          // 判斷市場類型（從最新資料）
          const latestMarketType = data[data.length - 1].market_type;
          setMarketType(latestMarketType);
          
          const chartPoints: MinuteChartPoint[] = data.map(bar => ({
            time: bar.time,
            avg_price: bar.avg_price,
            high: bar.high,
            low: bar.low,
            volume: bar.volume,
            buy_volume: bar.buy_volume,
            sell_volume: bar.sell_volume
          }));
          setChartData(chartPoints);
          
          // 更新報價資訊
          const quoteData = generateQuoteFromMinuteData(data);
          setQuote(quoteData);
          
          const latest = data[data.length - 1];
          if (latest.analysis) {
            setLatestAnalysis(latest.analysis);
            setLatestTime(`${latest.date} ${latest.time}`);
          }
          
          console.log('✅ 資料已更新:', latest.time);
        }
      } catch (error) {
        console.error('更新資料失敗:', error);
      }
    }

    // 設定首次更新
    const firstDelay = getNextUpdateDelay();
    const firstTimeout = setTimeout(() => {
      updateData();
      
      // 之後每60秒更新一次（在每分鐘的03秒）
      const interval = setInterval(updateData, 60000);
      
      return () => clearInterval(interval);
    }, firstDelay);

    return () => clearTimeout(firstTimeout);
  }, [minuteData.length]);

  // 切換市場類型（日盤/夜盤）
  const handleMarketTypeChange = (newMarketType: 'regular' | 'after_hours') => {
    setMarketType(newMarketType);
    
    // 過濾對應的資料
    const filteredData = allMinuteData.filter(bar => bar.market_type === newMarketType);
    setMinuteData(filteredData);
    
    // 更新圖表資料
    const chartPoints: MinuteChartPoint[] = filteredData.map(bar => ({
      time: bar.time,
      avg_price: bar.avg_price,
      high: bar.high,
      low: bar.low,
      volume: bar.volume,
      buy_volume: bar.buy_volume,
      sell_volume: bar.sell_volume
    }));
    setChartData(chartPoints);
    
    // 更新報價資訊
    const quoteData = generateQuoteFromMinuteData(filteredData);
    setQuote(quoteData);
    
    // 更新分析結果
    const latest = filteredData[filteredData.length - 1];
    if (latest?.analysis) {
      setLatestAnalysis(latest.analysis);
      setLatestTime(`${latest.date} ${latest.time}`);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* 頁面標題 */}
      <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            期貨資訊分析
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            台指期分鐘級走勢與多空分析
          </p>
        </div>
      </header>

      {/* 主要內容 */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {isLoading ? (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            <p className="mt-4 text-gray-500">載入資料中...</p>
          </div>
        ) : (
          <>
            {/* 市場類型切換按鈕 */}
            <div className="mb-6 flex gap-3">
              <button
                onClick={() => handleMarketTypeChange('regular')}
                className={`px-6 py-2.5 rounded-lg font-medium transition-all ${
                  marketType === 'regular'
                    ? 'bg-blue-600 text-white shadow-md'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                日盤 (08:45-13:45)
              </button>
              <button
                onClick={() => handleMarketTypeChange('after_hours')}
                className={`px-6 py-2.5 rounded-lg font-medium transition-all ${
                  marketType === 'after_hours'
                    ? 'bg-blue-600 text-white shadow-md'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                夜盤 (15:00-05:00)
              </button>
            </div>

            {/* 台指期分鐘級走勢 */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
              {/* 左側：報價卡片 */}
              <div className="lg:col-span-1">
                {quote && <QuoteCard quote={quote} analysis={latestAnalysis} />}
              </div>

              {/* 右側：分鐘級走勢圖 */}
              <div className="lg:col-span-2">
                <MinuteChart 
                  data={chartData} 
                  title="台指期分鐘級走勢"
                  marketType={marketType}
                />
              </div>
            </div>

            {/* 多空分析結果 */}
            <div className="border-t border-gray-200 dark:border-gray-700 pt-8">
              <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-6">
                多空分析
              </h2>
              <AnalysisTable 
                analysis={latestAnalysis} 
                time={latestTime}
              />
            </div>
          </>
        )}
      </main>
    </div>
  );
}

