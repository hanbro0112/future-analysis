'use client';

/**
 * 籌碼報告卡片組件
 * 顯示小台和微台散戶多空比圖表
 */

import { useState, useCallback, useMemo } from 'react';
import useSWR, { useSWRConfig } from 'swr';
import { storage } from '../lib/firebase';
import { ref, getDownloadURL } from 'firebase/storage';
import { getDateOffsetTradingDays, getLastTradingDay } from '../lib/tradingCalendar';

interface ChipReportCardProps {
  className?: string;
}

interface ChipReportImages {
  mtxUrl: string;
  tmfUrl: string;
}

/** 最多可往前切換的交易日數 */
const MAX_DAYS_BACK = 2;

/**
 * 獲取籌碼報告的日期
 * 15:20 前顯示前一交易日，15:21 後顯示當日
 */
export const getChipReportDate = (now: Date = new Date()): Date => {
  const hour = now.getHours();
  const minute = now.getMinutes();
  const timeInMinutes = hour * 60 + minute;
  
  // 15:21 前使用前一天的日期
  let dateForReport = now;
  if (timeInMinutes < 15 * 60 + 21) {  // 小於 15:21
    dateForReport = new Date(now);
    dateForReport.setDate(dateForReport.getDate() - 1);
  }
  
  // 排除週末與國定假日
  return getLastTradingDay(dateForReport);
};

// 交易日判斷（含國定假日）集中在 tradingCalendar，這裡轉出以維持既有匯入路徑
export { getDateOffsetTradingDays };

/**
 * 格式化日期為 YYYYMMDD
 */
export const formatDateToYYYYMMDD = (date: Date): string => {
  const year = date.getFullYear();
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const day = date.getDate().toString().padStart(2, '0');
  return `${year}${month}${day}`;
};

/**
 * 格式化日期為顯示用 (YYYY/MM/DD)
 */
const formatDateForDisplay = (date: Date): string => {
  const year = date.getFullYear();
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const day = date.getDate().toString().padStart(2, '0');
  return `${year}/${month}/${day}`;
};

/**
 * 格式化日期為顯示用 (MM/DD)，不含年份
 */
const formatDateAsMonthDay = (date: Date): string => {
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const day = date.getDate().toString().padStart(2, '0');
  return `${month}/${day}`;
};

/**
 * 依日期字串（YYYYMMDD）取得該日的籌碼報告圖片下載網址
 * 以 dateStr 作為 SWR 快取 key，切換回已抓過的日期時不會重打 API
 */
const fetchChipReportImages = async (dateStr: string): Promise<ChipReportImages> => {
  try {
    const mtxPath = `chip-reports/${dateStr}/${dateStr}_MTX_futures_ratio.png`;
    const tmfPath = `chip-reports/${dateStr}/${dateStr}_TMF_futures_ratio.png`;

    const mtxRef = ref(storage, mtxPath);
    const tmfRef = ref(storage, tmfPath);

    const [mtxUrl, tmfUrl] = await Promise.all([
      getDownloadURL(mtxRef),
      getDownloadURL(tmfRef)
    ]);

    return { mtxUrl, tmfUrl };
  } catch (err) {
    console.error('❌ 載入籌碼報告失敗:', err);
    throw err;
  }
};

export default function ChipReportCard({ className = '' }: ChipReportCardProps) {
  // 最新可顯示的交易日（切換日期時以此為基準往前推算）
  const [baseDate, setBaseDate] = useState<Date>(() => getChipReportDate());
  // 往前切換的交易日數，範圍為 0（最新交易日）～ MAX_DAYS_BACK
  const [daysBack, setDaysBack] = useState(0);

  const reportDate = useMemo(
    () => getDateOffsetTradingDays(baseDate, daysBack),
    [baseDate, daysBack]
  );
  const dateStr = formatDateToYYYYMMDD(reportDate);

  // SWR 依 dateStr 快取每個交易日的圖片網址，切換過的日期不會重新發送請求
  const { data, error, isLoading, isValidating } = useSWR(
    dateStr,
    fetchChipReportImages,
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      revalidateIfStale: false,
    }
  );
  const { mutate: mutateGlobal } = useSWRConfig();

  // 手動更新：不管目前停在哪一天，一律強制重新抓取「今天」最新的圖片
  const handleManualRefresh = useCallback(() => {
    const latestDate = getChipReportDate();
    const latestDateStr = formatDateToYYYYMMDD(latestDate);
    setBaseDate(latestDate);
    setDaysBack(0);
    mutateGlobal(latestDateStr, fetchChipReportImages(latestDateStr));
  }, [mutateGlobal]);

  // 切換到前一個交易日（最多往前 MAX_DAYS_BACK 天）
  const handlePrevDay = useCallback(() => {
    setDaysBack((prev) => Math.min(prev + 1, MAX_DAYS_BACK));
  }, []);

  // 切換到下一個交易日（最多回到最新交易日）
  const handleNextDay = useCallback(() => {
    setDaysBack((prev) => Math.max(prev - 1, 0));
  }, []);

  const isPrevDisabled = isValidating || daysBack >= MAX_DAYS_BACK;
  const isNextDisabled = isValidating || daysBack <= 0;

  // 左右切換鍵提示文字顯示切換後會看到的日期（僅月日）
  const prevDateLabel = useMemo(
    () => formatDateAsMonthDay(getDateOffsetTradingDays(baseDate, Math.min(daysBack + 1, MAX_DAYS_BACK))),
    [baseDate, daysBack]
  );
  const nextDateLabel = useMemo(
    () => formatDateAsMonthDay(getDateOffsetTradingDays(baseDate, Math.max(daysBack - 1, 0))),
    [baseDate, daysBack]
  );

  // 記錄目前已經完成載入（含解碼）的圖片網址，切換 src 時用淡入轉場蓋掉解碼耗時，
  // 不論解碼實際花多久都不會讓畫面卡一下
  const [mtxLoadedUrl, setMtxLoadedUrl] = useState<string | null>(null);
  const [tmfLoadedUrl, setTmfLoadedUrl] = useState<string | null>(null);

  return (
    <div className={`bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 ${className}`}>
      <div className="mb-4">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-bold text-gray-800 dark:text-gray-100">
            📊 散戶多空比
          </h2>
          <span className="text-base font-medium text-gray-700 dark:text-gray-300 min-w-[6.5rem] text-center">
            ({formatDateForDisplay(reportDate)})
          </span>
          <button
            type="button"
            onClick={handleManualRefresh}
            disabled={isValidating}
            title="手動更新"
            aria-label="手動更新籌碼報告"
            className="p-1 rounded-full text-gray-400 hover:text-blue-500 dark:hover:text-blue-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg
              className={`w-4 h-4 ${isValidating ? 'animate-spin' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          資料來源：永豐期貨籌碼快訊（每交易日 15:21 更新）
        </p>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handlePrevDay}
          disabled={isPrevDisabled}
          title={prevDateLabel}
          aria-label="切換至前一交易日"
          className="shrink-0 p-1 rounded-full text-gray-400 hover:text-blue-500 dark:hover:text-blue-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:text-gray-400 disabled:hover:bg-transparent"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        <div className="flex-1 min-w-0">
          {isLoading ? (
            <div className="flex items-center justify-center h-64 text-gray-500 dark:text-gray-400">
              <div className="text-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 dark:border-blue-400 mx-auto mb-4"></div>
                <p>載入中...</p>
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-64 text-red-500 dark:text-red-400">
              <div className="text-center">
                <p className="text-lg">⚠️ 載入籌碼報告失敗</p>
                <p className="text-sm mt-2 text-gray-500 dark:text-gray-400">請稍後再試</p>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* 微台散戶多空比 (左邊) */}
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                <div className="bg-gradient-to-r from-purple-500 to-purple-600 px-4 py-2">
                  <h3 className="text-white font-semibold">微台散戶多空比 (TMF)</h3>
                </div>
                <div className="p-2 bg-gray-50 dark:bg-gray-900">
                  {data?.tmfUrl ? (
                    <img
                      src={data.tmfUrl}
                      alt="微台散戶多空比"
                      className={`w-full h-auto transition-opacity duration-200 ${tmfLoadedUrl === data.tmfUrl ? 'opacity-100' : 'opacity-0'}`}
                      decoding="async"
                      onLoad={() => setTmfLoadedUrl(data.tmfUrl)}
                    />
                  ) : (
                    <div className="flex items-center justify-center h-48 text-gray-400">
                      無圖片資料
                    </div>
                  )}
                </div>
              </div>

              {/* 小台散戶多空比 (右邊) */}
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                <div className="bg-gradient-to-r from-blue-500 to-blue-600 px-4 py-2">
                  <h3 className="text-white font-semibold">小台散戶多空比 (MTX)</h3>
                </div>
                <div className="p-2 bg-gray-50 dark:bg-gray-900">
                  {data?.mtxUrl ? (
                    <img
                      src={data.mtxUrl}
                      alt="小台散戶多空比"
                      className={`w-full h-auto transition-opacity duration-200 ${mtxLoadedUrl === data.mtxUrl ? 'opacity-100' : 'opacity-0'}`}
                      decoding="async"
                      onLoad={() => setMtxLoadedUrl(data.mtxUrl)}
                    />
                  ) : (
                    <div className="flex items-center justify-center h-48 text-gray-400">
                      無圖片資料
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={handleNextDay}
          disabled={isNextDisabled}
          title={nextDateLabel}
          aria-label="切換至下一交易日"
          className="shrink-0 p-1 rounded-full text-gray-400 hover:text-blue-500 dark:hover:text-blue-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:text-gray-400 disabled:hover:bg-transparent"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>
    </div>
  );
}
