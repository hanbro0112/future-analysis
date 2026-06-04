# Future Analysis - 前端應用專案

這是一個使用 Next.js + TypeScript + Firestore 建構的前端應用專案。

## 📋 專案說明

本專案採用現代化的前端技術棧，直接從前端連接 Firestore 資料庫，提供快速、型別安全的開發體驗。

### 技術架構

- **框架**: Next.js 15+ (App Router)
- **語言**: TypeScript (嚴格模式)
- **UI 函式庫**: React.js
- **資料庫**: Firebase Firestore
- **樣式**: Tailwind CSS
- **測試**: Jest + React Testing Library

### 專案特色

- ✅ 完整的 TypeScript 型別定義（禁止使用 `any`）
- ✅ 繁體中文註解，易於閱讀和維護
- ✅ Clean Architecture 架構設計
- ✅ 函數式程式設計模式
- ✅ 完整的錯誤處理機制
- ✅ Firestore 即時資料同步

---

## 🚀 快速開始

### 1. 安裝依賴

```bash
pnpm install
```

### 2. 配置環境變數

建立 `.env.local` 檔案並填入 Firebase 配置：

```bash
# Firebase 配置
NEXT_PUBLIC_FIREBASE_API_KEY=your-api-key
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your-project-id
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=your-project.appspot.com
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=your-sender-id
NEXT_PUBLIC_FIREBASE_APP_ID=your-app-id
```

> **注意**: `.env.local` 已加入 `.gitignore`，請勿將此檔案提交到版本控制。

### 3. 啟動開發伺服器

```bash
pnpm dev
```

開啟瀏覽器訪問 [http://localhost:3000](http://localhost:3000) 查看結果。

---

## 📁 專案結構

```
web/
├── app/                      # Next.js App Router 頁面
│   ├── (routes)/            # 路由群組
│   ├── api/                 # API Routes（可選）
│   ├── layout.tsx           # 根佈局
│   ├── page.tsx             # 首頁
│   └── globals.css          # 全域樣式
├── components/              # React 元件
│   ├── ui/                  # 基礎 UI 元件
│   └── features/            # 功能性元件
├── lib/                     # 工具函式和共用邏輯
│   ├── firebase/            # Firebase 相關
│   │   ├── config.ts        # Firebase 初始化配置
│   │   ├── firestore.ts     # Firestore CRUD 工具函式
│   │   └── collections.ts   # Collection 名稱定義
│   ├── hooks/               # 自訂 React Hooks
│   └── utils/               # 通用工具函式
├── types/                   # TypeScript 型別定義
│   ├── user.ts              # 使用者相關型別
│   └── index.ts             # 匯出所有型別
├── public/                  # 靜態資源
├── AGENTS.md                # 開發規範文件
└── README.md                # 本文件
```

---

## 🔧 Firebase Firestore 設定

### 取得 Firebase 配置

1. 前往 [Firebase Console](https://console.firebase.google.com/)
2. 建立新專案或選擇現有專案
3. 進入「專案設定」→「一般」
4. 在「您的應用程式」區塊新增網頁應用程式
5. 複製 Firebase 配置並填入 `.env.local`

### 設定 Firestore 安全規則

在 Firebase Console 中設定 Firestore 規則（範例）：

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // 允許已驗證使用者讀取和寫入自己的資料
    match /users/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
  }
}
```

### 初始化 Firestore

專案已包含 Firestore 配置範例，請參考 `lib/firebase/config.ts`。

---

## 💻 開發規範

完整的開發規範請參閱 [AGENTS.md](./AGENTS.md)，包含：

- 📝 命名規範（元件、函式、型別）
- 🏗️ 架構原則（檔案結構、程式碼規範）
- 🔥 Firestore 使用模式（CRUD 操作、即時監聽）
- 📖 註解規範（繁體中文註解）
- 🧪 測試規範（Jest 測試案例）
- ✅ 最佳實踐檢查清單

### 核心原則

1. **禁止使用 `any` 型別** - 必須明確定義所有型別
2. **繁體中文註解** - 所有函式和複雜邏輯都要加上繁體中文說明
3. **錯誤處理** - 所有 API 調用必須包含 try-catch
4. **測試覆蓋** - 每個新功能都應撰寫對應的測試案例
5. **函數式程式設計** - 優先使用純函式和不可變資料

---

## 🧪 測試

執行測試：

```bash
# 執行所有測試
pnpm test

# 執行測試並生成覆蓋率報告
pnpm test:coverage

# 監聽模式（開發時使用）
pnpm test:watch
```

---

## 📦 建置與部署

### 建置正式版本

```bash
pnpm build
```

### 本地預覽正式版本

```bash
pnpm start
```

### 部署到 Vercel

最簡單的部署方式是使用 [Vercel Platform](https://vercel.com/new)：

1. 將專案推送到 GitHub
2. 在 Vercel 匯入專案
3. 設定環境變數（與 `.env.local` 相同）
4. 部署完成

詳細說明請參考 [Next.js 部署文件](https://nextjs.org/docs/app/building-your-application/deploying)。

---

## 📚 學習資源

- [Next.js 官方文件](https://nextjs.org/docs) - 學習 Next.js 功能和 API
- [React 官方文件](https://react.dev) - 學習 React 基礎
- [TypeScript 手冊](https://www.typescriptlang.org/docs) - TypeScript 型別系統
- [Firebase Firestore 文件](https://firebase.google.com/docs/firestore) - Firestore 使用指南
- [Tailwind CSS 文件](https://tailwindcss.com/docs) - Tailwind 樣式工具

---

## 🤝 貢獻指南

1. Fork 本專案
2. 建立功能分支 (`git checkout -b feature/amazing-feature`)
3. 遵循 [AGENTS.md](./AGENTS.md) 中的開發規範
4. 提交變更 (`git commit -m 'feat: add amazing feature'`)
5. 推送到分支 (`git push origin feature/amazing-feature`)
6. 開啟 Pull Request

### Commit 訊息規範

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```
feat: 新增功能
fix: 修復錯誤
docs: 文件變更
style: 程式碼格式調整
refactor: 重構程式碼
test: 新增測試
chore: 雜項變更
```

---

## 📄 授權

MIT License

---

## 🙋 問題回報

如有任何問題或建議，請開啟 Issue 或聯繫專案維護者。
