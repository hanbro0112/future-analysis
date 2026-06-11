'use client';

/**
 * 台指期報價卡片元件
 * 顯示即時報價資訊
 */

import type { TaifexQuote } from '../types/futures';

interface QuoteCardProps {
  /** 報價資料 */
  quote: TaifexQuote;
}

/**
 * 格式化數字顯示
 */
function formatNumber(value: number): string {
  return value.toLocaleString('zh-TW');
}

export default function QuoteCard({ quote }: QuoteCardProps) {
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

      {/* 詳細資訊 */}
      <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">開盤</p>
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {formatNumber(quote.openPrice)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">成交量</p>
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {formatNumber(quote.volume)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">最高</p>
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {formatNumber(quote.highPrice)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">最低</p>
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {formatNumber(quote.lowPrice)}
          </p>
        </div>
      </div>

      {/* 更新時間 */}
      <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          更新時間：{quote.updateTime.toLocaleTimeString('zh-TW')}
        </p>
      </div>
    </div>
  );
}
