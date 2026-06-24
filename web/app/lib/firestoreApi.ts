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
 * 往回查詢最近有資料的日期
 * @param symbol 商品代碼
 * @param marketType 盤別
 * @param maxDays 最多往回查詢天數
 * @returns 最近有資料的日期字串和資料
 */
async function findLatestAvailableData(
  symbol: string,
  marketType: 'regular' | 'after_hours',
  maxDays: number = 7
): Promise<{ date: string; data: MinuteBar[] }> {
  const today = new Date();
  
  for (let i = 0; i < maxDays; i++) {
    const checkDate = new Date(today);
    checkDate.setDate(checkDate.getDate() - i);
    const dateStr = formatDateToYYYYMMDD(checkDate);
    
    const data = await getMinuteData(symbol, dateStr, marketType);
    if (data.length > 0) {
      console.log(`✅ 找到最近資料: ${dateStr} (${i === 0 ? '今天' : `${i}天前`})`);
      return { date: dateStr, data };
    }
  }
  
  console.warn(`⚠️ 往回查詢 ${maxDays} 天都沒有資料`);
  return { date: formatDateToYYYYMMDD(today), data: [] };
}

/**
 * 取得今日日盤資料（若無則使用最近一次的日盤資料）
 * @param symbol 商品代碼 (例如: MXF)
 * @returns 日盤分鐘資料陣列
 */
export async function getTodayDaySession(symbol: string): Promise<MinuteBar[]> {
  const result = await findLatestAvailableData(symbol, 'regular');
  return result.data;
}

/**
 * 取得今日夜盤資料（處理跨日情況，若無則使用最近一次的夜盤資料）
 * @param symbol 商品代碼 (例如: MXF)
 * @returns 夜盤分鐘資料陣列
 */
export async function getTodayNightSession(symbol: string): Promise<MinuteBar[]> {
  const now = new Date();
  const currentHour = now.getHours();
  
  // 夜盤時間：15:00-05:00（次日）
  // 如果當前時間 < 05:00，表示是跨日的夜盤，需要查詢昨天的資料
  // 如果當前時間 >= 05:00，查詢今天的資料
  
  if (currentHour < 5) {
    // 凌晨時段，查詢昨天和今天的夜盤資料
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const yesterdayStr = formatDateToYYYYMMDD(yesterday);
    const todayStr = formatDateToYYYYMMDD(now);
    
    const [yesterdayNight, todayNight] = await Promise.all([
      getMinuteData(symbol, yesterdayStr, 'after_hours'),
      getMinuteData(symbol, todayStr, 'after_hours')
    ]);
    
    // 昨天 15:00-23:59 的資料 + 今天 00:00-05:00 的資料
    const yesterdayAfter1500 = yesterdayNight.filter(bar => {
      const hour = parseInt(bar.time.split(':')[0], 10);
      return hour >= 15; // 15:00 之後
    });
    
    const todayBefore0500 = todayNight.filter(bar => {
      const hour = parseInt(bar.time.split(':')[0], 10);
      return hour < 5; // 05:00 之前
    });
    
    const crossDayData = [...yesterdayAfter1500, ...todayBefore0500];
    
    // 如果跨日查詢沒有資料，往回查詢最近有資料的日期
    if (crossDayData.length === 0) {
      console.log('🌙 夜盤跨日無資料，往回查詢...');
      const result = await findLatestAvailableData(symbol, 'after_hours');
      return result.data;
    }
    
    console.log(`🌙 夜盤跨日: 昨日 ${yesterdayAfter1500.length} 筆 + 今日 ${todayBefore0500.length} 筆`);
    return crossDayData;
  } else {
    // 正常時段，查詢今天的夜盤資料（若無則往回查詢）
    const result = await findLatestAvailableData(symbol, 'after_hours');
    return result.data;
  }
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
