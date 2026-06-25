'use client'

import { ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import type { MinuteChartPoint } from '../types/minuteData'

interface MinuteChartProps {
  data: MinuteChartPoint[]
  title?: string
  marketType?: 'regular' | 'after_hours' // 市場類型：日盤或夜盤
}

/**
 * 自訂 Tooltip 組件
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
      <div className="bg-white/95 backdrop-blur-sm border border-gray-200 rounded-lg p-3 shadow-lg">
        <p className="font-semibold text-gray-900 mb-2">{displayTime}</p>
        <div className="space-y-1 text-sm">
          <p className="text-blue-600">
            平均價: <span className="font-semibold">{data.avg_price.toFixed(0)}</span>
          </p>
          <p className="text-green-600">
            最高價: <span className="font-semibold">{data.high.toFixed(0)}</span>
          </p>
          <p className="text-red-600">
            最低價: <span className="font-semibold">{data.low.toFixed(0)}</span>
          </p>
          <p className="text-purple-600">
            成交量: <span className="font-semibold">{data.volume.toLocaleString()}</span>
          </p>
          <div className="flex gap-3 pt-1 border-t border-gray-200 mt-2">
            <p className="text-green-500 text-xs">
              買: {data.buy_volume.toLocaleString()}
            </p>
            <p className="text-red-500 text-xs">
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
export default function MinuteChart({ data, title = '分鐘級走勢', marketType = 'regular' }: MinuteChartProps) {
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

  // 計算成交量最大值（用於設定右側 Y 軸）
  const maxVolume = hasData ? Math.max(...normalizedData.map(d => d.volume)) : 1000;

  // Debug: 輸出處理結果
  if (hasData) {
    console.log('📊 MinuteChart Debug:', {
      原始資料筆數: data.length,
      完整時間範圍: chartData.length,
      有效資料點: chartData.filter(d => d.avg_price !== null).length,
      時間範例: chartData.slice(0, 5).map(d => d.time),
      整點刻度: hourTicks
    });
  }

  return (
    <div className="bg-white rounded-lg shadow-sm p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
        {!hasData && (
          <span className="text-sm text-gray-400 animate-pulse">載入中...</span>
        )}
      </div>
      
      <ResponsiveContainer width="100%" height={400}>
        <ComposedChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 30 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          
          {/* X 軸：時間（只在整點顯示標籤） */}
          <XAxis 
            dataKey="time"
            type="category"
            tick={{ fontSize: 12, fill: '#666' }}
            tickLine={{ stroke: '#e5e7eb' }}
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
            tick={{ fontSize: 12 }}
            tickFormatter={(value) => value.toFixed(0)}
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
            wrapperStyle={{ fontSize: '12px' }}
            iconType="line"
          />
          
          {/* 成交量柱狀圖（背景） */}
          <Bar 
            yAxisId="volume"
            dataKey="volume" 
            fill="#e0e7ff" 
            opacity={0.3}
            name="成交量"
            radius={[4, 4, 0, 0]}
          />
          
          {/* 最低價線（淡紅色） */}
          <Line 
            yAxisId="price"
            type="monotone" 
            dataKey="low" 
            stroke="#fca5a5" 
            strokeWidth={1}
            dot={false}
            strokeDasharray="3 3"
            name="最低價"
            opacity={0.5}
            connectNulls={false}
          />
          
          {/* 最高價線（淡綠色） */}
          <Line 
            yAxisId="price"
            type="monotone" 
            dataKey="high" 
            stroke="#86efac" 
            strokeWidth={1}
            dot={false}
            strokeDasharray="3 3"
            name="最高價"
            opacity={0.5}
            connectNulls={false}
          />
          
          {/* 平均價線（主線，藍色） */}
          <Line 
            yAxisId="price"
            type="monotone" 
            dataKey="avg_price" 
            stroke="#3b82f6" 
            strokeWidth={2.5}
            dot={false}
            activeDot={{ r: 5 }}
            name="平均價"
            connectNulls={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
