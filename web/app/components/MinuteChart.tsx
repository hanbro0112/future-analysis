'use client'

import { useState, useEffect, useMemo, useRef, useCallback, memo } from 'react'
import { ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceDot } from 'recharts'
import type { MinuteChartPoint, AnalysisResult } from '../types/minuteData'

interface MinuteChartProps {
  data: MinuteChartPoint[] // 當前市場類型的資料（保持向後兼容）
  dayData?: MinuteChartPoint[] // 日盤資料（可選）
  nightData?: MinuteChartPoint[] // 夜盤資料（可選）
  title?: string
  marketType?: 'regular' | 'after_hours' // 市場類型：日盤或夜盤
  latestAnalysis?: AnalysisResult | null // 最新的分析結果（用於決定線條顏色）
  isLoading?: boolean // 是否載入中
  referencePrice?: number // 基準價格（用於漲跌幅計算，Y軸中心）
}

/**
 * 根據成交量比例決定線條顏色
 * 灰藍 → 藍 → 紫 → 橙 → 紅 → 深紅（優化配色）
 */
function getVolumeColor(volumeRatio: number): string {
  // volumeRatio: 當前成交量 / 平均成交量
  // < 0.8: 淺灰藍（量縮）
  if (volumeRatio < 0.8) {
    return '#94a3b8'; // slate-400
  }
  // 0.8 - 1.2: 灰藍 → 藍色（正常）
  else if (volumeRatio < 1.2) {
    const t = (volumeRatio - 0.8) / 0.4; // 0-1
    const r = Math.floor(148 - t * 89); // 148 -> 59
    const g = Math.floor(163 - t * 33); // 163 -> 130
    const b = Math.floor(184 + t * 62); // 184 -> 246
    return `rgb(${r}, ${g}, ${b})`; // #94a3b8 -> #3b82f6
  }
  // 1.2 - 1.8: 藍色 → 紫藍色（小放量）
  else if (volumeRatio < 1.8) {
    const t = (volumeRatio - 1.2) / 0.6; // 0-1
    const r = Math.floor(59 + t * 80); // 59 -> 139
    const g = Math.floor(130 - t * 38); // 130 -> 92
    const b = 246; // 保持不變
    return `rgb(${r}, ${g}, ${b})`; // #3b82f6 -> #8b5cf6
  }
  // 1.8 - 2.5: 紫藍色 → 橙紅色（放量）
  else if (volumeRatio < 2.5) {
    const t = (volumeRatio - 1.8) / 0.7; // 0-1
    const r = Math.floor(139 + t * 110); // 139 -> 249
    const g = Math.floor(92 + t * 23); // 92 -> 115
    const b = Math.floor(246 - t * 224); // 246 -> 22
    return `rgb(${r}, ${g}, ${b})`; // #8b5cf6 -> #f97316
  }
  // 2.5 - 3.5: 橙紅色 → 紅色（爆量）
  else if (volumeRatio < 3.5) {
    const t = (volumeRatio - 2.5) / 1.0; // 0-1
    const r = Math.floor(249 - t * 10); // 249 -> 239
    const g = Math.floor(115 - t * 47); // 115 -> 68
    const b = Math.floor(22 + t * 46); // 22 -> 68
    return `rgb(${r}, ${g}, ${b})`; // #f97316 -> #ef4444
  }
  // > 3.5: 深紅色（嚴重爆量）
  else {
    return '#991b1b'; // red-800
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
        <p className="font-semibold text-gray-800 dark:text-gray-100 mb-2 text-xs">{displayTime}</p>
        <div className="space-y-1 text-xs">
          <p className="text-gray-700 dark:text-gray-300">
            平均價: <span className="font-semibold text-blue-600">{data.avg_price.toFixed(0)}</span>
          </p>
          {data.taiex != null && (
            <p className="text-gray-700 dark:text-gray-300">
              加權指數: <span className="font-semibold text-yellow-600">{data.taiex.toFixed(2)}</span>
            </p>
          )}
          <p className="text-gray-700 dark:text-gray-300">
            最高價: <span className="font-semibold text-red-600">{data.high.toFixed(0)}</span>
          </p>
          <p className="text-gray-700 dark:text-gray-300">
            最低價: <span className="font-semibold text-green-600">{data.low.toFixed(0)}</span>
          </p>
          <p className="text-gray-700 dark:text-gray-300">
            成交量: <span className="font-semibold">{data.volume.toLocaleString()}</span>
          </p>
          <div className="flex gap-3 pt-1 border-t border-gray-200 dark:border-gray-700 mt-2">
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
const MinuteChart = ({ data, dayData, nightData, title = '分鐘級走勢', marketType = 'regular', latestAnalysis = null, isLoading = false, referencePrice }: MinuteChartProps) => {
  // 控制是否顯示高低價線（預設關閉）
  const [showHighLow, setShowHighLow] = useState(false);
  // 控制是否顯示加權指數線（預設開啟）
  const [showTaiex, setShowTaiex] = useState(true);
  
  // 判斷是否使用預先計算模式（有提供日盤和夜盤數據）
  const usePrecomputedMode = dayData !== undefined && nightData !== undefined;
  
  // 處理並標準化時間格式為 'HH:mm' - 為每個市場類型分別處理
  const normalizedDayData = useMemo(() => {
    if (!usePrecomputedMode || !dayData) return [];
    return dayData.map(item => {
      let timeStr = item.time;
      if (!timeStr.includes(':')) {
        if (timeStr.length === 4) {
          timeStr = `${timeStr.slice(0, 2)}:${timeStr.slice(2)}`;
        } else if (timeStr.length === 3) {
          timeStr = `0${timeStr.slice(0, 1)}:${timeStr.slice(1)}`;
        }
      }
      return { ...item, time: timeStr };
    });
  }, [dayData, usePrecomputedMode]);

  const normalizedNightData = useMemo(() => {
    if (!usePrecomputedMode || !nightData) return [];
    return nightData.map(item => {
      let timeStr = item.time;
      if (!timeStr.includes(':')) {
        if (timeStr.length === 4) {
          timeStr = `${timeStr.slice(0, 2)}:${timeStr.slice(2)}`;
        } else if (timeStr.length === 3) {
          timeStr = `0${timeStr.slice(0, 1)}:${timeStr.slice(1)}`;
        }
      }
      return { ...item, time: timeStr };
    });
  }, [nightData, usePrecomputedMode]);
  
  // 處理並標準化時間格式為 'HH:mm' - 單一數據集模式（向後兼容）
  const normalizedData = useMemo(() => {
    if (usePrecomputedMode) {
      // 預先計算模式：根據 marketType 選擇對應的數據
      return marketType === 'regular' ? normalizedDayData : normalizedNightData;
    }
    // 單一數據集模式
    return data.map(item => {
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
  }, [data, usePrecomputedMode, marketType, normalizedDayData, normalizedNightData]);

  // 生成完整的時間範圍（固定範圍）- 為兩個市場類型分別生成
  const dayTimeRange = useMemo(() => {
    const times: string[] = [];
    // 日盤：08:45 - 13:45
    for (let h = 8; h <= 13; h++) {
      const startMin = h === 8 ? 45 : 0;
      const endMin = h === 13 ? 45 : 59;
      for (let m = startMin; m <= endMin; m++) {
        times.push(`${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`);
      }
    }
    return times;
  }, []);

  const nightTimeRange = useMemo(() => {
    const times: string[] = [];
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
    return times;
  }, []);

  // 根據當前市場類型選擇時間範圍（向後兼容）
  const fullTimeRange = marketType === 'regular' ? dayTimeRange : nightTimeRange;

  // 計算價格範圍（用於設定 Y 軸）
  const hasData = normalizedData && normalizedData.length > 0;
  
  // 檢查是否有加權指數資料（僅日盤）
  const hasTaiex = hasData && normalizedData.some(d => d.taiex != null);

  // 計算 Legend payload
  const legendPayload = useMemo((): any => {
    return hasTaiex 
      ? [
          { value: '成交量', type: 'rect', color: '#3b82f6' },
          { value: '加權指數', type: 'line', color: '#eab308' },
          { value: '區間高低價', type: 'line', color: '#374151' }
        ]
      : [
          { value: '成交量', type: 'rect', color: '#3b82f6' },
          { value: '區間高低價', type: 'line', color: '#374151' }
        ];
  }, [hasTaiex]);

  // 計算平均成交量（用於顏色計算）- 為兩個市場類型分別計算
  const dayAvgVolume = useMemo(() => {
    if (!usePrecomputedMode || normalizedDayData.length === 0) return 1000;
    return normalizedDayData.reduce((sum, d) => sum + d.volume, 0) / normalizedDayData.length;
  }, [normalizedDayData, usePrecomputedMode]);

  const nightAvgVolume = useMemo(() => {
    if (!usePrecomputedMode || normalizedNightData.length === 0) return 1000;
    return normalizedNightData.reduce((sum, d) => sum + d.volume, 0) / normalizedNightData.length;
  }, [normalizedNightData, usePrecomputedMode]);

  const avgVolume = usePrecomputedMode 
    ? (marketType === 'regular' ? dayAvgVolume : nightAvgVolume)
    : (hasData ? normalizedData.reduce((sum, d) => sum + d.volume, 0) / normalizedData.length : 1000);

  // 函數：計算 chartData 和 lineSegments
  const computeChartDataAndSegments = useCallback((
    dataArray: MinuteChartPoint[],
    timeRange: string[],
    avgVol: number
  ) => {
    const dataMap = new Map(dataArray.map(item => [item.time, item]));

    const chart = timeRange.map(time => {
      const dataPoint = dataMap.get(time);
      if (dataPoint) {
        const volumeRatio = dataPoint.volume / avgVol;
        const color = getVolumeColor(volumeRatio);
        
        // 盤前時段 (08:45-08:59) 不顯示加權指數
        const [hour] = time.split(':').map(Number);
        const shouldHideTaiex = hour === 8;
        
        return {
          ...dataPoint,
          taiex: shouldHideTaiex ? undefined : dataPoint.taiex,
          color
        };
      }
      return {
        time,
        avg_price: null as number | null,
        high: null as number | null,
        low: null as number | null,
        volume: 0,
        buy_volume: 0,
        sell_volume: 0,
        color: '#3b82f6'
      };
    });

    // 第一步：生成所有線段（相鄰的點之間）
    let segmentIndex = 0;
    const allSegments: Array<{ idx: number; color: string }> = [];
    
    for (let i = 0; i < chart.length - 1; i++) {
      const current = chart[i];
      const next = chart[i + 1];
      
      if (current.avg_price !== null && next.avg_price !== null) {
        allSegments.push({
          idx: i,
          color: current.color
        });
      }
    }

    // 第二步：合併連續相同顏色的線段
    const mergedSegments: Array<{ startIdx: number; endIdx: number; color: string }> = [];
    let currentMerged: { startIdx: number; endIdx: number; color: string } | null = null;
    
    allSegments.forEach((seg) => {
      if (!currentMerged) {
        currentMerged = { startIdx: seg.idx, endIdx: seg.idx + 1, color: seg.color };
      } else if (currentMerged.color === seg.color && currentMerged.endIdx === seg.idx) {
        // 同色且連續，延伸區段
        currentMerged.endIdx = seg.idx + 1;
      } else {
        // 顏色改變或不連續，儲存前一個區段
        mergedSegments.push(currentMerged);
        currentMerged = { startIdx: seg.idx, endIdx: seg.idx + 1, color: seg.color };
      }
    });
    
    if (currentMerged) {
      mergedSegments.push(currentMerged);
    }

    // 第三步：為合併後的線段生成 dataKey
    const finalSegments: Array<{ dataKey: string; color: string }> = [];
    mergedSegments.forEach((merged, mergedIdx) => {
      const dataKey = `merged_${mergedIdx}`;
      
      // 為這個合併線段涵蓋的所有點添加 dataKey
      for (let i = merged.startIdx; i <= merged.endIdx; i++) {
        if (i < chart.length && chart[i].avg_price !== null) {
          (chart[i] as any)[dataKey] = chart[i].avg_price;
        }
      }
      
      finalSegments.push({
        dataKey,
        color: merged.color
      });
    });

    // console.log(`[計算] 原始線段: ${allSegments.length}, 合併後: ${finalSegments.length}`);
    return { chartData: chart, lineSegments: finalSegments };
  }, []);

  // 使用 useRef 保存預先計算的結果（支持增量更新）
  const dayChartRef = useRef<{
    normalizedData: MinuteChartPoint[];
    chartData: any[];
    lineSegments: Array<{ dataKey: string; color: string }>;
  } | null>(null);
  
  const nightChartRef = useRef<{
    normalizedData: MinuteChartPoint[];
    chartData: any[];
    lineSegments: Array<{ dataKey: string; color: string }>;
  } | null>(null);

  // 為日盤預先計算（支持增量更新）
  const dayChartResult = useMemo(() => {
    if (!usePrecomputedMode) return { chartData: [], lineSegments: [] };
    
    const prev = dayChartRef.current;
    
    // 如果數據長度沒變，直接返回上次結果（避免不必要的重新計算）
    if (prev && prev.normalizedData.length === normalizedDayData.length) {
      return { chartData: prev.chartData, lineSegments: prev.lineSegments };
    }
    
    const canIncremental = prev && 
      prev.normalizedData.length > 0 &&
      normalizedDayData.length > prev.normalizedData.length &&
      normalizedDayData.length - prev.normalizedData.length <= 2;
    
    if (canIncremental) {
      // console.log('[日盤] 增量更新，新增', normalizedDayData.length - prev!.normalizedData.length, '筆');
      // 複製前一次的結果
      const chart = [...prev!.chartData];
      const segments = [...prev!.lineSegments];
      
      // 只處理新增的資料點
      const newPoints = normalizedDayData.slice(prev!.normalizedData.length);
      
      newPoints.forEach(point => {
        const timeIndex = dayTimeRange.indexOf(point.time);
        if (timeIndex >= 0) {
          const volumeRatio = point.volume / dayAvgVolume;
          const color = getVolumeColor(volumeRatio);
          chart[timeIndex] = {
            ...point,
            color
          };
          
          // 檢查是否需要新增線段（與前一個點連接）
          if (timeIndex > 0 && chart[timeIndex - 1].avg_price !== null) {
            const prevColor = chart[timeIndex - 1].color;
            const lastSeg = segments[segments.length - 1];
            
            // 如果與最後一個線段同色，延伸該線段
            if (lastSeg && lastSeg.color === prevColor) {
              const lastDataKey = lastSeg.dataKey;
              (chart[timeIndex] as any)[lastDataKey] = point.avg_price;
            } else {
              // 否則建立新線段
              const newDataKey = `merged_${segments.length}`;
              (chart[timeIndex - 1] as any)[newDataKey] = chart[timeIndex - 1].avg_price;
              (chart[timeIndex] as any)[newDataKey] = point.avg_price;
              segments.push({ dataKey: newDataKey, color: prevColor });
            }
          }
        }
      });
      
      const result = { chartData: chart, lineSegments: segments };
      dayChartRef.current = {
        normalizedData: normalizedDayData,
        chartData: chart,
        lineSegments: segments
      };
      return result;
    }
    
    // 完整計算
    // console.log('[日盤] 完整計算，共', normalizedDayData.length, '筆資料');
    const result = computeChartDataAndSegments(normalizedDayData, dayTimeRange, dayAvgVolume);
    dayChartRef.current = {
      normalizedData: normalizedDayData,
      chartData: result.chartData,
      lineSegments: result.lineSegments
    };
    return result;
  }, [normalizedDayData, dayTimeRange, dayAvgVolume, usePrecomputedMode, computeChartDataAndSegments]);

  // 為夜盤預先計算（支持增量更新）
  const nightChartResult = useMemo(() => {
    if (!usePrecomputedMode) return { chartData: [], lineSegments: [] };
    
    const prev = nightChartRef.current;
    
    // 如果數據長度沒變，直接返回上次結果（避免不必要的重新計算）
    if (prev && prev.normalizedData.length === normalizedNightData.length) {
      return { chartData: prev.chartData, lineSegments: prev.lineSegments };
    }
    
    const canIncremental = prev && 
      prev.normalizedData.length > 0 &&
      normalizedNightData.length > prev.normalizedData.length &&
      normalizedNightData.length - prev.normalizedData.length <= 2;
    
    if (canIncremental) {
      // console.log('[夜盤] 增量更新，新增', normalizedNightData.length - prev!.normalizedData.length, '筆');
      // 複製前一次的結果
      const chart = [...prev!.chartData];
      const segments = [...prev!.lineSegments];
      
      // 只處理新增的資料點
      const newPoints = normalizedNightData.slice(prev!.normalizedData.length);
      
      newPoints.forEach(point => {
        const timeIndex = nightTimeRange.indexOf(point.time);
        if (timeIndex >= 0) {
          const volumeRatio = point.volume / nightAvgVolume;
          const color = getVolumeColor(volumeRatio);
          chart[timeIndex] = {
            ...point,
            color
          };
          
          // 檢查是否需要新增線段（與前一個點連接）
          if (timeIndex > 0 && chart[timeIndex - 1].avg_price !== null) {
            const prevColor = chart[timeIndex - 1].color;
            const lastSeg = segments[segments.length - 1];
            
            // 如果與最後一個線段同色，延伸該線段
            if (lastSeg && lastSeg.color === prevColor) {
              const lastDataKey = lastSeg.dataKey;
              (chart[timeIndex] as any)[lastDataKey] = point.avg_price;
            } else {
              // 否則建立新線段
              const newDataKey = `merged_${segments.length}`;
              (chart[timeIndex - 1] as any)[newDataKey] = chart[timeIndex - 1].avg_price;
              (chart[timeIndex] as any)[newDataKey] = point.avg_price;
              segments.push({ dataKey: newDataKey, color: prevColor });
            }
          }
        }
      });
      
      const result = { chartData: chart, lineSegments: segments };
      nightChartRef.current = {
        normalizedData: normalizedNightData,
        chartData: chart,
        lineSegments: segments
      };
      return result;
    }
    
    // 完整計算
    // console.log('[夜盤] 完整計算，共', normalizedNightData.length, '筆資料');
    const result = computeChartDataAndSegments(normalizedNightData, nightTimeRange, nightAvgVolume);
    nightChartRef.current = {
      normalizedData: normalizedNightData,
      chartData: result.chartData,
      lineSegments: result.lineSegments
    };
    return result;
  }, [normalizedNightData, nightTimeRange, nightAvgVolume, usePrecomputedMode, computeChartDataAndSegments]);

  // 使用 useRef 保存上一次的資料和計算結果（單一數據集模式的增量更新）
  const prevDataRef = useRef<{
    normalizedData: MinuteChartPoint[];
    fullTimeRange: string[];
    avgVolume: number;
    chartData: any[];
    lineSegments: Array<{ dataKey: string; color: string }>;
  } | null>(null);

  // 最終的 chartData 和 lineSegments
  const { chartData, lineSegments } = useMemo(() => {
    // 預先計算模式：直接返回對應的結果（不重新計算）
    if (usePrecomputedMode) {
      const result = marketType === 'regular' ? dayChartResult : nightChartResult;
      // console.log(`[使用] ${marketType === 'regular' ? '日盤' : '夜盤'} 預計算結果:`, result.lineSegments.length, '個線段');
      return result;
    }

    // 單一數據集模式：支持增量更新
    const prev = prevDataRef.current;
    
    const canIncrementalUpdate = prev &&
      prev.fullTimeRange === fullTimeRange &&
      normalizedData.length > 0 &&
      prev.normalizedData.length > 0 &&
      normalizedData.length - prev.normalizedData.length <= 2 &&
      normalizedData.length >= prev.normalizedData.length;
    
    if (canIncrementalUpdate) {
      // 增量更新：只更新最後變化的部分
      const chart = [...prev.chartData];
      const segments = [...prev.lineSegments];
      
      // 找出需要更新的時間範圍（最後幾筆資料）
      const updateStartIndex = Math.max(0, prev.normalizedData.length - 2);
      const newDataItems = normalizedData.slice(updateStartIndex);
      
      // 更新受影響的 chartData 點
      newDataItems.forEach(dataPoint => {
        const timeIndex = fullTimeRange.indexOf(dataPoint.time);
        if (timeIndex >= 0) {
          const volumeRatio = dataPoint.volume / avgVolume;
          const color = getVolumeColor(volumeRatio);
          chart[timeIndex] = {
            ...dataPoint,
            color
          };
        }
      });
      
      // 移除受影響的舊線段（最後2個線段可能需要重繪）
      const removeCount = Math.min(2, segments.length);
      if (removeCount > 0) {
        segments.splice(segments.length - removeCount, removeCount);
      }
      
      // 找出需要重新生成線段的起始位置
      const segmentStartIndex = Math.max(0, prev.normalizedData.length - 3);
      let segmentIndex = segments.length;
      
      // 重新生成受影響的線段
      for (let i = segmentStartIndex; i < chart.length - 1; i++) {
        const current = chart[i];
        const next = chart[i + 1];
        
        if (current.avg_price !== null && next.avg_price !== null) {
          const dataKey = `segment_${segmentIndex}`;
          
          // 清除舊的 dataKey（如果存在）
          delete (chart[i] as any)[dataKey];
          delete (chart[i + 1] as any)[dataKey];
          
          // 添加新的 dataKey
          (chart[i] as any)[dataKey] = current.avg_price;
          (chart[i + 1] as any)[dataKey] = next.avg_price;
          
          segments.push({
            dataKey,
            color: current.color
          });
          
          segmentIndex++;
        }
      }
      
      // 保存結果到 ref
      prevDataRef.current = {
        normalizedData,
        fullTimeRange,
        avgVolume,
        chartData: chart,
        lineSegments: segments
      };
      
      return { chartData: chart, lineSegments: segments };
    }
    
    // 完整計算：使用共用函數
    const result = computeChartDataAndSegments(normalizedData, fullTimeRange, avgVolume);
    
    // 保存結果到 ref
    prevDataRef.current = {
      normalizedData,
      fullTimeRange,
      avgVolume,
      chartData: result.chartData,
      lineSegments: result.lineSegments
    };

    return result;
  }, [normalizedData, fullTimeRange, avgVolume, usePrecomputedMode, marketType, dayChartResult, nightChartResult, computeChartDataAndSegments]);

  // 生成整點刻度（用於橫軸標籤）
  const hourTicks = useMemo(() => {
    if (marketType === 'regular') {
      // 日盤：08-13（整點）
      return ['08:00', '09:00', '10:00', '11:00', '12:00', '13:00'];
    } else {
      // 夜盤：15-05（整點，跨日）
      return ['15:00', '16:00', '17:00', '18:00', '19:00', '20:00', '21:00', '22:00', '23:00', '00:00', '01:00', '02:00', '03:00', '04:00', '05:00'];
    }
  }, [marketType]);

  // 計算價格資料
  const prices = hasData ? normalizedData.flatMap(d => [d.avg_price, d.high, d.low]) : [20000, 22000];
  
  // 計算 Y 軸範圍和刻度（以基準價為中心，1% 為間隔）
  let yAxisDomain: [number, number];
  let yAxisTicks: number[];
  
  if (referencePrice && referencePrice > 0 && hasData) {
    // 使用基準價計算 Y 軸
    const onePercent = referencePrice * 0.01; // 基準價的 1%
    const dataMin = Math.min(...prices);
    const dataMax = Math.max(...prices);
    
    // 初始刻度範圍：±1%（刻度只顯示到 ±1%）
    let rangeStepsAbove = 1;
    let rangeStepsBelow = 1;
    
    // 檢查數據是否超出 ±1% 範圍，單向擴增到整數百分比
    const rangeAbove = (dataMax - referencePrice) / onePercent;
    const rangeBelow = (referencePrice - dataMin) / onePercent;
    
    // 如果數據超出 ±1%，單向擴增到達到的整數百分比
    if (rangeAbove > 1) {
      rangeStepsAbove = Math.ceil(rangeAbove);
    }
    if (rangeBelow > 1) {
      rangeStepsBelow = Math.ceil(rangeBelow);
    }
    
    // 生成 Y 軸刻度（基準價在中間，從 -rangeStepsBelow 到 +rangeStepsAbove）
    yAxisTicks = [];
    for (let i = -rangeStepsBelow; i <= rangeStepsAbove; i++) {
      yAxisTicks.push(referencePrice + i * onePercent);
    }
    
    // Y 軸實際顯示範圍：比刻度多 0.5%
    yAxisDomain = [
      referencePrice - (rangeStepsBelow + 0.5) * onePercent,
      referencePrice + (rangeStepsAbove + 0.5) * onePercent
    ];
  } else {
    // 無基準價時，使用原本的自動範圍
    const minPrice = hasData ? Math.floor(Math.min(...prices) * 0.999) : 20000;
    const maxPrice = hasData ? Math.ceil(Math.max(...prices) * 1.001) : 22000;
    yAxisDomain = [minPrice, maxPrice];
    yAxisTicks = [];
  }

  // 計算成交量最大值
  const maxVolume = hasData ? Math.max(...normalizedData.map(d => d.volume)) : 1000;

  // 找出當前盤面的最高價和最低價的位置（標記在平均價線上）
  let highestPoint: { time: string; price: number } | null = null;
  let lowestPoint: { time: string; price: number } | null = null;
  if (hasData && normalizedData.length > 0) {
    const highestPrice = Math.max(...normalizedData.map(d => d.high));
    const lowestPrice = Math.min(...normalizedData.map(d => d.low));
    const highPoint = normalizedData.find(d => d.high === highestPrice);
    const lowPoint = normalizedData.find(d => d.low === lowestPrice);
    
    if (highPoint) {
      highestPoint = { time: highPoint.time, price: highestPrice };
    }
    if (lowPoint) {
      lowestPoint = { time: lowPoint.time, price: lowestPrice };
    }
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-semibold text-gray-800 dark:text-gray-100">{title}</h3>
        <div className="flex items-center gap-3">
          {!isLoading && hasTaiex && (
            <label className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400 cursor-pointer hover:text-gray-800 dark:hover:text-gray-100 transition-colors">
              <input
                type="checkbox"
                checked={showTaiex}
                onChange={(e) => setShowTaiex(e.target.checked)}
                className="w-3.5 h-3.5 text-blue-600 rounded border-gray-300 focus:ring-2 focus:ring-blue-500 focus:ring-offset-0 cursor-pointer"
              />
              <span>加權指數</span>
            </label>
          )}
          {!isLoading && (
            <label className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400 cursor-pointer hover:text-gray-800 dark:hover:text-gray-100 transition-colors">
              <input
                type="checkbox"
                checked={showHighLow}
                onChange={(e) => setShowHighLow(e.target.checked)}
                className="w-3.5 h-3.5 text-blue-600 rounded border-gray-300 focus:ring-2 focus:ring-blue-500 focus:ring-offset-0 cursor-pointer"
              />
              <span>區間高低價</span>
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
          
          {/* 左側 Y 軸：價格（以基準價為中心，1% 為間隔，基準以上紅色，以下綠色） */}
          <YAxis 
            yAxisId="price"
            type="number"
            domain={yAxisDomain}
            ticks={yAxisTicks.length > 0 ? yAxisTicks : undefined}
            tick={(props) => {
              const { x, y, payload } = props;
              const value = payload.value;
              // 基準以上顯示紅色，基準以下顯示綠色，基準本身顯示黑色
              let color = '#6b7280'; // 預設灰色
              if (referencePrice && referencePrice > 0) {
                if (value > referencePrice) {
                  color = '#ef4444'; // 紅色
                } else if (value < referencePrice) {
                  color = '#22c55e'; // 綠色
                } else {
                  color = '#1f2937'; // 黑色（基準價）
                }
              }
              return (
                <text 
                  x={x} 
                  y={y} 
                  dx={-5} 
                  dy={4} 
                  textAnchor="end" 
                  fontSize={11} 
                  fill={color}
                >
                  {value.toFixed(0)}
                </text>
              );
            }}
            tickLine={false}
            axisLine={{ stroke: '#e5e7eb' }}
            width={60}
            allowDataOverflow={false}
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
            payload={legendPayload}
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
              name="區間高低價"
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
              name="區間高低價"
              opacity={0.6}
              connectNulls={false}
            />
          )}
          
          {/* 平均價線（多段線，每段根據該分鐘的成交量顯示不同顏色） */}
          {lineSegments.map((segment, index) => (
            <Line 
              key={segment.dataKey}
              yAxisId="price"
              type="monotone" 
              dataKey={segment.dataKey}
              stroke={segment.color}
              strokeWidth={2}
              dot={false}
              activeDot={false}
              hide={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
          
          {/* 加權指數線（淺黃色細線，僅日盤有資料時顯示，盤前不顯示） */}
          {hasTaiex && showTaiex && (
            <Line 
              yAxisId="price"
              type="monotone" 
              dataKey="taiex"
              stroke="#fde68a"
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 4 }}
              name="加權指數"
              connectNulls={false}
              isAnimationActive={false}
            />
          )}
          
          {/* 標記最高價位置 */}
          {highestPoint && referencePrice && (
            <ReferenceDot
              x={highestPoint.time}
              y={highestPoint.price}
              yAxisId="price"
              r={0}
              fill="transparent"
              stroke="transparent"
              strokeWidth={0}
              label={{
                value: highestPoint.price.toFixed(0),
                position: 'top',
                fill: '#374151',
                fontSize: 11,
                fontWeight: 400,
                offset: 5
              }}
            />
          )}
          
          {/* 標記最低價位置 */}
          {lowestPoint && referencePrice && (
            <ReferenceDot
              x={lowestPoint.time}
              y={lowestPoint.price}
              yAxisId="price"
              r={0}
              fill="transparent"
              stroke="transparent"
              strokeWidth={0}
              label={{
                value: lowestPoint.price.toFixed(0),
                position: 'bottom',
                fill: '#374151',
                fontSize: 11,
                fontWeight: 400,
                offset: 5
              }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

export default memo(MinuteChart);
