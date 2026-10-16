/**
 * Firestore 資料存取層
 * 讀取分鐘級期貨資料與每日分析
 */
import { collection, query, where, orderBy, limit, getDocs, doc, getDoc, setDoc, onSnapshot, Unsubscribe } from 'firebase/firestore';
import type { DocumentData } from 'firebase/firestore';
import { db } from './firebase';
import { getLastTradingDay } from './tradingCalendar';
import type { MinuteBar } from '../types/minuteData';
import type { PttPush, PttSession } from '../types/pttChat';

// 交易日判斷（含國定假日）集中在 tradingCalendar，這裡轉出以維持既有匯入路徑
export { getLastTradingDay };

type MarketType = 'regular' | 'after_hours';

/** 日盤最後一根 K 棒的文件 ID，結算日提早於 13:30 收盤時改取 1329 */
const DAY_SESSION_CLOSE_DOC_IDS = ['1344', '1329'] as const;

/**
 * 將 Firestore 文件轉成 MinuteBar
 */
function toMinuteBar(docData: DocumentData, docId: string, symbol: string, date: string): MinuteBar {
  return {
    code: docData.code || symbol,
    timestamp: docData.timestamp,
    date: docData.date || date,
    time: docData.time || docId,
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
  };
}

/**
 * 夜盤排序：15:00-23:59 在前，00:00-05:59（寫在同一天集合 time 最小處）排在後
 */
function compareNightTime(a: MinuteBar, b: MinuteBar): number {
  const timeA = parseInt(a.time);
  const timeB = parseInt(b.time);
  const isEarlyA = timeA < 600;  // 00:00-05:59
  const isEarlyB = timeB < 600;

  if (isEarlyA && !isEarlyB) return 1;   // A 是凌晨，B 不是 -> A 排後面
  if (!isEarlyA && isEarlyB) return -1;  // A 不是凌晨，B 是 -> A 排前面
  return timeA - timeB;  // 同區段，按時間升序
}

/**
 * 依盤別排序：日盤依 time 升序、夜盤依跨日規則；混合資料則日盤在前、夜盤在後
 */
export function sortMinuteBars(data: MinuteBar[]): MinuteBar[] {
  const dayBars = data
    .filter((bar) => bar.market_type === 'regular')
    .sort((a, b) => parseInt(a.time) - parseInt(b.time));
  const nightBars = data
    .filter((bar) => bar.market_type === 'after_hours')
    .sort(compareNightTime);
  return [...dayBars, ...nightBars];
}

/**
 * 將 Firestore Timestamp / Date / ISO 字串轉成 Date，無法辨識時回傳 null
 */
export function timestampToDate(value: unknown): Date | null {
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }
  if (typeof value === 'string') {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }
  if (value && typeof (value as { toDate?: unknown }).toDate === 'function') {
    return (value as { toDate: () => Date }).toDate();
  }
  return null;
}

/**
 * 取得一批 K 棒中最新的 timestamp，作為增量查詢的游標
 * （timestamp 為 K 棒真實時間，夜盤跨午夜後仍單調遞增，不受 time 欄位回捲影響）
 */
export function getLatestBarTimestamp(bars: MinuteBar[]): Date | null {
  let latest: Date | null = null;
  for (const bar of bars) {
    const current = timestampToDate(bar.timestamp);
    if (current && (!latest || current.getTime() > latest.getTime())) {
      latest = current;
    }
  }
  return latest;
}

/**
 * 將增量資料合併進既有資料（同盤別 + time 相同者以新資料覆蓋），並重新排序
 */
export function mergeMinuteBars(existing: MinuteBar[], incoming: MinuteBar[]): MinuteBar[] {
  const merged = new Map<string, MinuteBar>();
  for (const bar of existing) {
    merged.set(`${bar.market_type}|${bar.time}`, bar);
  }
  for (const bar of incoming) {
    merged.set(`${bar.market_type}|${bar.time}`, bar);
  }
  return sortMinuteBars([...merged.values()]);
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
  marketType?: MarketType
): Promise<MinuteBar[]> {
  try {
    const collectionPath = `market/${symbol}/${date}`;

    // 指定盤別時用 where 等值條件只讀該盤別的文件（不搭配 orderBy，避免每天都要建立 composite index），
    // 排序改在讀取後於前端處理；未指定盤別則維持整集合依 time 排序
    const q = marketType
      ? query(collection(db, collectionPath), where('market_type', '==', marketType))
      : query(collection(db, collectionPath), orderBy('time', 'asc'));

    const querySnapshot = await getDocs(q);
    const data: MinuteBar[] = [];

    querySnapshot.forEach((docSnap) => {
      data.push(toMinuteBar(docSnap.data(), docSnap.id, symbol, date));
    });

    return marketType ? sortMinuteBars(data) : data;
  } catch (error) {
    console.error('❌ 讀取分鐘資料失敗:', error);
    if (error instanceof Error) {
      console.error('錯誤詳情:', error.message);
    }
    return [];
  }
}

/**
 * 增量讀取：只取 timestamp 大於等於游標的新資料
 *
 * 使用 timestamp（K 棒真實時間）而非 time 當游標：夜盤過 00:00 的資料寫在前一天集合、
 * time 會排到集合最前面，但 timestamp 仍依真實時序遞增，所以不會取回整個集合。
 * 取「大於等於」是為了多讀游標那一筆（約 1 筆），避免最後一根 K 棒事後被更新或延遲寫入而漏掉。
 * 盤別在前端過濾（where 搭配 timestamp 範圍需要 composite index），增量資料量很小。
 *
 * @param symbol 商品代碼
 * @param date 日期 (格式: YYYYMMDD)，即集合 ID
 * @param after 游標時間（通常為已載入資料中最新一筆的 timestamp）
 * @param marketType 盤別過濾
 * @returns 新增（或被更新）的分鐘資料，讀取失敗回傳空陣列
 */
export async function getMinuteDataAfter(
  symbol: string,
  date: string,
  after: Date,
  marketType?: MarketType
): Promise<MinuteBar[]> {
  try {
    const q = query(
      collection(db, `market/${symbol}/${date}`),
      where('timestamp', '>=', after),
      orderBy('timestamp', 'asc')
    );

    const querySnapshot = await getDocs(q);
    const data: MinuteBar[] = [];

    querySnapshot.forEach((docSnap) => {
      data.push(toMinuteBar(docSnap.data(), docSnap.id, symbol, date));
    });

    return marketType ? data.filter((bar) => bar.market_type === marketType) : data;
  } catch (error) {
    console.error('❌ 增量讀取分鐘資料失敗:', error);
    return [];
  }
}

/**
 * 取得日盤的查詢日期 (YYYYMMDD)：08:30 前使用前一天，並排除週末與國定假日
 */
export function getDaySessionDate(now: Date = new Date()): string {
  const timeInMinutes = now.getHours() * 60 + now.getMinutes();

  let dateForQuery = now;
  if (timeInMinutes < 8 * 60 + 30) {
    dateForQuery = new Date(now);
    dateForQuery.setDate(dateForQuery.getDate() - 1);
  }

  return formatDateToYYYYMMDD(getLastTradingDay(dateForQuery));
}

/**
 * 取得夜盤的查詢日期 (YYYYMMDD)：
 * - 00:00-14:49 使用前一天的夜盤資料
 * - 14:50-23:59 使用當天的夜盤資料
 * 並排除週末與國定假日
 */
export function getNightSessionDate(now: Date = new Date()): string {
  const timeInMinutes = now.getHours() * 60 + now.getMinutes();

  let dateForQuery = now;
  if (timeInMinutes < 14 * 60 + 50) {
    dateForQuery = new Date(now);
    dateForQuery.setDate(dateForQuery.getDate() - 1);
  }

  return formatDateToYYYYMMDD(getLastTradingDay(dateForQuery));
}

/**
 * 取得今日日盤資料
 * 邏輯：08:30 前查詢前一個交易日的日盤
 * @param symbol 商品代碼 (例如: MXF)
 * @returns 日盤分鐘資料陣列
 */
export async function getTodayDaySession(symbol: string): Promise<MinuteBar[]> {
  return getMinuteData(symbol, getDaySessionDate(), 'regular');
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
  return getMinuteData(symbol, getNightSessionDate(), 'after_hours');
}

/**
 * 取得今日資料（日盤 + 夜盤）
 * 日盤與夜盤落在同一天集合時（14:50 之後）只讀一次再切分，避免同一集合重複讀取
 * @param symbol 商品代碼 (例如: MXF)
 * @returns 分鐘資料陣列（日盤在前，夜盤在後）
 */
export async function getTodayMinuteData(symbol: string): Promise<MinuteBar[]> {
  const now = new Date();
  const dayDate = getDaySessionDate(now);
  const nightDate = getNightSessionDate(now);

  if (dayDate === nightDate) {
    const allData = await getMinuteData(symbol, dayDate);
    const sorted = sortMinuteBars(allData);
    console.log(`📈 日盤: ${sorted.filter((bar) => bar.market_type === 'regular').length} 筆, 夜盤: ${sorted.filter((bar) => bar.market_type === 'after_hours').length} 筆`);
    return sorted;
  }

  const [dayData, nightData] = await Promise.all([
    getMinuteData(symbol, dayDate, 'regular'),
    getMinuteData(symbol, nightDate, 'after_hours')
  ]);

  console.log(`📈 日盤: ${dayData.length} 筆, 夜盤: ${nightData.length} 筆`);

  // 日盤在前，夜盤在後
  return [...dayData, ...nightData];
}

/**
 * 取得指定日期日盤的收盤價（用於漲跌幅參考價）
 * 直接讀日盤最後一根 K 棒（1344）；結算日 13:30 收盤則改讀 1329。每次最多讀 2 筆文件。
 * @param symbol 商品代碼 (例如: MXF)
 * @param date 日期 (格式: YYYYMMDD)
 * @returns 收盤價，兩根都讀不到（或讀取失敗）則回傳 null
 */
export async function getDaySessionClosePrice(symbol: string, date: string): Promise<number | null> {
  for (const docId of DAY_SESSION_CLOSE_DOC_IDS) {
    try {
      const docSnap = await getDoc(doc(db, `market/${symbol}/${date}/${docId}`));
      if (docSnap.exists()) {
        const close = docSnap.data()?.close;
        if (typeof close === 'number' && close > 0) {
          return close;
        }
      }
    } catch (error) {
      console.error(`❌ 讀取日盤收盤價失敗 (${date}/${docId}):`, error);
    }
  }
  return null;
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
  
  // 確保日期是交易日（排除週末與國定假日）
  dateForQuery = getLastTradingDay(dateForQuery);
  
  const dateStr = formatDateToYYYYMMDD(dateForQuery);
  console.log(`📅 查詢每日分析日期: ${dateStr} (當前時間: ${hour}:${String(minute).padStart(2, '0')})`);

  return getDailyReport(dateStr);
}

/**
 * 監聽指定日期與盤別的 PTT Stock 板閒聊訊息
 * @param session 'intraday' (盤中閒聊) | 'afterhours' (盤後閒聊)
 * @param date 日期 (格式: YYYYMMDD)
 * @param callback 訊息更新回調函數
 * @returns 取消監聽函數
 */
export function subscribeToPttPosts(
  session: PttSession,
  date: string,
  callback: (posts: PttPush[]) => void
): Unsubscribe {
  const docId = `${date}_${session}`;
  const docRef = doc(db, 'pttPosts', docId);

  return onSnapshot(docRef, (docSnap) => {
    const data = docSnap.data();
    const posts = (data?.posts as PttPush[] | undefined) || [];
    const updatedAt = data?.updated_at?.toDate?.() ?? data?.updated_at ?? null;

    // TODO(debug): 排查前端收不到 PTT 訊息問題，之後移除
    console.log(
      `[PTT DEBUG] pttPosts/${docId} exists=${docSnap.exists()} posts=${posts.length} updated_at=${updatedAt}`
    );

    callback(posts);
  }, (error) => {
    console.error(`❌ 監聽 PTT 閒聊訊息失敗 (pttPosts/${docId}):`, error);
  });
}

/**
 * PTT 閒聊個人設定文件路徑：users/{uid}/setting/pttReadState
 * 盤中/盤後的已讀位置與視窗大小都合併存在同一份文件裡，
 * 已讀位置用 intraday/afterhours 各自的巢狀欄位分開、寫入時傳巢狀物件搭配 setDoc merge，
 * 不會互相覆蓋、也不會動到 width/height
 * （注意：setDoc 的 key 不會像 updateDoc 一樣解析 dot-notation 字串路徑，
 * 必須傳實際的巢狀物件，否則會寫成一個帶點的字面欄位名稱）
 */
function getPttSettingDocRef(uid: string) {
  return doc(db, 'users', uid, 'setting', 'pttReadState');
}

/**
 * 取得使用者在指定日期與盤別的已讀位置（posts 陣列的索引）
 *
 * intraday/afterhours 共用同一份文件，各自的巢狀欄位內用 date 記錄該已讀位置屬於哪一天；
 * 若存的 date 跟查詢的 date 不同，代表是前一天殘留的舊資料，對今天全新的訊息列表沒有意義，
 * 視為未讀（回傳 -1）
 *
 * @param uid 使用者 ID
 * @param session 'intraday' | 'afterhours'
 * @param date 日期 (格式: YYYYMMDD)
 * @returns 已讀到的索引，無記錄或記錄屬於別天則回傳 -1
 */
export async function getPttReadState(uid: string, session: PttSession, date: string): Promise<number> {
  try {
    const docSnap = await getDoc(getPttSettingDocRef(uid));
    if (!docSnap.exists()) {
      return -1;
    }
    const sessionData = docSnap.data()[session];
    if (!sessionData || sessionData.date !== date) {
      return -1;
    }
    const lastReadIndex = sessionData.last_read_index;
    return typeof lastReadIndex === 'number' ? lastReadIndex : -1;
  } catch (error) {
    console.error('❌ 讀取 PTT 已讀位置失敗:', error);
    return -1;
  }
}

/**
 * 儲存使用者在指定日期與盤別的已讀位置（隔天會覆蓋掉前一天的值，不影響另一個 session 或視窗大小）
 * @param uid 使用者 ID
 * @param session 'intraday' | 'afterhours'
 * @param date 日期 (格式: YYYYMMDD)
 * @param lastReadIndex 已讀到的索引
 */
export async function savePttReadState(
  uid: string,
  session: PttSession,
  date: string,
  lastReadIndex: number
): Promise<void> {
  try {
    await setDoc(
      getPttSettingDocRef(uid),
      { [session]: { date, last_read_index: lastReadIndex } },
      { merge: true }
    );
  } catch (error) {
    console.error('❌ 儲存 PTT 已讀位置失敗:', error);
  }
}

/**
 * 取得使用者上次調整過的 PTT 閒聊視窗大小
 * @param uid 使用者 ID
 * @returns 寬高（px），無記錄則回傳 null
 */
export async function getPttWindowSize(uid: string): Promise<{ width: number; height: number } | null> {
  try {
    const docSnap = await getDoc(getPttSettingDocRef(uid));
    if (!docSnap.exists()) {
      return null;
    }
    const data = docSnap.data();
    if (typeof data.width === 'number' && typeof data.height === 'number') {
      return { width: data.width, height: data.height };
    }
    return null;
  } catch (error) {
    console.error('❌ 讀取 PTT 視窗大小失敗:', error);
    return null;
  }
}

/**
 * 儲存使用者調整過的 PTT 閒聊視窗大小（不影響已讀位置）
 * @param uid 使用者 ID
 * @param width 寬度 (px)
 * @param height 高度 (px)
 */
export async function savePttWindowSize(uid: string, width: number, height: number): Promise<void> {
  try {
    await setDoc(getPttSettingDocRef(uid), { width, height }, { merge: true });
  } catch (error) {
    console.error('❌ 儲存 PTT 視窗大小失敗:', error);
  }
}
