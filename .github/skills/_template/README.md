# 模板結構說明

此文檔說明如何使用 Skill 模板建立新的 Skill。

## 檔案結構

```
skills/_template/
├── SKILL.md              # ✅ 必要：主設定、觸發時機、工具、執行流程
├── reference.md          # 📌 如果需要：補充參考、專有名詞、填寫範例
├── template/             # 📦 如果需要：輸出模板（需要固定格式時）
│   └── README.md
├── scripts/              # 🔧 程式碼檔案（所有邏輯都在這裡）
│   ├── types.ts          # 類型定義
│   ├── execute.ts        # 核心執行邏輯
│   ├── execute.test.ts   # 執行邏輯測試
│   ├── index.ts          # ✅ 主入口點（呼叫 execute）
│   └── index.test.ts     # scripts 整合測試
└── README.md             # 此說明文檔
```

## 開發步驟

### 1️⃣ 複製模板

```bash
cp -r skills/_template skills/my-skill
cd skills/my-skill
```

### 2️⃣ 編輯 SKILL.md（必要）

在 `SKILL.md` 中定義：
- **基本資訊**: Skill ID、版本
- **功能說明**: 一句話描述、詳細功能
- **觸發時機**: 自動/手動/定時/事件驅動
- **相依工具**: 列出所有依賴
- **執行流程**: 圖表和詳細步驟
- **輸入輸出**: 參數表和結果表
- **錯誤處理**: 錯誤碼對應表

### 3️⃣ 定義類型 (scripts/types.ts)

更新 `[SkillName]Input` 和 `[SkillName]Output` 介面。

### 4️⃣ 實現邏輯 (scripts/execute.ts)

在 `scripts/execute.ts` 中實現：
- `validateInput()` - 驗證輸入
- `checkPreconditions()` - 檢查前置條件
- `executeCore()` - 核心邏輯
- `execute()` - 主執行函數

### 5️⃣ 編寫測試

在 `scripts/execute.test.ts` 編寫單元測試覆蓋：
- 驗證邏輯測試
- 前置條件檢查
- 執行邏輯測試
- 錯誤處理

在 `scripts/index.test.ts` 編寫主入口整合測試。

### 6️⃣ 補充文檔（如需要）

根據需要建立：
- **reference.md** - 專有名詞、範本、常見問題
- **template/** - 輸出模板檔案

### 7️⃣ 更新 manifest.ts

在 `skills/manifest.ts` 中註冊此 skill：

```typescript
'my-skill': {
  name: 'My Skill',
  description: 'Skill 描述',
  handler: () => import('./my-skill/scripts/index.js'),
  inputs: { ... },
  outputs: { ... }
}
```

## 檔案用途

| 檔案 | 用途 | 必要性 |
|------|------|--------|
| SKILL.md | 主設定、觸發時機、執行流程 | ✅ 必要 |
| reference.md | 補充參考、專有名詞、範例 | 📌 可選 |
| template/ | 輸出模板 | 📦 可選 |
| scripts/ | 執行過程程式碼 | ✅ 必要 |
| scripts/types.ts | 類型定義 | ✅ 必要 |
| scripts/execute.ts | 核心執行邏輯 | ✅ 必要 |
| scripts/execute.test.ts | 執行邏輯測試 | ✅ 必要 |
| scripts/index.ts | 主入口點 | ✅ 必要 |
| scripts/index.test.ts | 主入口整合測試 | ✅ 必要 |

## 命名規範

- **Folder**: `kebab-case` (例如 `my-skill`)
- **Files**: `kebab-case.ts` (例如 `execute.ts`)
- **Functions**: `camelCase` (例如 `mySkill()`)
- **Types**: `PascalCase` (例如 `MySkillInput`)

## 快速檢查清單

- [ ] SKILL.md 完整填寫
- [ ] scripts/types.ts 定義 Input/Output Interface
- [ ] scripts/execute.ts 實現所有函數
- [ ] scripts/execute.test.ts 編寫完整測試
- [ ] scripts/index.ts 正確匯入 execute
- [ ] scripts/index.test.ts 編寫整合測試
- [ ] 需要時建立 reference.md
- [ ] 需要時建立 template/ 目錄
- [ ] skills/manifest.ts 中註冊
- [ ] pnpm test 確保所有測試通過
