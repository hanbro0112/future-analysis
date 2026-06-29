'use client'

import { useState, useEffect } from 'react'
import { ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import type { MinuteChartPoint, AnalysisResult } from '../types/minuteData'

interface MinuteChartProps {
  data: MinuteChartPoint[]
  title?: string
  marketType?: 'regular' | 'after_hours' // 市場類型：日盤或夜盤
  latestAnalysis?: AnalysisResult | null // 最新的分析結果（用於決定線條顏色）
  isLoading?: boolean // 是否載入中
}

/**
 * 根據成交量比例決定線條顏色
 * 藍色 → 深藍 → 紅色 → 深紅 → 黑色（嚴重爆量）
 */
function getVolumeColor(volumeRatio: number): string {
  // volumeRatio: 當前成交量 / 平均成交量
  // < 0.8: 淡藍色（量縮）
  if (volumeRatio < 0.8) {
    return '#60a5fa'; // 淡藍色
  }
  // 0.8 - 1.2: 藍色（正常）
  else if (volumeRatio < 1.2) {
    const t = (volumeRatio - 0.8) / 0.4; // 0-1
    const r = Math.floor(96 - t * 37); // 96 -> 59
    const g = Math.floor(165 - t * 35); // 165 -> 130
    const b = Math.floor(250 - t * 4); // 250 -> 246
    return `rgb(${r}, ${g}, ${b})`; // #60a5fa -> #3b82f6
  }
  // 1.2 - 1.8: 深藍色（小放量）
  else if (volumeRatio < 1.8) {
    const t = (volumeRatio - 1.2) / 0.6; // 0-1
    const r = Math.floor(59 - t * 34); // 59 -> 25
    const g = Math.floor(130 - t * 61); // 130 -> 69
    const b = Math.floor(246 - t * 113); // 246 -> 133
    return `rgb(${r}, ${g}, ${b})`; // #3b82f6 -> #194585
  }
  // 1.8 - 2.5: 紅色（放量）
  else if (volumeRatio < 2.5) {
    const t = (volumeRatio - 1.8) / 0.7; // 0-1
    const r = Math.floor(25 + t * 214); // 25 -> 239
    const g = Math.floor(69 - t * 1); // 69 -> 68
    const b = Math.floor(133 - t * 65); // 133 -> 68
    return `rgb(${r}, ${g}, ${b})`; // #194585 -> #ef4444
  }
  // 2.5 - 3.5: 深紅色（爆量）
  else if (volumeRatio < 3.5) {
    const t = (volumeRatio - 2.5) / 1.0; // 0-1
    const r = Math.floor(239 - t * 19); // 239 -> 220
    const g = Math.floor(68 - t * 30); // 68 -> 38
    const b = Math.floor(68 - t * 30); // 68 -> 38
    return `rgb(${r}, ${g}, ${b})`; // #ef4444 -> #dc2626
  }
  // > 3.5: 黑色（嚴重爆量）
  else {
    return '#1f2937'; // 深灰黑色
  }
}

/**
 * 自訂 Tooltip 組件（專業淺色主題）
 */
const CustomTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload
    
    // 如果該時段沒有資料，不顯示 tooltip
    if (data.avg_price === null) {
      return null;
    }
    
    // 格式化時間：顯示完整時間
    const displayTime = data.time;
    
    return (
      <div className="bg-white/95 backdrop-blur-sm border border-gray-300 rounded-lg p-3 shadow-lg">
        <p className="font-semibold text-gray-800 mb-2 text-xs">{displayTime}</p>
        <div className="space-y-1 text-xs">
          <p className="text-gray-700">
            平均價: <span className="font-semibold text-blue-600">{data.avg_price.toFixed(0)}</span>
          </p>
          <p className="text-gray-700">
            最高價: <span className="font-semibold text-red-600">{data.high.toFixed(0)}</span>
          </p>
          <p className="text-gray-700">
            最低價: <span className="font-semibold text-green-600">{data.low.toFixed(0)}</span>
          </p>
          <p className="text-gray-700">
            成交量: <span className="font-semibold">{data.volume.toLocaleString()}</span>
          </p>
          <div className="flex gap-3 pt-1 border-t border-gray-200 mt-2">
            <p className="text-red-600 text-xs">
              買: {data.buy_volume.toLocaleString()}
            </p>
            <p className="text-green-600 text-xs">
              賣: {data.sell_volume.toLocaleString()}
            </p>
          </div>
        </div>
      </div>
    )
  }
  return null
}

/**
 * 分鐘級線路圖組件
 * - 平均價格折線圖
 * - 高低價格淡色線
 * - 成交量柱狀圖背景
 */
export default function MinuteChart({ data, title = '分鐘級走勢', marketType = 'regular', latestAnalysis = null, isLoading = false }: MinuteChartProps) {
  // 控制是否顯示高低價線（日盤預設開啟，夜盤預設關閉）
  const [showHighLow, setShowHighLow] = useState(marketType === 'regular');
  
  // 當 marketType 改變時，更新 showHighLow 狀態
  useEffect(() => {
    setShowHighLow(marketType === 'regular');
  }, [marketType]);
  
  // 處理並標準化時間格式為 'HH:mm'
  const normalizedData = data.map(item => {
    let timeStr = item.time;
    
    // 處理 HHMM 格式（沒有冒號）
    if (!timeStr.includes(':')) {
      if (timeStr.length === 4) {
        timeStr = `${timeStr.slice(0, 2)}:${timeStr.slice(2)}`;
      } else if (timeStr.length === 3) {
        timeStr = `0${timeStr.slice(0, 1)}:${timeStr.slice(1)}`;
      }
    }
    
    return {
      ...item,
      time: timeStr
    };
  });

  // 生成完整的時間範圍（固定範圍）
  const generateFullTimeRange = () => {
    const times: string[] = [];
    
    if (marketType === 'regular') {
      // 日盤：08:45 - 13:45
      for (let h = 8; h <= 13; h++) {
        const startMin = h === 8 ? 45 : 0;
        const endMin = h === 13 ? 45 : 59;
        for (let m = startMin; m <= endMin; m++) {
          times.push(`${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`);
        }
      }
    } else {
      // 夜盤：15:00 - 05:00（跨日）
      // 15:00 - 23:59
      for (let h = 15; h <= 23; h++) {
        for (let m = 0; m <= 59; m++) {
          times.push(`${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`);
        }
      }
      // 00:00 - 05:00
      for (let h = 0; h <= 5; h++) {
        for (let m = 0; m <= 59; m++) {
          times.push(`${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`);
        }
      }
    }
    
    return times;
  };

  const fullTimeRange = generateFullTimeRange();

  // 建立資料查找表
  const dataMap = new Map(normalizedData.map(item => [item.time, item]));

  // 填充完整時間範圍的資料（沒有資料的時段設為 null）
  const chartData = fullTimeRange.map(time => {
    const dataPoint = dataMap.get(time);
    return dataPoint || {
      time,
      avg_price: null as number | null,
      high: null as number | null,
      low: null as number | null,
      volume: 0,
      buy_volume: 0,
      sell_volume: 0
    };
  });

  // 生成整點刻度（用於橫軸標籤）
  const generateHourTicks = () => {
    if (marketType === 'regular') {
      // 日盤：08-13（整點）
      return ['08:00', '09:00', '10:00', '11:00', '12:00', '13:00'];
    } else {
      // 夜盤：15-05（整點，跨日）
      return ['15:00', '16:00', '17:00', '18:00', '19:00', '20:00', '21:00', '22:00', '23:00', '00:00', '01:00', '02:00', '03:00', '04:00', '05:00'];
    }
  };

  const hourTicks = generateHourTicks();

  // 計算價格範圍（用於設定 Y 軸）
  const hasData = normalizedData && normalizedData.length > 0;
  const prices = hasData ? normalizedData.flatMap(d => [d.avg_price, d.high, d.low]) : [20000, 22000];
  const minPrice = hasData ? Math.floor(Math.min(...prices) * 0.999) : 20000;
  const maxPrice = hasData ? Math.ceil(Math.max(...prices) * 1.001) : 22000;

  // 計算成交量最大值和平均值
  const maxVolume = hasData ? Math.max(...normalizedData.map(d => d.volume)) : 1000;
  const avgVolume = hasData ? normalizedData.reduce((sum, d) => sum + d.volume, 0) / normalizedData.length : 1000;

  // 決定線條顏色：根據成交量決定（藍色 -> 黃色 -> 紅色）
  let lineColor: string;
  if (hasData && normalizedData.length > 0) {
    // 使用最新一筆資料的成交量
    const latestVolume = normalizedData[normalizedData.length - 1].volume;
    const volumeRatio = latestVolume / avgVolume;
    lineColor = getVolumeColor(volumeRatio);
  } else {
    lineColor = '#3b82f6'; // 預設藍色
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-semibold text-gray-800">{title}</h3>
        <div className="flex items-center gap-3">
          {!isLoading && (
            <label className="flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer hover:text-gray-800 transition-colors">
              <input
                type="checkbox"
                checked={showHighLow}
                onChange={(e) => setShowHighLow(e.target.checked)}
                className="w-3.5 h-3.5 text-blue-600 rounded border-gray-300 focus:ring-2 focus:ring-blue-500 focus:ring-offset-0 cursor-pointer"
              />
              <span>顯示區間高低價</span>
            </label>
          )}
          {isLoading && (
            <span className="text-sm text-gray-400 animate-pulse">載入中...</span>
          )}
        </div>
      </div>
      
      <ResponsiveContainer width="100%" height={400}>
        <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 30 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
          
          {/* X 軸：時間（只在整點顯示標籤） */}
          <XAxis 
            dataKey="time"
            type="category"
            tick={{ fontSize: 11, fill: '#6b7280' }}
            tickLine={false}
            axisLine={{ stroke: '#e5e7eb' }}
            angle={0}
            textAnchor="middle"
            height={50}
            ticks={hourTicks}
            tickFormatter={(value: string) => {
              // 顯示小時部分
              if (value.includes(':')) {
                return value.split(':')[0];
              }
              return value;
            }}
          />
          
          {/* 左側 Y 軸：價格 */}
          <YAxis 
            yAxisId="price"
            domain={[minPrice, maxPrice]}
            tick={{ fontSize: 11, fill: '#6b7280' }}
            tickLine={false}
            axisLine={{ stroke: '#e5e7eb' }}
            tickFormatter={(value) => value.toFixed(0)}
            width={60}
          />
          
          {/* 右側 Y 軸：成交量（隱藏） */}
          <YAxis 
            yAxisId="volume"
            orientation="right"
            domain={[0, maxVolume * 5]}
            hide={true}
          />
          
          <Tooltip content={<CustomTooltip />} />
          
          <Legend 
            wrapperStyle={{ fontSize: '11px', color: '#374151' }}
            iconType="line"
            iconSize={10}
            payload={[
              { value: '成交量', type: 'rect', color: '#3b82f6' },
              { value: '最低價', type: 'line', color: '#374151' },
              { value: '最高價', type: 'line', color: '#374151' }
            ]}
          />
          
          {/* 成交量柱狀圖（背景，淡藍色） */}
          <Bar 
            yAxisId="volume"
            dataKey="volume" 
            fill="#3b82f6" 
            opacity={0.7}
            name="成交量"
            radius={[2, 2, 0, 0]}
          />
          
          {/* 最低價線（黑色細虛線）- 根據選項顯示 */}
          {showHighLow && (
            <Line 
              yAxisId="price"
              type="monotone" 
              dataKey="low" 
              stroke="#374151" 
              strokeWidth={1}
              dot={false}
              strokeDasharray="3 3"
              name="最低價"
              opacity={0.6}
              connectNulls={false}
            />
          )}
          
          {/* 最高價線（黑色細虛線）- 根據選項顯示 */}
          {showHighLow && (
            <Line 
              yAxisId="price"
              type="monotone" 
              dataKey="high" 
              stroke="#374151" 
              strokeWidth={1}
              dot={false}
              strokeDasharray="3 3"
              name="最高價"
              opacity={0.6}
              connectNulls={false}
            />
          )}
          
          {/* 平均價線（主線，根據市場情緒顯示顏色，台灣風格） */}
          <Line 
            yAxisId="price"
            type="monotone" 
            dataKey="avg_price" 
            stroke={lineColor}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: lineColor, strokeWidth: 2, stroke: '#fff' }}
            hide={false}
            connectNulls={false}
            opacity={0.7}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
