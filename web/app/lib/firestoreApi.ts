/**
 * Firestore 資料存取層
 * 讀取分鐘級期貨資料與每日分析
 */
import { collection, query, orderBy, limit, getDocs, doc, getDoc, onSnapshot, Unsubscribe } from 'firebase/firestore';
import { db } from './firebase';
import type { MinuteBar } from '../types/minuteData';

/**
 * 獲取最近的交易日（排除週末）
 * @param date 基準日期
 * @returns 最近的交易日
 */
export function getLastTradingDay(date: Date): Date {
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
}

/**
 * 取得指定日期的所有分鐘資料
 * @param symbol 商品代碼 (例如: MXF)
 * @param date 日期 (格式: YYYYMMDD)
 * @param marketType 盤別過濾 ('regular' = 日盤, 'after_hours' = 夜盤, undefined = 全部)
 * @returns 分鐘資料陣列
 */
export async function getMinuteData(
  symbol: string, 
  date: string, 
  marketType?: 'regular' | 'after_hours'
): Promise<MinuteBar[]> {
  try {
    const collectionPath = `market/${symbol}/${date}`;
    console.log(`📊 讀取 Firestore 路徑: ${collectionPath}`, marketType ? `盤別: ${marketType}` : '全部');

    // 集合 ID 為日期（每天不同），不使用 where + orderBy 的複合查詢
    // （否則每天都要重新建立 composite index），盤別改在讀取後於前端過濾
    const q = query(
      collection(db, collectionPath),
      orderBy('time', 'asc')
    );

    const querySnapshot = await getDocs(q);
    let data: MinuteBar[] = [];

    querySnapshot.forEach((docSnap) => {
      const docData = docSnap.data();
      data.push({
        code: docData.code || symbol,
        timestamp: docData.timestamp,
        date: docData.date || date,
        time: docData.time || docSnap.id,
        market_type: docData.market_type || 'regular',
        open: docData.open || 0,
        high: docData.high || 0,
        low: docData.low || 0,
        close: docData.close || 0,
        volume: docData.volume || 0,
        buy_volume: docData.buy_volume || 0,
        sell_volume: docData.sell_volume || 0,
        avg_price: docData.avg_price || 0,
        tick_count: docData.tick_count || 0,
        bid_total: docData.total_bid || 0,
        ask_total: docData.total_ask || 0,
        analysis: docData.analysis
      });
    });

    if (marketType) {
      data = data.filter((bar) => bar.market_type === marketType);
    }

    // 如果是夜盤資料，需要重新排序（15:00-23:59 在前，00:00-05:59 在後）
    if (marketType === 'after_hours' && data.length > 0) {
      data.sort((a, b) => {
        const timeA = parseInt(a.time);
        const timeB = parseInt(b.time);
        
        // 夜盤邏輯：15:00-23:59 (900-1439) 排在前，00:00-05:59 (0-359) 排在後
        const isEarlyA = timeA < 600;  // 00:00-05:59
        const isEarlyB = timeB < 600;
        
        if (isEarlyA && !isEarlyB) return 1;   // A 是凌晨，B 不是 -> A 排後面
        if (!isEarlyA && isEarlyB) return -1;  // A 不是凌晨，B 是 -> A 排前面
        return timeA - timeB;  // 同區段，按時間升序
      });
    }
    
    console.log(`✅ 讀取成功: ${data.length} 筆資料`);
    return data;
  } catch (error) {
    console.error('❌ 讀取分鐘資料失敗:', error);
    if (error instanceof Error) {
      console.error('錯誤詳情:', error.message);
    }
    return [];
  }
}

/**
 * 取得今日日盤資料
 * 邏輯：08:30 前查詢前一個交易日的日盤
 * @param symbol 商品代碼 (例如: MXF)
 * @returns 日盤分鐘資料陣列
 */
export async function getTodayDaySession(symbol: string): Promise<MinuteBar[]> {
  const now = new Date();
  const hour = now.getHours();
  const minute = now.getMinutes();
  const timeInMinutes = hour * 60 + minute;
  
  // 08:30 前使用前一天的日期
  let dateForQuery = now;
  if (timeInMinutes < 8 * 60 + 30) {  // 小於 08:30
    dateForQuery = new Date(now);
    dateForQuery.setDate(dateForQuery.getDate() - 1);
  }
  
  // 確保日期是交易日（排除週末）
  dateForQuery = getLastTradingDay(dateForQuery);
  
  const dateStr = formatDateToYYYYMMDD(dateForQuery);
  return getMinuteData(symbol, dateStr, 'regular');
}

/**
 * 取得今日夜盤資料
 * 夜盤跨日邏輯：
 * - 00:00-14:49 使用前一天的夜盤資料
 * - 14:50-23:59 使用當天的夜盤資料
 * @param symbol 商品代碼 (例如: MXF)
 * @returns 夜盤分鐘資料陣列
 */
export async function getTodayNightSession(symbol: string): Promise<MinuteBar[]> {
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
  
  // 確保日期是交易日（排除週末）
  dateForQuery = getLastTradingDay(dateForQuery);
  
  const dateStr = formatDateToYYYYMMDD(dateForQuery);
  return getMinuteData(symbol, dateStr, 'after_hours');
}

/**
 * 取得今日資料（日盤 + 夜盤）
 * @param symbol 商品代碼 (例如: MXF)
 * @returns 分鐘資料陣列（日盤在前，夜盤在後）
 */
export async function getTodayMinuteData(symbol: string): Promise<MinuteBar[]> {
  const [dayData, nightData] = await Promise.all([
    getTodayDaySession(symbol),
    getTodayNightSession(symbol)
  ]);
  
  console.log(`📈 日盤: ${dayData.length} 筆, 夜盤: ${nightData.length} 筆`);
  
  // 日盤在前，夜盤在後
  return [...dayData, ...nightData];
}

/**
 * 取得最新 N 筆分鐘資料
 * @param symbol 商品代碼
 * @param date 日期
 * @param count 資料筆數
 * @returns 分鐘資料陣列
 */
export async function getLatestMinuteData(symbol: string, date: string, count: number): Promise<MinuteBar[]> {
  try {
    const collectionPath = `market/${symbol}/${date}`;
    const q = query(
      collection(db, collectionPath),
      orderBy('time', 'desc'),
      limit(count)
    );
    
    const querySnapshot = await getDocs(q);
    const data: MinuteBar[] = [];
    
    querySnapshot.forEach((doc) => {
      data.push({
        ...doc.data() as MinuteBar,
        time: doc.id
      });
    });
    
    // 反轉順序（從舊到新）
    return data.reverse();
  } catch (error) {
    console.error('讀取最新分鐘資料失敗:', error);
    return [];
  }
}

/**
 * 監聽指定日期的分鐘資料變化
 * @param symbol 商品代碼
 * @param date 日期
 * @param callback 資料更新回調函數
 * @returns 取消監聽函數
 */
export function subscribeToMinuteData(
  symbol: string,
  date: string,
  callback: (data: MinuteBar[]) => void
): Unsubscribe {
  const collectionPath = `market/${symbol}/${date}`;
  const q = query(
    collection(db, collectionPath),
    orderBy('time', 'asc')
  );
  
  return onSnapshot(q, (querySnapshot) => {
    const data: MinuteBar[] = [];
    querySnapshot.forEach((doc) => {
      data.push({
        ...doc.data() as MinuteBar,
        time: doc.id
      });
    });
    callback(data);
  }, (error) => {
    console.error('監聽分鐘資料失敗:', error);
  });
}

/**
 * 監聽今日資料變化
 * @param symbol 商品代碼
 * @param callback 資料更新回調函數
 * @returns 取消監聽函數
 */
export function subscribeToTodayData(
  symbol: string,
  callback: (data: MinuteBar[]) => void
): Unsubscribe {
  const today = new Date();
  const dateStr = formatDateToYYYYMMDD(today);
  return subscribeToMinuteData(symbol, dateStr, callback);
}

/**
 * 格式化日期為 YYYYMMDD
 */
export function formatDateToYYYYMMDD(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}${month}${day}`;
}

/**
 * 每日分析報告類型
 */
export interface DailyReport {
  date: string;          // YYYYMMDD 格式
  raw_content: string;   // Gemini 生成的分析內容
  created_at?: string;   // 創建時間
  model_used?: string;   // 使用的 AI 模型
}

/**
 * 取得指定日期的每日分析報告
 * @param date 日期 (格式: YYYYMMDD)
 * @returns 每日分析報告，若無資料則返回 null
 */
export async function getDailyReport(date: string): Promise<DailyReport | null> {
  try {
    const docPath = `daily_reports/${date}`;
    console.log(`📄 讀取每日分析: ${docPath}`);
    
    const docRef = doc(db, docPath);
    const docSnap = await getDoc(docRef);
    
    if (docSnap.exists()) {
      const data = docSnap.data();
      console.log(`✅ 讀取成功: ${date}`);
      return {
        date: date,
        raw_content: data.raw_content || '',
        created_at: data.created_at || '',
        model_used: data.model_used || ''
      };
    } else {
      console.log(`⚠️ 無資料: ${date}`);
      return null;
    }
  } catch (error) {
    console.error('❌ 讀取每日分析失敗:', error);
    return null;
  }
}

/**
 * 取得今日的每日分析報告
 * 邏輯：08:00 前查詢前一個交易日的分析，08:01 後查詢當天的分析
 * @returns 每日分析報告，若無資料則返回 null
 */
export async function getTodayDailyReport(): Promise<DailyReport | null> {
  const now = new Date();
  const hour = now.getHours();
  const minute = now.getMinutes();
  const timeInMinutes = hour * 60 + minute;
  
  // 08:00 前使用前一個交易日的日期
  let dateForQuery = now;
  if (timeInMinutes <= 8 * 60) {  // 小於等於 08:00
    dateForQuery = new Date(now);
    dateForQuery.setDate(dateForQuery.getDate() - 1);
  }
  
  // 確保日期是交易日（排除週末）
  dateForQuery = getLastTradingDay(dateForQuery);
  
  const dateStr = formatDateToYYYYMMDD(dateForQuery);
  console.log(`📅 查詢每日分析日期: ${dateStr} (當前時間: ${hour}:${String(minute).padStart(2, '0')})`);
  
  return getDailyReport(dateStr);
}
