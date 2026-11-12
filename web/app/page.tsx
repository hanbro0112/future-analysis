'use client';

/**
 * 期貨資訊分析首頁
 * 顯示台指期分鐘級走勢圖與報價資訊
 */

import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import QuoteCard from './components/QuoteCard';
import MinuteChart from './components/MinuteChart';
import DailyAnalysisCard from './components/DailyAnalysisCard';
import ChipReportCard from './components/ChipReportCard';
import ThemeToggle from './components/ThemeToggle';
import LoginScreen from './components/LoginScreen';
import { useWebSocket } from './lib/useWebSocket';
import { isInTradingHours } from './lib/tradingHours';
import { useAuth } from './lib/AuthContext';
import { auth } from './lib/firebase';
import { onIdTokenChanged } from 'firebase/auth';
import { resolveWsUrl } from './lib/wsUrl';

import { 
  getTodayMinuteData, 
  getTodayDaySession, 
  getTodayNightSession,
  getMinuteDataAfter,
  getDaySessionClosePrice,
  getDaySessionDate as getDaySessionCollectionDate,
  getNightSessionDate as getNightSessionCollectionDate,
  getLatestBarTimestamp,
  mergeMinuteBars,
  getTodayDailyReport,
  type DailyReport
} from './lib/firestoreApi';
import {
  getDaySessionDateKey,
  getDefaultMarketType,
  getNightSessionDateKey,
  getReferencePriceDates,
  shouldSkipHistoryPolling,
  type MarketType,
  type ReferencePriceDates
} from './lib/marketSession';
import type { TaifexQuote } from './types/futures';
import type { MinuteBar, MinuteChartPoint, AnalysisResult } from './types/minuteData';

// Price Broadcaster WebSocket 網址（本地開發預設連 localhost，正式環境由環境變數指定）
// resolveWsUrl 會自動修正 http(s) 開頭、缺少 /ws/price 路徑等常見設定失誤
const WS_URL = resolveWsUrl(process.env.NEXT_PUBLIC_WS_URL);

/**
 * 將 YYYY-MM-DD 格式化為 MM/DD
 */
const formatDateKey = (dateKey: string): string => dateKey.slice(5).replace('-', '/');

/**
 * 獲取日盤顯示文字
 */
const getDaySessionLabel = (): string => {
  return `日盤 ${formatDateKey(getDaySessionDateKey())} (08:45-13:45)`;
};

/**
 * 獲取夜盤顯示文字
 */
const getNightSessionLabel = (): string => {
  return `夜盤 ${formatDateKey(getNightSessionDateKey())} (15:00-05:00)`;
};

export default function Home() {
  const { user, loading: authLoading, signOut } = useAuth();

  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900">
        <p className="text-sm text-gray-500 dark:text-gray-400">載入中...</p>
      </div>
    );
  }

  if (!user) {
    return <LoginScreen />;
  }

  return <Dashboard onSignOut={signOut} />;
}

function Dashboard({ onSignOut }: { onSignOut: () => Promise<void> }) {
  // 分鐘級資料狀態
  const [allMinuteData, setAllMinuteData] = useState<MinuteBar[]>([]); // 所有資料
  // 供定時器（閉包只建立一次）讀取最新的全部資料，增量合併必須建立在最新資料上
  const allMinuteDataRef = useRef<MinuteBar[]>([]);
  // 各盤別目前已載入的「盤別_集合日期」，一致時只做增量讀取，換日／換集合時改整批重讀
  const loadedSessionKeysRef = useRef<Record<MarketType, string | null>>({
    regular: null,
    after_hours: null
  });
  const [minuteData, setMinuteData] = useState<MinuteBar[]>([]); // 當前顯示的資料
  const [chartData, setChartData] = useState<MinuteChartPoint[]>([]);
  const [dayChartData, setDayChartData] = useState<MinuteChartPoint[]>([]); // 日盤圖表資料
  const [nightChartData, setNightChartData] = useState<MinuteChartPoint[]>([]); // 夜盤圖表資料
  const [quote, setQuote] = useState<TaifexQuote | null>(null);
  const [latestAnalysis, setLatestAnalysis] = useState<AnalysisResult | null>(null);
  const [latestTime, setLatestTime] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [marketType, setMarketType] = useState<MarketType>(getDefaultMarketType()); // 根據當前時間判斷預設盤面
  // 目前參考價對應的日期，跨日／換盤後與最新日期不同時需重新取得參考價
  const referenceDatesRef = useRef<ReferencePriceDates | null>(null);
  const [isMarketTypeManuallySelected, setIsMarketTypeManuallySelected] = useState(false);
  const [dayReferencePrice, setDayReferencePrice] = useState<number | null>(null); // 日盤漲跌幅參考價
  const [nightReferencePrice, setNightReferencePrice] = useState<number | null>(null); // 夜盤漲跌幅參考價
  const [dailyReport, setDailyReport] = useState<DailyReport | null>(null); // 每日分析報告
  const [isDailyReportLoading, setIsDailyReportLoading] = useState(true); // 每日分析載入狀態

  // 是否已登入，用來決定是否開始建立 WebSocket 連線
  const [isSignedIn, setIsSignedIn] = useState(false);

  useEffect(() => {
    const unsubscribe = onIdTokenChanged(auth, (firebaseUser) => {
      setIsSignedIn(!!firebaseUser);
    });
    return unsubscribe;
  }, []);

  // 每次連線（含重連）都即時取得最新 Firebase ID Token，避免使用已過期的 Token 重連；
  // forceRefresh 為 true 時（上次連線因驗證失敗而關閉）強制向 Firebase 換發新 Token
  const getWsUrl = useCallback(async (forceRefresh: boolean): Promise<string | null> => {
    const firebaseUser = auth.currentUser;
    if (!firebaseUser) return null;

    try {
      const token = await firebaseUser.getIdToken(forceRefresh);
      return `${WS_URL}?token=${encodeURIComponent(token)}`;
    } catch (err) {
      return null;
    }
  }, []);

  // WebSocket 即時報價連接（尚未登入前不建立連線）
  const { prices: realtimePrices, isConnected: wsConnected } = useWebSocket(
    isSignedIn ? getWsUrl : null
  );

  // 使用 useMemo 提取即時報價，避免不必要的重新渲染
  const realtimePrice = useMemo(() => {
    return Object.values(realtimePrices)[0] || null;
  }, [realtimePrices]);

  // 使用 useMemo 計算當前參考價格
  const currentReferencePrice = useMemo(() => {
    return marketType === 'regular' ? dayReferencePrice : nightReferencePrice;
  }, [marketType, dayReferencePrice, nightReferencePrice]);

  /**
   * 取得日盤與夜盤的參考價（用於漲跌幅計算），只靠日期推算，不需等分鐘資料載入
   * - 夜盤：使用夜盤所屬交易日當天的日盤收盤價
   * - 日盤：使用前一交易日日盤收盤價
   * 兩個收盤價各只讀一筆文件並行取得，讀不到時回傳 null（由呼叫端退回開盤價）
   */
  const fetchReferencePrices = async (
    dates: ReferencePriceDates
  ): Promise<{ day: number | null; night: number | null }> => {
    const [day, night] = await Promise.all([
      getDaySessionClosePrice('MXF', dates.day),
      getDaySessionClosePrice('MXF', dates.night)
    ]);
    console.log('🔵 參考價 - 日盤（前一交易日收盤）:', day, dates.day, '夜盤（當天日盤收盤）:', night, dates.night);
    return { day, night };
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
        // 分鐘資料與參考價並行取得，全部就緒後才一起更新狀態，避免定時器拿到尚未算出的參考價
        // 參考價對應的日期一併記錄，之後跨日／換盤時才知道要重新取得
        const referenceDates = getReferencePriceDates();
        const [data, referencePrices] = await Promise.all([
          getTodayMinuteData('MXF'), // 台指期商品代碼
          fetchReferencePrices(referenceDates)
        ]);
        referenceDatesRef.current = referenceDates;

        // 記錄初始載入的集合日期，之後的輪詢才知道可以用增量讀取
        loadedSessionKeysRef.current = {
          regular: `regular_${getDaySessionCollectionDate()}`,
          after_hours: `after_hours_${getNightSessionCollectionDate()}`
        };

        allMinuteDataRef.current = data;
        setAllMinuteData(data); // 儲存所有資料

        // 依時間規則決定盤面；該盤沒有資料就顯示空盤，不退回另一盤（休市日由日期推算前一交易日）
        const resolvedMarketType = getDefaultMarketType();
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
        
        // 日盤和夜盤的參考價格（用於漲跌幅計算），讀不到時退回當前盤別第一筆開盤價
        const dayRefPrice = referencePrices.day ?? dayData[0]?.open ?? 0;
        const nightRefPrice = referencePrices.night ?? nightData[0]?.open ?? 0;
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

  // 讀取每日分析報告（僅首次載入，之後由使用者點擊更新圖示手動觸發）
  const loadDailyReport = useCallback(async () => {
    try {
      setIsDailyReportLoading(true);
      const report = await getTodayDailyReport();
      setDailyReport(report);
    } catch (error) {
      console.error('❌ 載入每日分析失敗:', error);
      setDailyReport(null);
    } finally {
      setIsDailyReportLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDailyReport();
  }, [loadDailyReport]);

  const isUpdatingRef = useRef(false);

  // 定時器只建立一次，更新函式透過這個 ref 讀取最新狀態，避免閉包拿到過期的值
  const liveStateRef = useRef({
    wsConnected,
    isMarketTypeManuallySelected,
    marketType,
    dayReferencePrice,
    nightReferencePrice
  });
  useEffect(() => {
    liveStateRef.current = {
      wsConnected,
      isMarketTypeManuallySelected,
      marketType,
      dayReferencePrice,
      nightReferencePrice
    };
  });

  // 初次載入完成後即啟動定時器；即使目前顯示的盤沒有資料（例如 14:51 剛切到尚未開盤的夜盤）也要持續輪詢
  const isInitialLoadDone = !isLoading;

  // 定期更新分鐘級資料（每分鐘03秒更新一次）
  useEffect(() => {
    if (!isInitialLoadDone) return;

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
      
      // 檢查是否可略過本輪更新
      // 條件：websocket 連線正常、沒有手動選擇盤別、不在交易時段，且沒有待處理的盤別切換或參考價換日
      // （有即時資料不需要更新歷史）；否則無論是斷線降級或手動選擇，都應該更新
      const gateState = liveStateRef.current;
      const referenceDates = getReferencePriceDates();
      const referenceDatesChanged =
        referenceDatesRef.current?.day !== referenceDates.day ||
        referenceDatesRef.current?.night !== referenceDates.night;
      const marketTypeSwitchPending =
        !gateState.isMarketTypeManuallySelected && gateState.marketType !== getDefaultMarketType();

      if (shouldSkipHistoryPolling({
        wsConnected: gateState.wsConnected,
        isMarketTypeManuallySelected: gateState.isMarketTypeManuallySelected,
        inTradingHours: isInTradingHours(),
        marketTypeSwitchPending,
        referenceDatesChanged
      })) {
        isUpdatingRef.current = false;
        return;
      }

      try {
        // 判斷當前應該是什麼時段
        const currentSessionType = getDefaultMarketType();

        const currentData = allMinuteDataRef.current;
        const currentSessionBars = currentData.filter(bar => bar.market_type === currentSessionType);
        const collectionDate = currentSessionType === 'regular' ? getDaySessionCollectionDate() : getNightSessionCollectionDate();
        const sessionKey = `${currentSessionType}_${collectionDate}`;
        const cursor = getLatestBarTimestamp(currentSessionBars);

        let mergedData: MinuteBar[];
        let sessionData: MinuteBar[];
        // 換日／換集合（例如 14:51 切到當天尚未開盤的夜盤）時，空資料也是合法結果，必須套用到畫面；
        // 同一集合重讀到空資料則視為暫時性失敗，保留原本畫面
        const isNewSession =
          marketTypeSwitchPending || loadedSessionKeysRef.current[currentSessionType] !== sessionKey;

        if (loadedSessionKeysRef.current[currentSessionType] === sessionKey && cursor) {
          // 同一個集合：只讀游標之後的新資料（約 1-2 筆）再合併，不重讀整個集合
          const newBars = await getMinuteDataAfter('MXF', collectionDate, cursor, currentSessionType);
          mergedData = mergeMinuteBars(currentData, newBars);
          sessionData = mergedData.filter(bar => bar.market_type === currentSessionType);
        } else {
          // 首次載入該盤別、尚無資料或換日／換集合：整批重讀該盤別，之後再改走增量
          sessionData = currentSessionType === 'regular'
            ? await getTodayDaySession('MXF')
            : await getTodayNightSession('MXF');

          // 合併資料：保留其他時段的資料，更新當前時段的資料
          const otherSessionData = currentData.filter(bar => bar.market_type !== currentSessionType);
          mergedData = currentSessionType === 'regular'
            ? [...sessionData, ...otherSessionData]  // 日盤在前
            : [...otherSessionData, ...sessionData]; // 夜盤在後

          loadedSessionKeysRef.current[currentSessionType] = sessionKey;
        }

        if (sessionData.length > 0 || isNewSession || referenceDatesChanged) {
          allMinuteDataRef.current = mergedData;
          setAllMinuteData(mergedData);

          // 請求期間使用者可能已切換盤別，這裡重新讀取最新狀態
          const { isMarketTypeManuallySelected, marketType } = liveStateRef.current;
          let { dayReferencePrice, nightReferencePrice } = liveStateRef.current;

          const resolvedMarketType = isMarketTypeManuallySelected
            ? marketType
            : currentSessionType;

          // 參考價日期已改變（跨日或換盤）：重新取得參考價，讀不到時退回該盤第一筆開盤價
          if (referenceDatesChanged) {
            const prices = await fetchReferencePrices(referenceDates);
            referenceDatesRef.current = referenceDates;
            dayReferencePrice = prices.day
              ?? mergedData.find(bar => bar.market_type === 'regular')?.open
              ?? 0;
            nightReferencePrice = prices.night
              ?? mergedData.find(bar => bar.market_type === 'after_hours')?.open
              ?? 0;
            setDayReferencePrice(dayReferencePrice);
            setNightReferencePrice(nightReferencePrice);
          }

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

          // console.log('✅ 資料已更新:', latest?.time);
        }
      } catch (error) {
        console.error('更新資料失敗:', error);
      } finally {
        isUpdatingRef.current = false;
      }
    }

    // 每輪結束後重新計算下一個 03 秒，避免固定間隔的 setInterval 隨時間漂移
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;

    const scheduleNext = () => {
      timeoutId = setTimeout(async () => {
        await updateData();
        if (!cancelled) scheduleNext();
      }, getNextUpdateDelay());
    };
    scheduleNext();

    return () => {
      cancelled = true;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [isInitialLoadDone]);

  // 監聽 WebSocket 重連，自動切回當前時段
  useEffect(() => {
    // 只在 WebSocket 連線且用戶未手動選擇盤別時，自動切回當前時段
    if (wsConnected && !isMarketTypeManuallySelected) {
      const currentSessionType = getDefaultMarketType();
      
      if (marketType !== currentSessionType) {
        setMarketType(currentSessionType);
        
        // 更新顯示資料（該盤沒有資料時也要切換並清空，不留下另一盤的畫面）
        const filteredData = allMinuteData.filter(bar => bar.market_type === currentSessionType);
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
          taiex: bar.analysis?.basis != null && currentSessionType === 'regular' ? bar.avg_price - bar.analysis.basis : undefined
        }));
        setChartData(chartPoints);

        // 更新報價和分析
        const refPrice = currentSessionType === 'regular' ? dayReferencePrice : nightReferencePrice;
        if (filteredData.length === 0) {
          setQuote(null);
        } else if (refPrice) {
          const quoteData = generateQuoteFromMinuteData(filteredData, refPrice);
          setQuote(quoteData);
        }

        const latest = filteredData[filteredData.length - 1];
        if (latest?.analysis) {
          setLatestAnalysis(latest.analysis);
          const formattedTime = latest.time.length === 4
            ? `${latest.time.slice(0, 2)}:${latest.time.slice(2)}`
            : latest.time;
          setLatestTime(`${latest.date} ${formattedTime}`);
        } else if (filteredData.length === 0) {
          setLatestAnalysis(null);
          setLatestTime('');
        }
      }
    }
  }, [wsConnected, isMarketTypeManuallySelected]);

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
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* 頁面標題 */}
      <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold text-gray-800 dark:text-gray-100">
                期貨資訊分析
              </h1>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                台指期分鐘級走勢與多空分析
              </p>
            </div>
            <div className="flex items-center gap-2">
              {/* 主題切換按鈕 */}
              <ThemeToggle />
              {/* 登出按鈕 */}
              <button
                onClick={onSignOut}
                className="p-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 text-sm text-gray-700 dark:text-gray-200 transition-colors"
              >
                登出
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* 主要內容 */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {isLoading ? (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 dark:border-blue-400"></div>
            <p className="mt-4 text-gray-600 dark:text-gray-300">載入資料中...</p>
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
                    : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 border border-gray-300 dark:border-gray-600'
                }`}
              >
                {getDaySessionLabel()}
              </button>
              <button
                onClick={() => handleMarketTypeChange('after_hours')}
                className={`px-5 py-2 rounded-lg text-sm font-medium transition-all ${
                  marketType === 'after_hours'
                    ? 'bg-blue-600 text-white shadow-md'
                    : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 border border-gray-300 dark:border-gray-600'
                }`}
              >
                {getNightSessionLabel()}
              </button>
            </div>

            {/* 台指期分鐘級走勢 */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* 左側：報價卡片 */}
              <div className="lg:col-span-1">
                <QuoteCard 
                  quote={quote} 
                  realtimePrice={marketType === getDefaultMarketType() && wsConnected ? realtimePrice : null}
                  referencePrice={currentReferencePrice}
                  analysis={latestAnalysis}
                  isConnected={wsConnected}
                  isCurrentSession={marketType === getDefaultMarketType()}
                />
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
                  referencePrice={currentReferencePrice}
                />
              </div>
            </div>

            {/* 分隔線 */}
            <div className="my-8 border-t border-gray-200"></div>

            {/* 每日分析報告 */}
            <DailyAnalysisCard
              report={dailyReport}
              isLoading={isDailyReportLoading}
              onRefresh={loadDailyReport}
            />
            
            {/* 分隔線 */}
            <div className="my-8 border-t border-gray-200"></div>
            
            {/* 籌碼報告 */}
            <ChipReportCard />
          </>
        )}
      </main>
    </div>
  );
}

