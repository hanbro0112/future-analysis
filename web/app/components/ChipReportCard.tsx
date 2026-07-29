'use client';

/**
 * 籌碼報告卡片組件
 * 顯示小台和微台散戶多空比圖表
 */

import { useState, useEffect, useCallback } from 'react';
import { storage } from '../lib/firebase';
import { ref, getDownloadURL } from 'firebase/storage';

interface ChipReportCardProps {
  className?: string;
}

/**
 * 獲取籌碼報告的日期
 * 15:20 前顯示前一交易日，15:21 後顯示當日
 */
const getChipReportDate = (): Date => {
  const now = new Date();
  const hour = now.getHours();
  const minute = now.getMinutes();
  const timeInMinutes = hour * 60 + minute;
  
  // 15:21 前使用前一天的日期
  let dateForReport = now;
  if (timeInMinutes < 15 * 60 + 21) {  // 小於 15:21
    dateForReport = new Date(now);
    dateForReport.setDate(dateForReport.getDate() - 1);
  }
  
  // 排除週末
  return getLastTradingDay(dateForReport);
};

/**
 * 獲取最近的交易日（排除週末）
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
 * 格式化日期為 YYYYMMDD
 */
const formatDateToYYYYMMDD = (date: Date): string => {
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

export default function ChipReportCard({ className = '' }: ChipReportCardProps) {
  const [mtxImageUrl, setMtxImageUrl] = useState<string | null>(null);
  const [tmfImageUrl, setTmfImageUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [reportDate, setReportDate] = useState<Date>(new Date());
  const [error, setError] = useState<string | null>(null);

  // 載入籌碼報告圖片（僅首次載入，之後由使用者點擊更新圖示手動觸發）
  const loadChipReportImages = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      // 獲取報告日期
      const date = getChipReportDate();
      setReportDate(date);
      const dateStr = formatDateToYYYYMMDD(date);

      // 構建 Storage 路徑
      const mtxPath = `chip-reports/${dateStr}/${dateStr}_MTX_futures_ratio.png`;
      const tmfPath = `chip-reports/${dateStr}/${dateStr}_TMF_futures_ratio.png`;

      // 獲取下載 URL
      const mtxRef = ref(storage, mtxPath);
      const tmfRef = ref(storage, tmfPath);

      const [mtxUrl, tmfUrl] = await Promise.all([
        getDownloadURL(mtxRef),
        getDownloadURL(tmfRef)
      ]);

      setMtxImageUrl(mtxUrl);
      setTmfImageUrl(tmfUrl);
    } catch (err) {
      console.error('❌ 載入籌碼報告失敗:', err);
      setError('載入籌碼報告失敗');
      setMtxImageUrl(null);
      setTmfImageUrl(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadChipReportImages();
  }, [loadChipReportImages]);

  return (
    <div className={`bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 ${className}`}>
      <div className="mb-4">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-bold text-gray-800 dark:text-gray-100">
            📊 散戶多空比 ({formatDateForDisplay(reportDate)})
          </h2>
          <button
            type="button"
            onClick={loadChipReportImages}
            disabled={isLoading}
            title="手動更新"
            aria-label="手動更新籌碼報告"
            className="p-1 rounded-full text-gray-400 hover:text-blue-500 dark:hover:text-blue-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg
              className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`}
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
            <p className="text-lg">⚠️ {error}</p>
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
              {tmfImageUrl ? (
                <img 
                  src={tmfImageUrl} 
                  alt="微台散戶多空比" 
                  className="w-full h-auto"
                  loading="lazy"
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
              {mtxImageUrl ? (
                <img 
                  src={mtxImageUrl} 
                  alt="小台散戶多空比" 
                  className="w-full h-auto"
                  loading="lazy"
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
  );
}
