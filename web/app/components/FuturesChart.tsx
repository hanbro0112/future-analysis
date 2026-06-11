'use client';

/**
 * 台指期折線圖元件
 * 簡潔風格，參考永豐金格式
 */

import { useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine
} from 'recharts';
import type { PricePoint } from '../types/futures';

interface FuturesChartProps {
  /** 價格資料 */
  data: PricePoint[];
  /** 開盤價（用於參考線） */
  openPrice?: number;
}

/**
 * 格式化時間顯示
 */
function formatTime(date: Date): string {
  return date.toLocaleTimeString('zh-TW', { 
    hour: '2-digit', 
    minute: '2-digit' 
  });
}

/**
 * 格式化價格顯示
 */
function formatPrice(value: number): string {
  return value.toLocaleString('zh-TW');
}

export default function FuturesChart({ data, openPrice }: FuturesChartProps) {
  // 轉換資料格式供 Recharts 使用
  const chartData = useMemo(() => {
    return data.map(point => ({
      time: formatTime(point.timestamp),
      price: point.price,
      timestamp: point.timestamp.getTime()
    }));
  }, [data]);

  // 計算價格範圍
  const { minPrice, maxPrice, priceRange } = useMemo(() => {
    if (chartData.length === 0) {
      return { minPrice: 0, maxPrice: 0, priceRange: 0 };
    }
    
    const prices = chartData.map(d => d.price);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min;
    
    // 加上 5% 的邊距
    const padding = range * 0.05;
    
    return {
      minPrice: Math.floor(min - padding),
      maxPrice: Math.ceil(max + padding),
      priceRange: range
    };
  }, [chartData]);

  // 決定線條顏色（相對於開盤價）
  const lineColor = useMemo(() => {
    if (!openPrice || chartData.length === 0) return '#6b7280';
    const lastPrice = chartData[chartData.length - 1].price;
    return lastPrice >= openPrice ? '#ef4444' : '#22c55e';
  }, [chartData, openPrice]);

  // 自訂 Tooltip
  const CustomTooltip = ({ active, payload }: any) => {
    if (!active || !payload || payload.length === 0) return null;
    
    const data = payload[0].payload;
    const price = data.price;
    const change = openPrice ? price - openPrice : 0;
    const changePercent = openPrice ? ((change / openPrice) * 100).toFixed(2) : '0.00';
    
    return (
      <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 shadow-lg">
        <p className="text-xs text-gray-500 dark:text-gray-400">{data.time}</p>
        <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          {formatPrice(price)}
        </p>
        {openPrice && (
          <p className={`text-xs ${change >= 0 ? 'text-red-500' : 'text-green-500'}`}>
            {change >= 0 ? '+' : ''}{change.toFixed(0)} ({change >= 0 ? '+' : ''}{changePercent}%)
          </p>
        )}
      </div>
    );
  };

  if (chartData.length === 0) {
    return (
      <div className="w-full h-[400px] flex items-center justify-center text-gray-400">
        載入資料中...
      </div>
    );
  }

  return (
    <div className="w-full h-[400px]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={chartData}
          margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
        >
          <CartesianGrid 
            strokeDasharray="3 3" 
            stroke="#e5e7eb"
            vertical={false}
          />
          <XAxis 
            dataKey="time"
            stroke="#9ca3af"
            style={{ fontSize: '12px' }}
            tickLine={false}
            interval="preserveStartEnd"
            minTickGap={50}
          />
          <YAxis 
            domain={[minPrice, maxPrice]}
            stroke="#9ca3af"
            style={{ fontSize: '12px' }}
            tickLine={false}
            tickFormatter={formatPrice}
            width={60}
          />
          <Tooltip content={<CustomTooltip />} />
          
          {/* 開盤價參考線 */}
          {openPrice && (
            <ReferenceLine 
              y={openPrice} 
              stroke="#9ca3af" 
              strokeDasharray="3 3"
              strokeWidth={1}
            />
          )}
          
          <Line
            type="monotone"
            dataKey="price"
            stroke={lineColor}
            strokeWidth={2}
            dot={false}
            animationDuration={300}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
