'use client';

/**
 * 台指期報價卡片元件
 * 顯示即時報價資訊
 */

import { useMemo, memo, useState, useEffect } from 'react';
import type { TaifexQuote } from '../types/futures';
import type { RealtimePrice } from '../lib/useWebSocket';
import type { AnalysisResult } from '../types/minuteData';

interface QuoteCardProps {
  /** 報價資料 */
  quote: TaifexQuote | null;
  /** 即時報價（WebSocket，優先使用） */
  realtimePrice?: RealtimePrice | null;
  /** 參考價格（用於計算漲跌幅） */
  referencePrice?: number | null;
  /** 分析結果 */
  analysis?: AnalysisResult | null;
  /** WebSocket 連線狀態 */
  isConnected?: boolean;
  /** 是否為當前交易時段（用於判斷是即時資料還是歷史資料） */
  isCurrentSession?: boolean;
}

/**
 * 格式化數字顯示
 */
function formatNumber(value: number): string {
  return value.toLocaleString('zh-TW');
}

/**
 * 計算成交量顏色（0-200 範圍，台指風格：數值越高越紅）
 */
function getVolumeColor(volume: number): string {
  const clampedVolume = Math.min(Math.max(volume, 0), 200);
  const ratio = clampedVolume / 200;
  
  if (ratio < 0.25) return 'bg-green-400';
  else if (ratio < 0.5) return 'bg-lime-400';
  else if (ratio < 0.75) return 'bg-yellow-400';
  else if (ratio < 0.9) return 'bg-orange-500';
  else return 'bg-red-600';
}

/**
 * 根據信號決定顏色（專業淺色主題 + 台灣風格：紅漲線跌）
 */
function getSignalColor(signal: string): string {
  if (signal.includes('強多')) return 'bg-red-600 text-white';
  if (signal.includes('偏多')) return 'bg-red-100 text-red-700';
  if (signal.includes('強空')) return 'bg-green-600 text-white';
  if (signal.includes('偏空')) return 'bg-green-100 text-green-700';
  return 'bg-gray-100 dark:bg-gray-700 text-gray-700';
}

/**
 * 根據情緒決定顏色（專業淺色主題 + 台灣風格）
 */
function getSentimentColor(label: string): string {
  if (label.includes('貧婪')) return 'text-red-600';
  if (label.includes('恐慌')) return 'text-green-600';
  return 'text-gray-600';
}

/**
 * 根據波動率決定操作建議與顏色：
 * >= 50% 代表走勢來回震盪，適合低買高賣；< 50% 代表走勢單向，適合順勢操作
 */
function getVolatilityInfo(volatility: number): { label: string; color: string } {
  if (volatility >= 50) return { label: '低買高賣', color: 'text-orange-600' };
  return { label: '順勢', color: 'text-blue-600' };
}

/**
 * 指標說明結構：用途、計算方式、分級門檻
 */
interface MetricInfo {
  purpose: string;
  formula: string;
  levels: string[];
}

/**
 * 各指標的用意與計算方式說明（參考 apps/price-analyzer/src/price_analyzer/STRATEGY_README.md）
 */
const METRIC_INFO: Record<'signal' | 'sentiment' | 'volumeExplosion' | 'basis' | 'volatility', MetricInfo> = {
  signal: {
    purpose: '綜合多空比判斷',
    formula: '加權：1分鐘(25%) + 5分鐘(30%) + 30分鐘(20%) 價量趨勢 + 爆量指標(15%) + 期現價差(10%)',
    levels: ['多方 ≥70%：強多', '≥58%：偏多', '42~58%：中性', '≤42%：偏空', '≤30%：強空'],
  },
  sentiment: {
    purpose: '綜合情緒分數 (0-100)，反映市場貪婪／恐慌程度',
    formula: '加權：委買委賣比(30%) + 連續內外盤方向(25%) + 動能分數(35%) + 波動率調整(10%)',
    levels: ['≥75：極度貪婪', '≥60：貪婪', '45~55：一般', '≥25：恐慌', '<25：極度恐慌'],
  },
  volumeExplosion: {
    purpose: '偵測成交量是否異常放大',
    formula: '爆量比率 = 當前1分鐘成交量 ÷ 當日每分鐘平均成交量',
    levels: ['≥3.0x：極度爆量', '≥2.0x：嚴重爆量', '≥1.5x：爆量', '≥1.2x：放量', '<1.2x：正常'],
  },
  basis: {
    purpose: '期貨與現貨（加權指數）的價差，市場情緒的領先指標',
    formula: '期現價差 = 期貨價格 − 現貨指數',
    levels: ['正價差（期貨>現貨）：通常偏多', '逆價差（期貨<現貨）：通常偏空'],
  },
  volatility: {
    purpose: '衡量短線走勢是單向趨勢還是來回震盪，不受 tick 數量多寡影響',
    formula: '改良自 Choppiness Index：100 × log10(路徑總長 ÷ 價格範圍) ÷ log10(tick 步數)',
    levels: ['≥50%：來回震盪，適合低買高賣', '<50%：走勢單向，適合順勢操作'],
  },
};

/**
 * 帶有滑鼠懸停說明的指標小標，說明分成用途／公式／分級門檻三段顯示
 */
function MetricLabel({ label, info, className = '' }: { label: string; info: MetricInfo; className?: string }) {
  return (
    <span className={`group relative inline-flex ${className}`}>
      <span className="cursor-help border-b border-dotted border-gray-400 text-xs text-gray-500 dark:border-gray-500 dark:text-gray-400">
        {label}
      </span>
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-0 z-20 mb-1 w-64 rounded-md bg-gray-800 p-3 text-xs text-white opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 dark:bg-gray-900"
      >
        <p className="mb-1.5 font-semibold text-white">{label}</p>
        <p className="mb-1.5 leading-relaxed text-gray-300">{info.purpose}</p>
        <p className="mb-1.5 leading-relaxed text-gray-400">{info.formula}</p>
        <ul className="space-y-0.5 border-t border-gray-700 pt-1.5 leading-relaxed text-gray-200">
          {info.levels.map((level) => (
            <li key={level}>{level}</li>
          ))}
        </ul>
      </span>
    </span>
  );
}

const QuoteCard = ({ quote, realtimePrice, referencePrice, analysis, isConnected, isCurrentSession = true }: QuoteCardProps) => {
  // 追蹤更新時間
  const [updateTime, setUpdateTime] = useState<string>('');

  // 當有即時報價時更新時間
  useEffect(() => {
    if (realtimePrice) {
      const now = new Date();
      const hours = now.getHours().toString().padStart(2, '0');
      const minutes = now.getMinutes().toString().padStart(2, '0');
      const seconds = now.getSeconds().toString().padStart(2, '0');
      setUpdateTime(`${hours}:${minutes}:${seconds}`);
    } else if (quote?.updateTime) {
      // 非即時模式，顯示歷史數據的更新時間
      const date = new Date(quote.updateTime);
      const hours = date.getHours().toString().padStart(2, '0');
      const minutes = date.getMinutes().toString().padStart(2, '0');
      const seconds = date.getSeconds().toString().padStart(2, '0');
      setUpdateTime(`${hours}:${minutes}:${seconds}`);
    }
  }, [realtimePrice, quote?.updateTime]);

  // 決定使用的價格：優先使用即時報價，否則使用原本的 lastPrice
  const currentPrice = useMemo(() => {
    return realtimePrice?.price ?? quote?.lastPrice;
  }, [realtimePrice?.price, quote?.lastPrice]);
  
  // 重新計算漲跌幅（總是使用當前的 referencePrice 重新計算）
  const { change, changePercent } = useMemo(() => {
    // 如果有當前價格和參考價格，總是重新計算
    if (currentPrice != null && referencePrice != null) {
      const changeVal = currentPrice - referencePrice;
      const changePercentVal = (changeVal / referencePrice) * 100;
      return { change: changeVal, changePercent: changePercentVal };
    }
    
    // 如果沒有參考價格，使用 quote 中的值作為後備
    return { 
      change: quote?.change ?? 0, 
      changePercent: quote?.changePercent ?? 0 
    };
  }, [currentPrice, referencePrice, quote?.change, quote?.changePercent]);

  // 成交量資訊
  const { displayVolume, volumeWidth } = useMemo(() => {
    const vol = realtimePrice?.volume != null ? Math.min(realtimePrice.volume, 200) : 0;
    return {
      displayVolume: vol,
      volumeWidth: (vol / 200) * 100
    };
  }, [realtimePrice?.volume]);

  // 期現價差計算（優先使用即時數據，否則使用分析結果）
  const { basis, basisSignal, basisColor } = useMemo(() => {
    // 優先使用即時報價計算
    if (realtimePrice?.underlying_price != null && realtimePrice?.price != null) {
      const basisVal = realtimePrice.price - realtimePrice.underlying_price;
      const signal = basisVal > 0 ? '正價差' : basisVal < 0 ? '逆價差' : '平價';
      const color = basisVal > 0 ? 'text-red-600' : basisVal < 0 ? 'text-green-600' : 'text-gray-600';
      return { basis: basisVal, basisSignal: signal, basisColor: color };
    }
    
    // 否則使用分析結果中的期現價差
    if (analysis?.basis != null) {
      const basisVal = analysis.basis;
      const signal = basisVal > 0 ? '正價差' : basisVal < 0 ? '逆價差' : '平價';
      const color = basisVal > 0 ? 'text-red-600' : basisVal < 0 ? 'text-green-600' : 'text-gray-600';
      return { basis: basisVal, basisSignal: signal, basisColor: color };
    }
    
    return { basis: null, basisSignal: '--', basisColor: 'text-gray-400' };
  }, [realtimePrice?.underlying_price, realtimePrice?.price, analysis?.basis]);
  
  // 漲跌判斷和顏色
  const isPositive = change >= 0;
  const changeColor = isPositive ? 'text-red-600' : 'text-green-600';
  const bgColor = isPositive ? 'bg-red-50' : 'bg-green-50';
  
  // 完全沒有資料（歷史資料與即時資料都沒有）時才顯示空框架
  if (!quote && !realtimePrice) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        {/* 標題 */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100">
              台指期貨
            </h2>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              MXF
            </p>
          </div>
          <div className="px-3 py-1 rounded-full bg-gray-100 dark:bg-gray-700">
            <span className="text-xs font-medium text-gray-400 dark:text-gray-500">
              --
            </span>
          </div>
        </div>

        {/* 主要報價 */}
        <div className="mb-4">
          <div className="flex items-baseline gap-3">
            <span className="text-3xl font-bold text-gray-300 dark:text-gray-500">
              --,---
            </span>
            <div className="flex flex-col">
              <span className="text-base font-semibold text-gray-300 dark:text-gray-500">
                --
              </span>
              <span className="text-sm text-gray-300 dark:text-gray-500">
                --.--% 
              </span>
            </div>
          </div>
        </div>

        {/* 每秒成交量長條圖 */}
        <div className="mb-4 flex items-center gap-2">
          <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">每秒成交量:</span>
          <div className="flex-1 relative h-6 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
            <div className="absolute inset-0 flex items-center justify-end px-2 text-xs text-gray-400 dark:text-gray-500 pointer-events-none">
              <span>200</span>
            </div>
          </div>
        </div>

        {/* 更新時間與連線狀態 */}
        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            等待資料...
          </p>
          <div className="w-2 h-2 rounded-full bg-gray-300 dark:bg-gray-600" />
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      {/* 標題 */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100">
            {quote?.name ?? '台指期貨'}
          </h2>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {quote?.symbol ?? realtimePrice?.code ?? 'MXF'}
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
          <span className={`text-3xl font-bold ${changeColor}`}>
            {currentPrice != null ? formatNumber(currentPrice) : '--,---'}
          </span>
          <div className="flex flex-col">
            <span className={`text-base font-semibold ${changeColor}`}>
              {isPositive ? '+' : ''}{formatNumber(change)}
            </span>
            <span className={`text-sm ${changeColor}`}>
              {isPositive ? '+' : ''}{changePercent.toFixed(2)}%
            </span>
          </div>
        </div>
      </div>

      {/* 每秒成交量長條圖（僅即時模式顯示） */}
      {realtimePrice && (
        <div className="mb-4 flex items-center gap-2">
          <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">每秒成交量:</span>
          <div className="w-56 relative h-4 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
            <div 
              className={`h-full transition-all duration-300 ${getVolumeColor(displayVolume)}`}
              style={{ width: `${volumeWidth}%` }}
            />
            <div className="absolute inset-0 flex items-center justify-end px-2 text-xs text-gray-400 dark:text-gray-500 pointer-events-none">
              <span>200</span>
            </div>
          </div>
        </div>
      )}

      {/* 多空信號 */}
      {analysis && (
        <div className="mb-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <MetricLabel label="多空信號" info={METRIC_INFO.signal} />
            <span className={`px-3 py-1 rounded-full text-xs font-semibold ${getSignalColor(analysis.signal)}`}>
              {analysis.signal}
            </span>
          </div>
        </div>
      )}

      {/* 市場情緒與成交量 */}
      {analysis && (
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <MetricLabel label="市場情緒" info={METRIC_INFO.sentiment} className="mb-1" />
            <p className={`text-sm font-medium ${getSentimentColor(analysis.sentiment_label)}`}>
              {analysis.sentiment_label}
            </p>
          </div>
          <div>
            <MetricLabel label="成交量" info={METRIC_INFO.volumeExplosion} className="mb-1" />
            <p className="text-sm font-medium text-blue-600">
              {analysis.volume_explosion_level}
            </p>
          </div>
        </div>
      )}

      {/* 期現價差與波動率 */}
      {basis != null && (
        <div className="grid grid-cols-2 gap-4 mb-4 pt-2 border-t border-gray-200 dark:border-gray-700">
          <div>
            <MetricLabel label="期現價差" info={METRIC_INFO.basis} className="mb-1" />
            <p className={`text-sm font-medium ${basisColor}`}>
              {basis > 0 ? '+' : ''}{basis.toFixed(0)} ({basisSignal})
            </p>
          </div>
          <div>
            <MetricLabel label="波動率" info={METRIC_INFO.volatility} className="mb-1" />
            <p className={`text-sm font-medium ${analysis?.volatility != null ? getVolatilityInfo(analysis.volatility).color : 'text-gray-400'}`}>
              {analysis?.volatility != null
                ? `${analysis.volatility}% (${getVolatilityInfo(analysis.volatility).label})`
                : '--'}
            </p>
          </div>
        </div>
      )}

      {/* 更新時間與連線狀態 */}
      <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {updateTime ? `更新時間: ${updateTime}` : '等待資料...'}
        </p>
        <div className={`w-2 h-2 rounded-full ${
          isCurrentSession && isConnected
            ? 'bg-green-500 animate-pulse'
            : 'bg-gray-300'
        }`} 
             title={
               isCurrentSession && isConnected
                 ? '即時連線'
                 : isCurrentSession
                   ? '連線中斷，使用分鐘資料'
                   : '歷史資料'
             } />
      </div>
    </div>
  );
};

export default memo(QuoteCard);
