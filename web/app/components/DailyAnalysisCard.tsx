'use client';

/**
 * 每日市場分析卡片元件
 * 顯示 Gemini AI 生成的每日分析報告（Markdown 格式）
 */

import { memo, useMemo, useState, useEffect } from 'react';
import { marked } from 'marked';
import type { DailyReport } from '../lib/firestoreApi';

interface DailyAnalysisCardProps {
  /** 每日分析報告 */
  report: DailyReport | null;
  /** 是否正在載入 */
  isLoading?: boolean;
  /** 手動更新回調 */
  onRefresh?: () => void;
}

/**
 * 格式化日期顯示
 * @param dateStr YYYYMMDD 格式
 * @returns 2026/07/07 格式
 */
function formatDateDisplay(dateStr: string): string {
  if (!dateStr || dateStr.length !== 8) return dateStr;
  const year = dateStr.substring(0, 4);
  const month = dateStr.substring(4, 6);
  const day = dateStr.substring(6, 8);
  return `${year}/${month}/${day}`;
}

function DailyAnalysisCard({ report, isLoading = false, onRefresh }: DailyAnalysisCardProps) {
  // 展開/收回狀態
  const [isExpanded, setIsExpanded] = useState(false);
  
  // 當報告變化時，重置為收回狀態
  useEffect(() => {
    setIsExpanded(false);
  }, [report?.date]);
  
  // 將 Markdown 轉換為 HTML
  const htmlContent = useMemo(() => {
    if (!report?.raw_content) return '';
    return marked(report.raw_content, { 
      breaks: true,
      gfm: true 
    });
  }, [report?.raw_content]);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <svg className="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">AI 每日市場分析</h2>
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={isLoading}
              title="手動更新"
              aria-label="手動更新每日分析"
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
          )}
        </div>
        {report && (
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {formatDateDisplay(report.date)}
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <div className="animate-pulse flex flex-col items-center">
            <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
            <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">載入中...</p>
          </div>
        </div>
      ) : report ? (
        <div className="prose prose-sm max-w-none">
          <div className="relative">
            <div 
              className={`markdown-content text-gray-700 dark:text-gray-100 leading-relaxed transition-all duration-300 overflow-hidden ${
                isExpanded ? 'max-h-none' : 'max-h-[200px]'
              }`}
              dangerouslySetInnerHTML={{ __html: htmlContent }}
            />
            {!isExpanded && (
              <div className="absolute bottom-0 left-0 right-0 h-20 bg-gradient-to-t from-white dark:from-gray-800 to-transparent pointer-events-none"></div>
            )}
          </div>
          
          {/* 展開/收回按鈕 */}
          <div className="flex justify-center mt-3">
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="flex items-center gap-1 px-4 py-2 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 hover:bg-blue-50 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              <span>{isExpanded ? '收回' : '展開全文'}</span>
              <svg 
                className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                fill="none" 
                stroke="currentColor" 
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
          </div>
          
          {report.created_at && (
            <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-700">
              <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                <span>
                  生成時間：{new Date(report.created_at).toLocaleString('zh-TW', {
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit'
                  })}
                </span>
                {report.model_used && (
                  <span className="font-mono">
                    {report.model_used}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-8 text-gray-400 dark:text-gray-500">
          <svg className="w-12 h-12 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <p className="text-sm">尚無分析報告</p>
          <p className="text-xs mt-1 text-gray-400 dark:text-gray-500">每日 08:00 後更新</p>
        </div>
      )}

      <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-700">
        <div className="flex items-start gap-2 text-xs text-gray-500 dark:text-gray-400">
          <svg className="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <p>• 每個交易日 08:00 自動生成當天日盤分析</p>
            <p>• 08:00 前顯示前一交易日分析，08:01 後切換為當天分析</p>
            <p>• 分析由 Gemini AI 基於歷史數據生成</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default memo(DailyAnalysisCard);
