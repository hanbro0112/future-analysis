'use client';

/**
 * 籌碼報告卡片組件
 * 顯示小台和微台散戶多空比圖表
 */

import { useState, useEffect } from 'react';
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

  useEffect(() => {
    async function loadChipReportImages() {
      try {
        setIsLoading(true);
        setError(null);
        
        // 獲取報告日期
        const date = getChipReportDate();
        setReportDate(date);
        const dateStr = formatDateToYYYYMMDD(date);
        
        console.log('📊 載入籌碼報告:', dateStr);
        
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
        
        console.log('✅ 籌碼報告圖片載入成功');
      } catch (err) {
        console.error('❌ 載入籌碼報告失敗:', err);
        setError('載入籌碼報告失敗');
        setMtxImageUrl(null);
        setTmfImageUrl(null);
      } finally {
        setIsLoading(false);
      }
    }
    
    loadChipReportImages();
    
    // 每分鐘檢查一次，在 15:22 時自動更新
    const interval = setInterval(() => {
      const now = new Date();
      const hour = now.getHours();
      const minute = now.getMinutes();
      
      // 在 15:22 時重新載入
      if (hour === 15 && minute === 22) {
        console.log('🔄 15:22 自動更新籌碼報告');
        loadChipReportImages();
      }
    }, 60000); // 每分鐘檢查一次
    
    return () => clearInterval(interval);
  }, []);

  return (
    <div className={`bg-white rounded-lg shadow-md p-6 ${className}`}>
      <div className="mb-4">
        <h2 className="text-xl font-bold text-gray-800">
          📊 散戶多空比 ({formatDateForDisplay(reportDate)})
        </h2>
        <p className="text-sm text-gray-500 mt-1">
          資料來源：永豐期貨籌碼快訊（每交易日 15:21 更新）
        </p>
      </div>
      
      {isLoading ? (
        <div className="flex items-center justify-center h-64 text-gray-500">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
            <p>載入中...</p>
          </div>
        </div>
      ) : error ? (
        <div className="flex items-center justify-center h-64 text-red-500">
          <div className="text-center">
            <p className="text-lg">⚠️ {error}</p>
            <p className="text-sm mt-2 text-gray-500">請稍後再試</p>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* 微台散戶多空比 (左邊) */}
          <div className="border rounded-lg overflow-hidden">
            <div className="bg-gradient-to-r from-purple-500 to-purple-600 px-4 py-2">
              <h3 className="text-white font-semibold">微台散戶多空比 (TMF)</h3>
            </div>
            <div className="p-2 bg-gray-50">
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
          <div className="border rounded-lg overflow-hidden">
            <div className="bg-gradient-to-r from-blue-500 to-blue-600 px-4 py-2">
              <h3 className="text-white font-semibold">小台散戶多空比 (MTX)</h3>
            </div>
            <div className="p-2 bg-gray-50">
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
