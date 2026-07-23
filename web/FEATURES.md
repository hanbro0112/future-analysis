# 期貨資訊分析網頁

## 功能特色

### 1. 台指期即時走勢（上半部）
- 即時報價卡片：顯示當前價格、漲跌、OHLC、成交量
- 即時走勢圖：每 3 秒更新一次，顯示最近 60 個價格點

### 2. 分鐘級走勢與分析（下半部）
- **分鐘級線路圖**
  - 平均價格折線圖（藍色主線）
  - 最高價與最低價淡色線（綠色/紅色虛線）
  - 成交量柱狀圖背景
  - 自訂 tooltip 顯示完整資訊（價格、成交量、買賣量）

- **多空分析表格**
  - 綜合信號（強多/偏多/中性/偏空/強空）
  - 多空比例視覺化長條圖
  - 市場情緒指標
  - 成交量狀態
  - 期現價差分析

### 3. 智慧盤面選擇
- **自動判斷預設盤面**
  - 根據當前時間自動選擇日盤或夜盤
  - 日盤時段（週一至週五 08:45-13:45）=> 預設顯示日盤
  - 夜盤時段（週一至週五 15:00-次日 05:00）=> 預設顯示夜盤
  - 週六、週日全天 => 預設顯示夜盤
  - 其他時間（盤前、午休）=> 預設顯示夜盤

- **手動切換功能**
  - 提供「日盤」/「夜盤」切換按鈕
  - 切換後立即更新圖表和分析資料
  - 保持使用者選擇，不受自動更新影響

## 資料更新邏輯

1. **首次載入**：從 Firestore 載入今日所有分鐘級資料
2. **定期更新**：每分鐘 03 秒自動更新一次（考慮資料延遲）
3. **資料來源**：Firestore 路徑 `market/MXF/{YYYYMMDD}/{HHmm}`

## 環境配置

### 1. 複製環境變數範本
```bash
cp .env.example .env.local
```

### 2. 設定 Firebase 配置
編輯 `.env.local`，填入你的 Firebase 專案資訊：
```env
NEXT_PUBLIC_FIREBASE_API_KEY=your-api-key
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your-project-id
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=your-project.firebasestorage.app
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=your-sender-id
NEXT_PUBLIC_FIREBASE_APP_ID=your-app-id
```

### 3. 使用 Firebase Emulator（本地開發）
如果要使用 Firestore Emulator：
```env
NEXT_PUBLIC_USE_FIREBASE_EMULATOR=true
```

確保 Firestore Emulator 在 `localhost:8080` 運行。

## 執行專案

### 安裝依賴
```bash
pnpm install
```

### 開發模式
```bash
pnpm dev
```

開啟瀏覽器訪問 `http://localhost:3000`

### 建置生產版本
```bash
pnpm build
pnpm start
```

## 技術架構

### 前端框架
- **Next.js 15** (App Router)
- **React 19**
- **TypeScript** (strict mode)

### UI 與圖表
- **Tailwind CSS**：樣式框架
- **Recharts**：圖表庫（折線圖、柱狀圖、組合圖）

### 資料層
- **Firebase/Firestore**：即時資料庫
- 支援 Firestore Emulator 本地開發

## 檔案結構

```
web/
├── app/
│   ├── components/
│   │   ├── FuturesChart.tsx       # 台指期即時走勢圖
│   │   ├── QuoteCard.tsx          # 即時報價卡片
│   │   ├── MinuteChart.tsx        # 分鐘級線路圖（新增）
│   ├── lib/
│   │   ├── firebase.ts            # Firebase 初始化（新增）
│   │   ├── firestoreApi.ts        # Firestore 資料存取（新增）
│   │   └── mockData.ts            # 模擬資料生成
│   ├── types/
│   │   ├── futures.ts             # 期貨資料類型
│   │   └── minuteData.ts          # 分鐘級資料類型（新增）
│   ├── globals.css
│   ├── layout.tsx
│   └── page.tsx                   # 主頁面
├── .env.example                   # 環境變數範本（新增）
├── package.json
└── tailwind.config.ts
```

## 資料格式

### MinuteBar（分鐘級資料）
```typescript
{
  code: string              // 商品代碼 (MXF)
  timestamp: string         // 時間戳記
  date: string             // 日期 YYYY-MM-DD
  time: string             // 時間 HH:mm
  market_type: string      // 'regular' | 'after_hours'
  open: number             // 開盤價
  high: number             // 最高價
  low: number              // 最低價
  close: number            // 收盤價
  volume: number           // 成交量
  buy_volume: number       // 買方成交量
  sell_volume: number      // 賣方成交量
  avg_price: number        // 平均價格
  analysis?: {             // 分析結果（可選）
    signal: string         // 多空信號
    long_ratio: number     // 多方比例
    short_ratio: number    // 空方比例
    confidence: number     // 信心水準
    // ... 更多分析指標
  }
}
```

## 開發注意事項

1. **Firestore 安全規則**：確保 Firestore 規則允許讀取 `market` 集合
2. **資料延遲**：分鐘級資料在每分鐘 03 秒更新，給予後端 3 秒處理時間
3. **效能優化**：只查詢當日資料，避免載入過多歷史資料
4. **錯誤處理**：所有 Firestore 操作都有 try-catch 錯誤處理

## 未來改進方向

- [ ] 支援多商品切換（不只台指期）
- [ ] 歷史資料回放功能
- [ ] 更多技術指標（KD、MACD 等）
- [ ] 即時警示通知
- [ ] 響應式優化（手機版）
