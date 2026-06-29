/**
 * Firestore 資料存取層
 * 讀取分鐘級期貨資料
 */
import { collection, query, orderBy, limit, getDocs, doc, onSnapshot, Unsubscribe, where } from 'firebase/firestore';
import { db } from './firebase';
import type { MinuteBar } from '../types/minuteData';

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
    
    let q = query(
      collection(db, collectionPath),
      orderBy('time', 'asc')
    );
    
    // 如果指定盤別，加上過濾條件
    if (marketType) {
      q = query(
        collection(db, collectionPath),
        where('market_type', '==', marketType),
        orderBy('time', 'asc')
      );
    }
    
    const querySnapshot = await getDocs(q);
    const data: MinuteBar[] = [];
    
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
        total_bid: docData.total_bid || 0,
        total_ask: docData.total_ask || 0,
        analysis: docData.analysis
      });
    });
    
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
  
  const dateStr = formatDateToYYYYMMDD(dateForQuery);
  return getMinuteData(symbol, dateStr, 'regular');
}

/**
 * 取得今日夜盤資料
 * 夜盤跨日邏輯：00:00-05:59 的資料儲存在前一天
 * @param symbol 商品代碼 (例如: MXF)
 * @returns 夜盤分鐘資料陣列
 */
export async function getTodayNightSession(symbol: string): Promise<MinuteBar[]> {
  const now = new Date();
  const hour = now.getHours();
  
  // 夜盤跨日：如果當前時間在 00:00-05:59，使用前一天的日期
  let dateForQuery = now;
  if (hour >= 0 && hour < 6) {
    dateForQuery = new Date(now);
    dateForQuery.setDate(dateForQuery.getDate() - 1);
  }
  
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
function formatDateToYYYYMMDD(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}${month}${day}`;
}
