# Auto Commit

## 基本資訊

**Skill ID**: `auto-commit`  
**版本**: 2.2.0  
**最後更新**: 2026-06-30  

## 一句話描述

Git 提交訊息

## ⚠️ 使用條件與規範

### 優先使用原生 Git 命令

**如果可以直接使用 `git commit`，請優先使用原生命令而非此 skill**，以保持簡潔性。

### 必須包含 Body

所有 commit **必須包含 body**（詳細說明），格式如下：

```
{type}({scope}): {description}

- {改動說明 1}
- {改動說明 2}
- {改動說明 3}
```

### Body 格式規範

Body 必須使用**繁體中文**並遵循以下規範：

1. **使用條列式說明**（每項改動一行）
2. **清晰描述具體改動內容**（不要模糊描述）
3. **按邏輯順序排列**（從主要到次要）

#### ✅ 正確範例

```bash
git commit -m "fix(strategy): 修復多空比不更新的問題

- 當 tick_type 為 0 時，根據價格變動推測內外盤
- 價格上漲判定為外盤（買進），下跌判定為內盤（賣出）
- 價格不變時均分到買賣雙方
- 加入詳細的調試輸出顯示 tick_type 和視窗統計"
```

#### ❌ 錯誤範例

```bash
# ❌ 沒有 body
git commit -m "fix: 修復問題"

# ❌ body 描述不清楚
git commit -m "fix: 修復問題

- 更新了一些邏輯
- 修改了代碼"
```

### Commit Type 規範

遵循 Conventional Commits：

| Type | 說明 | 範例 |
|------|------|------|
| `feat` | 新增功能 | `feat(auth): 新增 OAuth 登入` |
| `fix` | 修復錯誤 | `fix(api): 修復資料重複問題` |
| `docs` | 文檔變更 | `docs(readme): 更新安裝說明` |
| `style` | 程式碼格式調整 | `style: 統一縮排為 2 空格` |
| `refactor` | 重構程式碼 | `refactor(utils): 簡化日期處理邏輯` |
| `perf` | 效能優化 | `perf(query): 優化資料庫查詢` |
| `test` | 測試相關 | `test(user): 新增使用者測試案例` |
| `chore` | 雜項變更 | `chore: 更新依賴版本` |
| `ci` | CI/CD 變更 | `ci: 新增 GitHub Actions` |

## 功能說明

此 Skill 簡化了 Git 提交流程，自動生成遵循 Conventional Commits 規範的提交訊息，並執行 Git 提交操作。支援提交類型、範疇、詳細說明、Breaking Changes 和 Issue 鏈接。

**新功能**: 支持按 commit 類型前綴（feat, fix, docs 等）自動拆分提交，讓每個 commit 更加單一職責。

## 觸發時機

- [x] 手動觸發 (開發者主動調用)
- [ ] 自動觸發 (Git hook 等)
- [ ] 定時執行
- [ ] 事件驅動

**條件**: 開發者在本地有未提交的 Git 變更

## 相依工具

- `git` - Git 版本控制系統（必須已安裝且配置完成）
- `node` - JavaScript 執行環境（v18+）

## 執行流程

**標準模式**：
```
開始
  ↓
[步驟 1]: 驗證輸入參數 (type, description)
  ↓
[步驟 2]: 檢查前置條件 (Git 可用、在 Git 儲存庫中、有暫存變更)
  ↓
[步驟 3]: 生成符合 Conventional Commits 規範的提交訊息
  ↓
[步驟 4]: 執行 git commit 命令
  ↓
[步驟 5]: 返回提交哈希值和訊息
  ↓
結束
```

**拆分模式** (當 `splitByType: true` 時)：
```
開始
  ↓
[步驟 1-2]: 驗證輸入和檢查前置條件
  ↓
[步驟 3]: 獲取暫存檔案清單
  ↓
[步驟 4]: 根據檔案路徑推測 commit 類型並分組
  ↓
[步驟 5]: 依序提交每組檔案 (feat, fix, docs, style, test, chore 等)
  ↓
[步驟 6]: 返回多個提交哈希值
  ↓
結束
```

## 輸入參數

| 參數名 | 類型 | 必填 | 說明 | 範例 |
|--------|------|------|------|------|
| type | CommitType | ✅ | 提交類型 | `feat`, `fix` |
| scope | string | ❌ | 提交範疇 | `auth`, `api` |
| description | string | ✅ | 簡短描述 | `新增用戶認證` |
| body | string | ✅ | 詳細說明（必填，使用條列式） | `- 新增 OAuth 登入流程\n- 整合 Firebase Auth` |
| breaking | string | ❌ | Breaking Change | `舊端點已移除` |
| issues | string[] | ❌ | 相關 Issue | `['#123']` |
| splitByType | boolean | ❌ | 是否按 commit 類型拆分 | `true` (預設: `false`) |
| includeChanges | boolean | ❌ | 自動添加改動摘要到訊息 | `true` (預設: `false`) |

## 輸出結果

| 欄位 | 類型 | 說明 | 範例 |
|------|------|------|------|
| success | boolean | 操作是否成功 | `true` |
| message | string | 生成的提交訊息 | `feat(auth): 新增` 或 `拆分為 3 個 commit` |
| commitHash | string | 提交哈希值 (成功時) | `a1b2c3d4` |
| commitHashes | string[] | 多個提交哈希值 (拆分時) | `['a1b2c3d4', 'b2c3d4e5']` |
| error | string | 錯誤訊息 (失敗時) | `E001: type 必填` |

## 錯誤處理

| 錯誤碼 | 錯誤訊息 | 原因 | 解決方案 |
|--------|--------|------|---------|
| E001 | type 是必填項 | 未提供 type | 提供有效的 type 值 |
| E002 | 無效的 type | type 不在允許清單 | 使用 feat, fix 等 |
| E003 | description 是必填項 | 未提供 description | 提供非空 description |
| E003-1 | body 是必填項 | 未提供 body 詳細說明 | 提供條列式改動說明 |
| E003-2 | body 格式不正確 | body 未使用條列式 | 使用 `- 改動項目` 格式 |
| E004 | Git 不可用 | Git 未安裝 | 安裝 Git |
| E005 | 不在 Git 儲存庫中 | 目錄不是 Git 儲存庫 | 進入 Git 儲存庫目錄 |
| E006 | 沒有暫存的變更 | 沒有 git add | 先執行 git add |
| E007 | Git 提交失敗 | 命令執行失敗 | 檢查 Git 配置 |
| E008 | 部分提交失敗 | 拆分模式中的提交失敗 | 檢查檔案權限和 Git 狀態 |

## 使用範例

### 基本使用

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

### 進階用法

```typescript
const result = await autoCommit({
  type: 'feat',
  scope: 'auth',
  description: '新增 OAuth 登入',
  body: '整合 Google 和 GitHub OAuth',
  breaking: '舊的 token 端點已移除',
  issues: ['#123', '#456']
})

// 生成的 commit 訊息格式：
// feat(auth): 新增 OAuth 登入
//
// 整合 Google 和 GitHub OAuth
//
// BREAKING CHANGE: 舊的 token 端點已移除
//
// Closes #123, #456
```

### 自動添加改動摘要

自動將暫存檔案列表添加到 commit 訊息中：

```typescript
const result = await autoCommit({
  type: 'feat',
  description: '新增認證功能',
  includeChanges: true  // 啟用改動摘要
})

// 生成的 commit 訊息：
// feat: 新增認證功能
// - feat: src/auth.ts
// - test: src/auth.test.ts
// - docs: README.md
```

### 拆分 commit 用法

當有多個不同類型的變更時，可以使用拆分模式自動分組提交：

```typescript
// 假設暫存區有：
// - src/auth.ts (feat)
// - src/auth.test.ts (test)
// - README.md (docs)
// - src/styles.css (style)

const result = await autoCommit({
  type: 'feat',
  description: '新增認證功能',
  splitByType: true  // 啟用拆分模式
})

// 結果會產生多個 commit：
// feat: 新增認證功能
// test: 新增認證功能
// docs: 新增認證功能
// style: 新增認證功能

console.log(result.commitHashes) // ['a1b2c3d4', 'b2c3d4e5', 'c3d4e5f6', 'd4e5f6g7']
```

## 相關文件

- `reference.md` - Conventional Commits 規範參考、常見問題
- `scripts/execute.ts` - 執行邏輯實現
- `scripts/execute.test.ts` - 邏輯測試
