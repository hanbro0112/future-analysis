# Auto Commit Skill

自動生成並提交符合 Conventional Commits 規範的 Git 提交訊息。

## 快速開始

```typescript
import { autoCommit } from './skills/auto-commit/scripts/index.js'

const result = await autoCommit({
  type: 'feat',
  description: '新增用戶認證功能'
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
- ✅ 支援詳細說明 (body) 和 Breaking Changes
- ✅ 支援 Issue 鏈接
- ✅ 完整的錯誤碼系統 (E001-E007)
- ✅ 前置條件檢查

## 使用場景

### 簡單提交

```typescript
await autoCommit({
  type: 'feat',
  description: '新增用戶認證'
})
```

### 帶範疇的提交

```typescript
await autoCommit({
  type: 'fix',
  scope: 'auth',
  description: '修復登入驗證'
})
```

### 完整提交

```typescript
await autoCommit({
  type: 'feat',
  scope: 'api',
  description: '重構 API 認證',
  body: '使用 Bearer token 替代 API key',
  breaking: 'API key 認證已棄用',
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

