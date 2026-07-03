'use client';

/**
 * 即時報價卡片元件
 * 顯示 WebSocket 每秒更新的報價資訊
 */

interface RealtimePrice {
  /** 商品代碼 */
  code: string;
  /** 價格 */
  price: number;
  /** 加權指數（現貨價格） */
  underlying_price?: number;
  /** 每秒成交量 */
  volume?: number;
}

interface RealtimeQuoteCardProps {
  /** 報價資料 */
  price: RealtimePrice | null;
  /** 是否連線中 */
  isConnected: boolean;
  /** 參考價格（用於計算漲跌幅） */
  referencePrice?: number | null;
}

/**
 * 格式化數字顯示
 */
function formatNumber(value?: number): string {
  if (value == null) return '--';
  return value.toLocaleString('zh-TW');
}

/**
 * 計算成交量顏色（0-200 範圍，台指風格：數值越高越紅）
 */
function getVolumeColor(volume: number): string {
  // 限制範圍在 0-200
  const clampedVolume = Math.min(Math.max(volume, 0), 200);
  const ratio = clampedVolume / 200;

  // 根據比例決定顏色：
  // 0-50: 綠色系 (低量)
  // 50-100: 黃色系 (中量)
  // 100-150: 橙色系 (高量)
  // 150-200: 紅色系 (超高量)
  
  if (ratio < 0.25) {
    // 0-25%: 淺綠到綠
    return 'bg-green-400';
  } else if (ratio < 0.5) {
    // 25-50%: 綠到黃綠
    return 'bg-lime-400';
  } else if (ratio < 0.75) {
    // 50-75%: 黃到橙
    return 'bg-yellow-400';
  } else if (ratio < 0.9) {
    // 75-90%: 橙到橙紅
    return 'bg-orange-500';
  } else {
    // 90-100%: 紅色系
    return 'bg-red-600';
  }
}

export default function RealtimeQuoteCard({ price, isConnected, referencePrice }: RealtimeQuoteCardProps) {
  // 計算漲跌
  const change = price?.price != null && referencePrice != null
    ? price.price - referencePrice
    : null;
  
  // 計算漲跌幅
  const changePercent = change != null && referencePrice != null && referencePrice !== 0
    ? (change / referencePrice) * 100
    : null;
  
  // 判斷漲跌方向
  const isPositive = change != null && change >= 0;
  
  // 台灣風格：紅漲綠跌
  const changeColor = change != null
    ? (isPositive ? 'text-red-600' : 'text-green-600')
    : 'text-gray-600';
  const bgColor = change != null
    ? (isPositive ? 'bg-red-50' : 'bg-green-50')
    : 'bg-gray-50';
  
  // 計算期現價差（期貨價格 - 現貨價格）
  const basis = price?.underlying_price != null && price?.price != null
    ? price.price - price.underlying_price
    : null;

  // 價差信號
  const basisSignal = basis != null 
    ? (basis > 0 ? '正價差' : basis < 0 ? '逆價差' : '平價')
    : '--';

  // 價差顏色（台灣風格：紅漲綠跌）
  const basisColor = basis != null
    ? (basis > 0 ? 'text-red-600' : basis < 0 ? 'text-green-600' : 'text-gray-600')
    : 'text-gray-400';

  // 成交量顯示值（限制在 0-200）
  const displayVolume = price?.volume != null ? Math.min(price.volume, 200) : 0;
  const volumeWidth = (displayVolume / 200) * 100;

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      {/* 標題 */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-gray-800">
            即時報價 {price?.code || 'MXF'}
          </h2>
          <p className="text-xs text-gray-500">
            每秒更新
          </p>
        </div>
        <div className={`px-3 py-1 rounded-full ${bgColor}`}>
          <span className={`text-sm font-medium ${changeColor}`}>
            {change != null ? (isPositive ? '▲' : '▼') : '--'}
          </span>
        </div>
      </div>

      {price ? (
        <>
          {/* 主要報價 */}
          <div className="mb-4">
            <div className="flex items-baseline gap-3">
              <span className={`text-3xl font-bold ${changeColor}`}>
                {formatNumber(price.price)}
              </span>
              <div className="flex flex-col">
                <span className={`text-base font-semibold ${changeColor}`}>
                  {change != null ? `${isPositive ? '+' : ''}${change.toFixed(0)}` : '--'}
                </span>
                <span className={`text-sm ${changeColor}`}>
                  {changePercent != null ? `${isPositive ? '+' : ''}${changePercent.toFixed(2)}%` : '--'}
                </span>
              </div>
            </div>
          </div>

          {/* 每秒成交量 */}
          <div className="mb-4 flex items-center gap-2">
            <span className="text-xs text-gray-500 whitespace-nowrap">每秒成交量:</span>
            <div className="flex-1 relative h-6 bg-gray-100 rounded-full overflow-hidden">
              <div 
                className={`h-full transition-all duration-300 ${getVolumeColor(displayVolume)}`}
                style={{ width: `${volumeWidth}%` }}
              />
              <div className="absolute inset-0 flex items-center justify-end px-2 text-xs text-gray-400 pointer-events-none">
                <span>200</span>
              </div>
            </div>
          </div>

          {/* 期現價差 */}
          <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-200">
            <div>
              <p className="text-xs text-gray-500 mb-1">期現價差</p>
              <p className={`text-lg font-semibold ${basisColor}`}>
                {basis != null ? `${basis > 0 ? '+' : ''}${basis.toFixed(0)}` : '--'}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500 mb-1">價差信號</p>
              <p className={`text-lg font-semibold ${basisColor}`}>
                {basisSignal}
              </p>
            </div>
          </div>
        </>
      ) : (
        <div className="py-8 text-center">
          <p className="text-sm text-gray-400">
            {isConnected ? '等待報價資料...' : '未連線到報價伺服器'}
          </p>
        </div>
      )}

      {/* 更新時間與連線狀態 */}
      <div className="mt-4 pt-4 border-t border-gray-200 flex items-center justify-between">
        <p className="text-xs text-gray-500">
          更新頻率：每秒
        </p>
        <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-gray-300'}`} 
             title={isConnected ? '已連線' : '未連線'} />
      </div>
    </div>
  );
}
