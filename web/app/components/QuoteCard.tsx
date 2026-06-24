'use client';

/**
 * 台指期報價卡片元件
 * 顯示即時報價資訊與多空分析
 */

import type { TaifexQuote } from '../types/futures';
import type { AnalysisResult } from '../types/minuteData';

interface QuoteCardProps {
  /** 報價資料 */
  quote: TaifexQuote;
  /** 分析結果 */
  analysis?: AnalysisResult | null;
}

/**
 * 格式化數字顯示
 */
function formatNumber(value: number): string {
  return value.toLocaleString('zh-TW');
}

/**
 * 格式化時間顯示
 */
function formatTime(date: Date): string {
  try {
    if (!date || isNaN(date.getTime())) {
      return '--:--:--';
    }
    return date.toLocaleTimeString('zh-TW', { 
      hour: '2-digit', 
      minute: '2-digit',
      second: '2-digit',
      hour12: false 
    });
  } catch (error) {
    console.error('時間格式化錯誤:', error);
    return '--:--:--';
  }
}

/**
 * 根據信號決定顏色
 */
function getSignalColor(signal: string): string {
  if (signal.includes('強多')) return 'bg-green-500 text-white';
  if (signal.includes('偏多')) return 'bg-green-100 text-green-700';
  if (signal.includes('強空')) return 'bg-red-500 text-white';
  if (signal.includes('偏空')) return 'bg-red-100 text-red-700';
  return 'bg-gray-100 text-gray-700';
}

export default function QuoteCard({ quote, analysis }: QuoteCardProps) {
  const isPositive = quote.change >= 0;
  const changeColor = isPositive ? 'text-red-500' : 'text-green-500';
  const bgColor = isPositive ? 'bg-red-50' : 'bg-green-50';

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      {/* 標題 */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {quote.name}
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {quote.symbol}
          </p>
        </div>
        <div className={`px-3 py-1 rounded-full ${bgColor}`}>
          <span className={`text-sm font-medium ${changeColor}`}>
            {isPositive ? '▲' : '▼'}
          </span>
        </div>
      </div>

      {/* 主要報價 */}
      <div className="mb-4">
        <div className="flex items-baseline gap-3">
          <span className={`text-4xl font-bold ${changeColor}`}>
            {formatNumber(quote.lastPrice)}
          </span>
          <div className="flex flex-col">
            <span className={`text-lg font-semibold ${changeColor}`}>
              {isPositive ? '+' : ''}{formatNumber(quote.change)}
            </span>
            <span className={`text-sm ${changeColor}`}>
              {isPositive ? '+' : ''}{quote.changePercent.toFixed(2)}%
            </span>
          </div>
        </div>
      </div>

      {/* 多空分析資訊 */}
      {analysis ? (
        <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
          {/* 多空信號 */}
          <div className="mb-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-gray-500 dark:text-gray-400">多空信號</span>
              <span className={`px-3 py-1 rounded-full text-xs font-semibold ${getSignalColor(analysis.signal)}`}>
                {analysis.signal}
              </span>
            </div>
          </div>

          {/* 多空比例條 */}
          <div className="mb-3">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">多空比例</p>
            <div className="flex gap-1 h-6 rounded overflow-hidden">
              <div 
                className="bg-green-500 flex items-center justify-center text-white text-xs font-semibold"
                style={{ width: `${analysis.long_ratio}%` }}
              >
                {analysis.long_ratio.toFixed(0)}%
              </div>
              <div 
                className="bg-red-500 flex items-center justify-center text-white text-xs font-semibold"
                style={{ width: `${analysis.short_ratio}%` }}
              >
                {analysis.short_ratio.toFixed(0)}%
              </div>
            </div>
          </div>

          {/* 其他指標 */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">市場情緒</p>
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {analysis.sentiment_label}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">信心水準</p>
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {analysis.confidence.toFixed(0)}%
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
          <p className="text-xs text-gray-400 text-center py-4">暫無分析資料</p>
        </div>
      )}

      {/* 更新時間 */}
      <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          更新時間：{formatTime(quote.updateTime)}
        </p>
      </div>
    </div>
  );
}
