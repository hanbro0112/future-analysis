# Auto Commit Skill

自動生成並提交符合 Conventional Commits 規範的 Git 提交訊息。

## ⚠️ 重要提醒

1. **優先使用原生 `git commit` 命令**：如果可以直接使用，請不要依賴此 skill
2. **body 為必填項**：所有 commit 必須包含詳細的改動說明
3. **body 使用條列式格式**：使用 `- 改動項目` 格式

## 快速開始

```typescript
import { autoCommit } from './skills/auto-commit/scripts/index.js'

// ✅ 正確：包含必填的 body
const result = await autoCommit({
  type: 'feat',
  description: '新增用戶認證功能',
  body: '- 整合 Firebase Auth\n- 新增 OAuth 登入流程\n- 加入 JWT token 驗證'
})

if (result.success) {
  console.log(`✅ 提交成功: ${result.commitHash}`)
} else {
  console.error(`❌ 提交失敗: ${result.error}`)
}
```

## 檔案結構

```
skills/auto-commit/
├── SKILL.md              # 主設定、執行流程、錯誤碼表
├── reference.md          # Conventional Commits 規範參考
├── scripts/              # 所有程式碼
│   ├── types.ts          # 類型定義
│   ├── index.ts          # 主入口點
│   ├── execute.ts        # 執行邏輯
│   ├── execute.test.ts   # 邏輯測試
│   └── index.test.ts     # 整合測試
├── types.ts              # 向後相容（重新匯出 scripts/types）
├── index.ts              # 向後相容（重新匯出 scripts/index）
└── README.md             # 此文檔
```

## 核心功能

- ✅ 遵循 Conventional Commits 規範
- ✅ 支援 9 種提交類型 (feat, fix, docs, style, refactor, perf, test, chore, ci)
- ✅ 支援提交範疇 (scope)
- ✅ **強制要求 body（詳細說明）**：必須使用條列式格式
- ✅ 支援 Breaking Changes 和 Issue 鏈接
- ✅ 完整的錯誤碼系統 (E001-E007)
- ✅ 前置條件檢查（Git 可用、在儲存庫中、有暫存變更）
- ✅ **description 和 body 之間空一行**
- ✅ **body 內條目之間不空行**：直接換行即可

## 提交訊息格式規範

### 基本格式

```
<type>(<scope>): <description>
<body>

BREAKING CHANGE: <breaking>

Closes <issues>
```

### 規則

1. **description 和 body 之間空一行**
2. **body 內條目之間不空行**：直接換行即可
3. **BREAKING CHANGE 和 Closes 前要空行**：用於區隔特殊標記
4. **條目使用 `-` 開頭**：清單格式

### 範例

```
feat(auth): 新增 OAuth 登入

- 支援 Google OAuth
- 支援 GitHub OAuth
- 添加 JWT token 驗證

BREAKING CHANGE: 舊的 token 端點已移除

Closes #123, #456
```

## 使用場景

### 基本提交（必須包含 body）

```typescript
await autoCommit({
  type: 'feat',
  description: '新增用戶認證',
  body: '- 整合 Firebase Auth\n- 新增登入頁面\n- 加入密碼加密'
})
```

### 帶範疇的提交

```typescript
await autoCommit({
  type: 'fix',
  scope: 'auth',
  description: '修復登入驗證',
  body: '- 修正 token 過期判斷邏輯\n- 加入重新登入提示\n- 優化錯誤訊息顯示'
})
```

### 完整提交（含 Breaking Changes）

```typescript
await autoCommit({
  type: 'feat',
  scope: 'api',
  description: '重構 API 認證',
  body: '- 使用 Bearer token 替代 API key\n- 新增 token 刷新機制\n- 加入 rate limiting',
  breaking: 'API key 認證已棄用，必須遷移至 Bearer token',
  issues: ['#123', '#456']
})
```

## 運行測試

```bash
# 執行所有測試
pnpm test -- skills/auto-commit/

# 執行邏輯測試
pnpm test -- skills/auto-commit/scripts/execute.test.ts

# 執行整合測試
pnpm test -- skills/auto-commit/scripts/index.test.ts
```

## 前置要求

- ✅ Git 已安裝且配置完成
- ✅ 在 Git 儲存庫中
- ✅ 已使用 `git add` 暫存檔案
- ✅ 已配置 Git 使用者資訊

## Conventional Commits 規範

詳見 [reference.md](./reference.md) 以了解：
- 提交類型說明
- 常見場景範例
- 最佳實踐

