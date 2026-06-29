'use client';

/**
 * 期貨資訊分析首頁
 * 顯示台指期分鐘級走勢圖與報價資訊
 */

import { useState, useEffect } from 'react';
import QuoteCard from './components/QuoteCard';
import MinuteChart from './components/MinuteChart';

import { getTodayMinuteData } from './lib/firestoreApi';
import type { TaifexQuote } from './types/futures';
import type { MinuteBar, MinuteChartPoint, AnalysisResult } from './types/minuteData';

/**
 * 根據當前時間判斷預設盤面類型
 * - 日盤時段（週一至週五 08:45-13:45）=> 'regular'
 * - 夜盤時段（週一至週五 15:00-次日 05:00）=> 'after_hours'
 * - 週六全天 => 'after_hours'（顯示週五夜盤資料）
 * - 週日全天 => 'after_hours'（等待週日晚上夜盤開始）
 */
const getDefaultMarketType = (): 'regular' | 'after_hours' => {
  const now = new Date();
  const day = now.getDay(); // 0 = 週日, 1 = 週一, ..., 6 = 週六
  const hours = now.getHours();
  const minutes = now.getMinutes();
  const totalMinutes = hours * 60 + minutes;

  // 週六全天 => 夜盤
  if (day === 6) {
    return 'after_hours';
  }

  // 週日全天 => 夜盤
  if (day === 0) {
    return 'after_hours';
  }

  // 週一至週五判斷時間段
  // 日盤時段：08:45-13:45 (525-825 分鐘)
  const daySessionStart = 8 * 60 + 45; // 525
  const daySessionEnd = 13 * 60 + 45; // 825

  // 夜盤時段：15:00-05:00
  const nightSessionStart = 15 * 60; // 900

  if (totalMinutes >= daySessionStart && totalMinutes <= daySessionEnd) {
    // 日盤時段
    return 'regular';
  } else if (totalMinutes >= nightSessionStart || totalMinutes < 5 * 60) {
    // 夜盤時段（15:00 之後或 05:00 之前）
    return 'after_hours';
  } else {
    // 其他時間（05:00-08:45 或 13:45-15:00）=> 預設夜盤
    return 'after_hours';
  }
};

/**
 * 獲取最近的交易日（排除週末）
 * @param date 基準日期
 * @returns 最近的交易日
 */
const getLastTradingDay = (date: Date): Date => {
  const result = new Date(date);
  const day = result.getDay();
  
  // 如果是週六，往前推到週五
  if (day === 6) {
    result.setDate(result.getDate() - 1);
  }
  // 如果是週日，往前推到週五
  else if (day === 0) {
    result.setDate(result.getDate() - 2);
  }
  
  return result;
};

/**
 * 獲取日盤的交易日期
 * @returns 當前交易日
 */
const getDaySessionDate = (): Date => {
  const now = new Date();
  return getLastTradingDay(now);
};

/**
 * 獲取夜盤的交易日期
 * @returns 夜盤對應的交易日
 */
const getNightSessionDate = (): Date => {
  const now = new Date();
  const hours = now.getHours();
  const minutes = now.getMinutes();
  const totalMinutes = hours * 60 + minutes;
  
  // 14:50 之前顯示前一天的夜盤
  if (totalMinutes < 14 * 60 + 50) {
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    return getLastTradingDay(yesterday);
  }
  
  // 14:50 之後顯示當天的夜盤
  return getLastTradingDay(now);
};

/**
 * 格式化日期為 MM/DD 格式
 */
const formatDate = (date: Date): string => {
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const day = date.getDate().toString().padStart(2, '0');
  return `${month}/${day}`;
};

/**
 * 獲取日盤顯示文字
 */
const getDaySessionLabel = (): string => {
  const date = getDaySessionDate();
  return `日盤 ${formatDate(date)} (08:45-13:45)`;
};

/**
 * 獲取夜盤顯示文字
 */
const getNightSessionLabel = (): string => {
  const date = getNightSessionDate();
  return `夜盤 ${formatDate(date)} (15:00-05:00)`;
};

export default function Home() {
  // 分鐘級資料狀態
  const [allMinuteData, setAllMinuteData] = useState<MinuteBar[]>([]); // 所有資料
  const [minuteData, setMinuteData] = useState<MinuteBar[]>([]); // 當前顯示的資料
  const [chartData, setChartData] = useState<MinuteChartPoint[]>([]);
  const [quote, setQuote] = useState<TaifexQuote | null>(null);
  const [latestAnalysis, setLatestAnalysis] = useState<AnalysisResult | null>(null);
  const [latestTime, setLatestTime] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [marketType, setMarketType] = useState<'regular' | 'after_hours'>(getDefaultMarketType()); // 根據當前時間判斷預設盤面
  const [isMarketTypeManuallySelected, setIsMarketTypeManuallySelected] = useState(false);

  const resolveMarketType = (
    data: MinuteBar[],
    preferredMarketType: 'regular' | 'after_hours'
  ): 'regular' | 'after_hours' => {
    const hasPreferredData = data.some(bar => bar.market_type === preferredMarketType);

    if (hasPreferredData) {
      return preferredMarketType;
    }

    // 若偏好盤面沒有資料，退回最新資料所屬盤面
    return data[data.length - 1].market_type;
  };

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

          // 預設使用時間判斷的盤面，若無資料則退回最新資料盤面
          const defaultMarketType = getDefaultMarketType();
          const resolvedMarketType = resolveMarketType(data, defaultMarketType);
          setMarketType(resolvedMarketType);

          // 根據解析後的市場類型過濾資料
          const filteredData = data.filter(bar => bar.market_type === resolvedMarketType);
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
          
          // 更新報價資訊（依目前盤面）
          const quoteData = generateQuoteFromMinuteData(filteredData);
          setQuote(quoteData);
          
          // 取得最新的分析結果
          const latest = filteredData[filteredData.length - 1];
          if (latest?.analysis) {
            setLatestAnalysis(latest.analysis);
            // 格式化時間：HHMM -> HH:MM
            const formattedTime = latest.time.length === 4 
              ? `${latest.time.slice(0, 2)}:${latest.time.slice(2)}` 
              : latest.time;
            setLatestTime(`${latest.date} ${formattedTime}`);
            console.log('📊 最新分析:', latest.analysis);
          } else {
            setLatestAnalysis(null);
            setLatestTime('');
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
          setAllMinuteData(data);

          const preferredMarketType = isMarketTypeManuallySelected
            ? marketType
            : getDefaultMarketType();
          const resolvedMarketType = resolveMarketType(data, preferredMarketType);

          if (!isMarketTypeManuallySelected) {
            setMarketType(resolvedMarketType);
          }

          const filteredData = data.filter(bar => bar.market_type === resolvedMarketType);
          setMinuteData(filteredData);

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
          
          // 更新報價資訊（依目前盤面）
          const quoteData = generateQuoteFromMinuteData(filteredData);
          setQuote(quoteData);

          const latest = filteredData[filteredData.length - 1];
          if (latest.analysis) {
            setLatestAnalysis(latest.analysis);
            // 格式化時間：HHMM -> HH:MM
            const formattedTime = latest.time.length === 4 
              ? `${latest.time.slice(0, 2)}:${latest.time.slice(2)}` 
              : latest.time;
            setLatestTime(`${latest.date} ${formattedTime}`);
          } else {
            setLatestAnalysis(null);
            setLatestTime('');
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
  }, [minuteData.length, marketType, isMarketTypeManuallySelected]);

  // 切換市場類型（日盤/夜盤）
  const handleMarketTypeChange = (newMarketType: 'regular' | 'after_hours') => {
    setIsMarketTypeManuallySelected(true);
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
      // 格式化時間：HHMM -> HH:MM
      const formattedTime = latest.time.length === 4 
        ? `${latest.time.slice(0, 2)}:${latest.time.slice(2)}` 
        : latest.time;
      setLatestTime(`${latest.date} ${formattedTime}`);
    } else {
      setLatestAnalysis(null);
      setLatestTime('');
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* 頁面標題 */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <h1 className="text-xl font-bold text-gray-800">
            期貨資訊分析
          </h1>
          <p className="text-xs text-gray-500 mt-1">
            台指期分鐘級走勢與多空分析
          </p>
        </div>
      </header>

      {/* 主要內容 */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {isLoading ? (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            <p className="mt-4 text-gray-600">載入資料中...</p>
          </div>
        ) : (
          <>
            {/* 市場類型切換按鈕 */}
            <div className="mb-6 flex gap-2">
              <button
                onClick={() => handleMarketTypeChange('regular')}
                className={`px-5 py-2 rounded-lg text-sm font-medium transition-all ${
                  marketType === 'regular'
                    ? 'bg-blue-600 text-white shadow-md'
                    : 'bg-white text-gray-700 hover:bg-gray-50 border border-gray-300'
                }`}
              >
                {getDaySessionLabel()}
              </button>
              <button
                onClick={() => handleMarketTypeChange('after_hours')}
                className={`px-5 py-2 rounded-lg text-sm font-medium transition-all ${
                  marketType === 'after_hours'
                    ? 'bg-blue-600 text-white shadow-md'
                    : 'bg-white text-gray-700 hover:bg-gray-50 border border-gray-300'
                }`}
              >
                {getNightSessionLabel()}
              </button>
            </div>

            {/* 台指期分鐘級走勢 */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* 左側：報價卡片 */}
              <div className="lg:col-span-1">
                <QuoteCard quote={quote} analysis={latestAnalysis} />
              </div>

              {/* 右側：分鐘級走勢圖 */}
              <div className="lg:col-span-2">
                <MinuteChart 
                  data={chartData} 
                  title="台指期分鐘級走勢"
                  marketType={marketType}
                  latestAnalysis={latestAnalysis}
                />
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

