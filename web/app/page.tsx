'use client';

/**
 * 期貨資訊分析首頁
 * 顯示台指期分鐘級走勢圖與報價資訊
 */

import { useState, useEffect, useRef } from 'react';
import QuoteCard from './components/QuoteCard';
import MinuteChart from './components/MinuteChart';

import { 
  getTodayMinuteData, 
  getTodayDaySession, 
  getTodayNightSession, 
  getMinuteData, 
  formatDateToYYYYMMDD 
} from './lib/firestoreApi';
import type { TaifexQuote } from './types/futures';
import type { MinuteBar, MinuteChartPoint, AnalysisResult } from './types/minuteData';

/**
 * 根據當前時間判斷預設盤面類型（包含延後 3 分鐘以更新最後一筆資料）
 * - 日盤時段（週一至週五 08:45-13:48）=> 'regular'
 * - 夜盤時段（週一至週五 15:00-次日 05:03）=> 'after_hours'
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
  // 日盤時段：08:45-13:48 (525-828 分鐘) - 延後 3 分鐘以更新最後一筆
  const daySessionStart = 8 * 60 + 45; // 525
  const daySessionEnd = 13 * 60 + 48; // 828 (原本 13:45 + 3 分鐘)

  // 夜盤時段：15:00-05:03 - 延後 3 分鐘以更新最後一筆
  const nightSessionStart = 15 * 60; // 900

  if (totalMinutes >= daySessionStart && totalMinutes <= daySessionEnd) {
    // 日盤時段
    return 'regular';
  } else if (totalMinutes >= nightSessionStart || totalMinutes < 5 * 60 + 3) {
    // 夜盤時段（15:00 之後或 05:03 之前）
    return 'after_hours';
  } else {
    // 其他時間（05:03-08:45 或 13:48-15:00）=> 預設夜盤
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
 * 邏輯：08:30 前顯示前一個交易日的日盤
 * @returns 當前交易日
 */
const getDaySessionDate = (): Date => {
  const now = new Date();
  const hour = now.getHours();
  const minute = now.getMinutes();
  const timeInMinutes = hour * 60 + minute;
  
  // 08:30 前使用前一天的日期
  let dateForSession = now;
  if (timeInMinutes < 8 * 60 + 30) {  // 小於 08:30
    dateForSession = new Date(now);
    dateForSession.setDate(dateForSession.getDate() - 1);
  }
  
  return getLastTradingDay(dateForSession);
};

/**
 * 判斷當前是否在交易時段內（包含延後 3 分鐘以更新最後一筆資料）
 * @returns 是否在交易時段（日盤或夜盤）
 */
const isInTradingHours = (): boolean => {
  const now = new Date();
  const day = now.getDay(); // 0 = 週日, 1 = 週一, ..., 6 = 週六
  const hours = now.getHours();
  const minutes = now.getMinutes();
  const totalMinutes = hours * 60 + minutes;

  // 週六全天不交易
  if (day === 6) {
    return false;
  }

  // 週日：只有夜盤（15:00 開始）
  if (day === 0) {
    return totalMinutes >= 15 * 60; // 15:00 之後
  }

  // 週一至週五
  // 日盤時段：08:45-13:48 (525-828 分鐘) - 延後 3 分鐘以更新最後一筆
  const daySessionStart = 8 * 60 + 45; // 525
  const daySessionEnd = 13 * 60 + 48; // 828 (原本 13:45 + 3 分鐘)

  // 夜盤時段：15:00-次日05:03 - 延後 3 分鐘以更新最後一筆
  const nightSessionStart = 15 * 60; // 900
  const nightSessionEnd = 5 * 60 + 3; // 303 (原本 05:00 + 3 分鐘)

  // 判斷是否在交易時段
  if (totalMinutes >= daySessionStart && totalMinutes <= daySessionEnd) {
    // 日盤時段
    return true;
  } else if (totalMinutes >= nightSessionStart || totalMinutes < nightSessionEnd) {
    // 夜盤時段（15:00 之後或 05:03 之前）
    return true;
  }

  // 其他時間不在交易時段
  return false;
};

/**
 * 獲取夜盤的交易日期
 * 夜盤跨日邏輯：
 * - 00:00-14:49 使用前一天的夜盤資料
 * - 14:50-23:59 使用當天的夜盤資料
 * @returns 夜盤對應的交易日
 */
const getNightSessionDate = (): Date => {
  const now = new Date();
  const hour = now.getHours();
  const minute = now.getMinutes();
  const timeInMinutes = hour * 60 + minute;
  
  // 14:50 前使用前一天的日期
  let dateForQuery = now;
  if (timeInMinutes < 14 * 60 + 50) {  // 小於 14:50
    dateForQuery = new Date(now);
    dateForQuery.setDate(dateForQuery.getDate() - 1);
  }
  
  return getLastTradingDay(dateForQuery);
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
  const [dayChartData, setDayChartData] = useState<MinuteChartPoint[]>([]); // 日盤圖表資料
  const [nightChartData, setNightChartData] = useState<MinuteChartPoint[]>([]); // 夜盤圖表資料
  const [quote, setQuote] = useState<TaifexQuote | null>(null);
  const [latestAnalysis, setLatestAnalysis] = useState<AnalysisResult | null>(null);
  const [latestTime, setLatestTime] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [marketType, setMarketType] = useState<'regular' | 'after_hours'>(getDefaultMarketType()); // 根據當前時間判斷預設盤面
  const [isMarketTypeManuallySelected, setIsMarketTypeManuallySelected] = useState(false);
  const [dayReferencePrice, setDayReferencePrice] = useState<number | null>(null); // 日盤漲跌幅參考價
  const [nightReferencePrice, setNightReferencePrice] = useState<number | null>(null); // 夜盤漲跌幅參考價

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

  /**
   * 計算參考價格（用於漲跌幅計算）
   * - 夜盤：使用當天日盤收盤價
   * - 日盤：使用前一天日盤收盤價
   * - 無資料時：使用當前盤別第一筆開盤價
   */
  const calculateReferencePrice = async (marketType: 'regular' | 'after_hours', allData: MinuteBar[], currentData: MinuteBar[]): Promise<number> => {
    try {
      if (marketType === 'after_hours') {
        // 夜盤：使用當天日盤收盤價
        const dayData = allData.filter(bar => bar.market_type === 'regular');
        if (dayData.length > 0) {
          const refPrice = dayData[dayData.length - 1].close;
          console.log('🔵 夜盤參考價（當天日盤收盤）:', refPrice);
          return refPrice;
        }
      } else {
        // 日盤：使用前一天日盤收盤價
        // 取當前查看的日盤資料日期，而非系統當前時間
        if (currentData.length > 0) {
          const currentDate = new Date(currentData[0].date);
          const yesterday = new Date(currentDate);
          yesterday.setDate(yesterday.getDate() - 1);
          
          const dateStr = formatDateToYYYYMMDD(yesterday);
          const yesterdayData = await getMinuteData('MXF', dateStr, 'regular');
          if (yesterdayData.length > 0) {
            const refPrice = yesterdayData[yesterdayData.length - 1].close;
            console.log('🔵 日盤參考價（前一天日盤收盤）:', refPrice, '日期:', dateStr);
            return refPrice;
          }
        }
      }
    } catch (error) {
      console.error('❌ 計算參考價失敗:', error);
    }
    
    // 後備方案：使用當前盤別第一筆開盤價
    if (currentData.length > 0) {
      console.log('⚠️ 使用後備方案：當前盤別開盤價:', currentData[0].open);
      return currentData[0].open;
    }
    
    return 0;
  };

  // 從分鐘資料生成報價資訊
  const generateQuoteFromMinuteData = (data: MinuteBar[], refPrice: number): TaifexQuote | null => {
    if (data.length === 0) return null;

    // 使用參考價作為基準
    const basePrice = refPrice;
    const lastBar = data[data.length - 1];
    const lastPrice = lastBar.close;
    const highPrice = Math.max(...data.map(bar => bar.high));
    const lowPrice = Math.min(...data.map(bar => bar.low));
    const volume = data.reduce((sum, bar) => sum + bar.volume, 0);
    const change = lastPrice - basePrice;
    const changePercent = (change / basePrice) * 100;

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
        let dateTimeStr = `${lastBar.date}T${timeStr}:00`;
        updateTime = new Date(dateTimeStr);
        
        // 夜盤跨日修正：如果是夜盤且時間在 00:00-05:59，日期需要加一天
        const [hour] = timeStr.split(':').map(Number);
        if (lastBar.market_type === 'after_hours' && hour >= 0 && hour < 6) {
          updateTime.setDate(updateTime.getDate() + 1);
        }
        
        // 如果解析失敗，嘗試其他方式
        if (isNaN(updateTime.getTime())) {
          // 方法2：分別解析日期和時間
          const [year, month, day] = lastBar.date.split('-').map(Number);
          const [h, minute] = timeStr.split(':').map(Number);
          updateTime = new Date(year, month - 1, day, h, minute);
          
          // 夜盤跨日修正
          if (lastBar.market_type === 'after_hours' && h >= 0 && h < 6) {
            updateTime.setDate(updateTime.getDate() + 1);
          }
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
      openPrice: basePrice,
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
      
      try {
        const data = await getTodayMinuteData('MXF'); // 台指期商品代碼
        
        if (data.length > 0) {
          setAllMinuteData(data); // 儲存所有資料

          // 預設使用時間判斷的盤面，若無資料則退回最新資料盤面
          const defaultMarketType = getDefaultMarketType();
          const resolvedMarketType = resolveMarketType(data, defaultMarketType);
          setMarketType(resolvedMarketType);

          // 分離日盤和夜盤數據
          const dayData = data.filter(bar => bar.market_type === 'regular');
          const nightData = data.filter(bar => bar.market_type === 'after_hours');

          // 轉換為圖表資料 - 日盤
          const dayChartPoints: MinuteChartPoint[] = dayData.map(bar => ({
            time: bar.time,
            avg_price: bar.avg_price,
            high: bar.high,
            low: bar.low,
            volume: bar.volume,
            buy_volume: bar.buy_volume,
            sell_volume: bar.sell_volume,
            taiex: bar.analysis?.basis != null ? bar.avg_price - bar.analysis.basis : undefined
          }));
          setDayChartData(dayChartPoints);

          // 轉換為圖表資料 - 夜盤
          const nightChartPoints: MinuteChartPoint[] = nightData.map(bar => ({
            time: bar.time,
            avg_price: bar.avg_price,
            high: bar.high,
            low: bar.low,
            volume: bar.volume,
            buy_volume: bar.buy_volume,
            sell_volume: bar.sell_volume
          }));
          setNightChartData(nightChartPoints);

          // 根據解析後的市場類型過濾資料
          const filteredData = data.filter(bar => bar.market_type === resolvedMarketType);
          setMinuteData(filteredData);
          
          // 轉換為圖表資料（當前顯示的資料，保持向後兼容）
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
          
          // 計算日盤和夜盤的參考價格（用於漲跌幅計算）
          const dayRefPrice = await calculateReferencePrice('regular', data, dayData);
          const nightRefPrice = await calculateReferencePrice('after_hours', data, nightData);
          setDayReferencePrice(dayRefPrice);
          setNightReferencePrice(nightRefPrice);
          console.log('📍 初始化基準價 - 日盤:', dayRefPrice, '夜盤:', nightRefPrice);
          
          // 更新報價資訊（依目前盤面）
          const refPrice = resolvedMarketType === 'regular' ? dayRefPrice : nightRefPrice;
          const quoteData = generateQuoteFromMinuteData(filteredData, refPrice);
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
      }
    }
    
    loadMinuteData();
  }, []);

  // 使用 ref 追蹤定時器是否已啟動
  const updateTimerRef = useRef<{ timeout?: NodeJS.Timeout; interval?: NodeJS.Timeout }>({});
  const isUpdatingRef = useRef(false);
  const timerInitializedRef = useRef(false);

  // 定期更新分鐘級資料（每分鐘03秒更新一次）
  useEffect(() => {
    // 只在首次有資料且未初始化時啟動定時器
    if (minuteData.length === 0 || timerInitializedRef.current) return;
    
    timerInitializedRef.current = true;

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

    // 更新資料函數（僅更新當前交易時段）
    async function updateData() {
      // 防止重複執行
      if (isUpdatingRef.current) {
        return;
      }
      
      isUpdatingRef.current = true;
      
      // 檢查是否在交易時段內
      if (!isInTradingHours()) {
        console.log('⏸️ 非交易時段，跳過更新');
        isUpdatingRef.current = false;
        return;
      }

      try {
        // 判斷當前應該是什麼時段
        const currentSessionType = getDefaultMarketType();
        
        // 只獲取當前時段的資料
        const sessionData = currentSessionType === 'regular' 
          ? await getTodayDaySession('MXF')
          : await getTodayNightSession('MXF');
        
        console.log(`🔄 更新 ${currentSessionType === 'regular' ? '日盤' : '夜盤'} 資料: ${sessionData.length} 筆`);

        // 合併資料：保留其他時段的資料，更新當前時段的資料
        const otherSessionData = allMinuteData.filter(bar => bar.market_type !== currentSessionType);
        const mergedData = currentSessionType === 'regular'
          ? [...sessionData, ...otherSessionData]  // 日盤在前
          : [...otherSessionData, ...sessionData]; // 夜盤在後

        if (sessionData.length > 0) {
          setAllMinuteData(mergedData);

          const preferredMarketType = isMarketTypeManuallySelected
            ? marketType
            : currentSessionType;
          const resolvedMarketType = resolveMarketType(mergedData, preferredMarketType);

          const filteredData = mergedData.filter(bar => bar.market_type === resolvedMarketType);
          
          if (!isMarketTypeManuallySelected) {
            setMarketType(resolvedMarketType);
          }

          setMinuteData(filteredData);

          // 更新當前顯示的圖表資料（向後兼容）
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

          // 更新日盤和夜盤的圖表資料
          const dayData = mergedData.filter(bar => bar.market_type === 'regular');
          const nightData = mergedData.filter(bar => bar.market_type === 'after_hours');

          const dayChartPoints: MinuteChartPoint[] = dayData.map(bar => ({
            time: bar.time,
            avg_price: bar.avg_price,
            high: bar.high,
            low: bar.low,
            volume: bar.volume,
            buy_volume: bar.buy_volume,
            sell_volume: bar.sell_volume,
            taiex: bar.analysis?.basis != null ? bar.avg_price - bar.analysis.basis : undefined
          }));
          setDayChartData(dayChartPoints);

          const nightChartPoints: MinuteChartPoint[] = nightData.map(bar => ({
            time: bar.time,
            avg_price: bar.avg_price,
            high: bar.high,
            low: bar.low,
            volume: bar.volume,
            buy_volume: bar.buy_volume,
            sell_volume: bar.sell_volume
          }));
          setNightChartData(nightChartPoints);
          
          // 使用對應的參考價
          const currentRefPrice = resolvedMarketType === 'regular' ? dayReferencePrice : nightReferencePrice;
          
          // 更新報價資訊（依目前盤面，使用參考價）
          const quoteData = generateQuoteFromMinuteData(filteredData, currentRefPrice ?? 0);
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
      } finally {
        isUpdatingRef.current = false;
      }
    }

    // 設定首次更新
    const firstDelay = getNextUpdateDelay();
    const firstTimeout = setTimeout(() => {
      updateData();
      
      // 之後每60秒更新一次（在每分鐘的03秒）
      const interval = setInterval(updateData, 60000);
      updateTimerRef.current.interval = interval;
    }, firstDelay);
    
    updateTimerRef.current.timeout = firstTimeout;

    return () => {
      if (updateTimerRef.current.timeout) {
        clearTimeout(updateTimerRef.current.timeout);
      }
      if (updateTimerRef.current.interval) {
        clearInterval(updateTimerRef.current.interval);
      }
      updateTimerRef.current = {};
      timerInitializedRef.current = false;
    };
  }, [minuteData.length]);

  // 切換市場類型（日盤/夜盤）
  const handleMarketTypeChange = async (newMarketType: 'regular' | 'after_hours') => {
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
      sell_volume: bar.sell_volume,
      taiex: bar.analysis?.basis != null && newMarketType === 'regular' ? bar.avg_price - bar.analysis.basis : undefined
    }));
    setChartData(chartPoints);
    
    // 使用對應的參考價格（不重新計算）
    const refPrice = newMarketType === 'regular' ? dayReferencePrice : nightReferencePrice;
    
    // 更新報價資訊
    const quoteData = generateQuoteFromMinuteData(filteredData, refPrice!);
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
                  dayData={dayChartData}
                  nightData={nightChartData}
                  title="台指期分鐘級走勢"
                  marketType={marketType}
                  latestAnalysis={latestAnalysis}
                  isLoading={isLoading}
                  referencePrice={marketType === 'regular' ? dayReferencePrice : nightReferencePrice}
                />
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

