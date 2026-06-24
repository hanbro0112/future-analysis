'use client'

import type { AnalysisResult } from '../types/minuteData'

interface AnalysisTableProps {
  analysis: AnalysisResult | null
  time?: string
}

/**
 * 根據信號決定背景顏色
 */
function getSignalColor(signal: string): string {
  if (signal.includes('強多')) return 'bg-green-100 text-green-800'
  if (signal.includes('偏多')) return 'bg-green-50 text-green-700'
  if (signal.includes('強空')) return 'bg-red-100 text-red-800'
  if (signal.includes('偏空')) return 'bg-red-50 text-red-700'
  return 'bg-gray-100 text-gray-700'
}

/**
 * 根據情緒決定顏色
 */
function getSentimentColor(label: string): string {
  if (label.includes('貪婪')) return 'text-green-600'
  if (label.includes('恐慌')) return 'text-red-600'
  return 'text-gray-600'
}

/**
 * 分析結果表格組件
 */
export default function AnalysisTable({ analysis, time }: AnalysisTableProps) {
  if (!analysis) {
    return (
      <div className="bg-white rounded-lg shadow-sm p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">多空分析</h3>
        <div className="text-center text-gray-400 py-8">
          暫無分析資料
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow-sm p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">多空分析</h3>
        {time && (
          <span className="text-sm text-gray-500">
            更新時間: {time}
          </span>
        )}
      </div>

      {/* 主要信號 */}
      <div className="mb-6">
        <div className="flex items-center justify-center gap-4">
          <span className={`px-6 py-3 rounded-lg font-bold text-2xl ${getSignalColor(analysis.signal)}`}>
            {analysis.signal}
          </span>
          <div className="text-center">
            <div className="text-xs text-gray-500 mb-1">信心水準</div>
            <div className="text-xl font-semibold text-gray-900">
              {analysis.confidence.toFixed(0)}%
            </div>
          </div>
        </div>
      </div>

      {/* 多空比例 */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-sm text-gray-600">多空比例</span>
        </div>
        <div className="flex gap-2 h-8">
          <div 
            className="bg-green-500 rounded-l flex items-center justify-center text-white text-sm font-semibold"
            style={{ width: `${analysis.long_ratio}%` }}
          >
            {analysis.long_ratio.toFixed(1)}%
          </div>
          <div 
            className="bg-red-500 rounded-r flex items-center justify-center text-white text-sm font-semibold"
            style={{ width: `${analysis.short_ratio}%` }}
          >
            {analysis.short_ratio.toFixed(1)}%
          </div>
        </div>
      </div>

      {/* 詳細指標 */}
      <div className="grid grid-cols-2 gap-4">
        {/* 市場情緒 */}
        <div className="border border-gray-200 rounded-lg p-4">
          <div className="text-xs text-gray-500 mb-1">市場情緒</div>
          <div className={`text-lg font-semibold ${getSentimentColor(analysis.sentiment_label)}`}>
            {analysis.sentiment_label}
          </div>
          <div className="text-sm text-gray-600 mt-1">
            分數: {analysis.sentiment_score.toFixed(1)}
          </div>
        </div>

        {/* 成交量狀態 */}
        <div className="border border-gray-200 rounded-lg p-4">
          <div className="text-xs text-gray-500 mb-1">成交量狀態</div>
          <div className="text-lg font-semibold text-purple-600">
            {analysis.volume_explosion_level}
          </div>
        </div>

        {/* 期現價差 */}
        <div className="border border-gray-200 rounded-lg p-4">
          <div className="text-xs text-gray-500 mb-1">期現價差</div>
          <div className={`text-lg font-semibold ${analysis.basis > 0 ? 'text-green-600' : 'text-red-600'}`}>
            {analysis.basis > 0 ? '+' : ''}{analysis.basis.toFixed(0)}
          </div>
          <div className="text-sm text-gray-600 mt-1">
            {analysis.basis_pct > 0 ? '+' : ''}{analysis.basis_pct.toFixed(2)}%
          </div>
        </div>

        {/* 價差信號 */}
        <div className="border border-gray-200 rounded-lg p-4">
          <div className="text-xs text-gray-500 mb-1">價差信號</div>
          <div className={`text-lg font-semibold ${analysis.basis > 0 ? 'text-green-600' : 'text-red-600'}`}>
            {analysis.basis > 0 ? '正價差' : '逆價差'}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {analysis.basis > 0 ? '偏多' : '偏空'}
          </div>
        </div>
      </div>
    </div>
  )
}
