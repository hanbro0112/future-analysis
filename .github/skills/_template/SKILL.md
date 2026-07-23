# [Skill 名稱]

## 基本資訊

**Skill ID**: `[skill-id]`  
**版本**: 1.0.0  
**最後更新**: 2026-03-06  

## 一句話描述

[簡潔描述此 skill 的核心功能]

## 功能說明

詳細說明此 skill 做了什麼，為什麼需要它。

## 觸發時機

何時應該執行此 skill？

- [ ] 自動觸發 (指定條件)
- [ ] 手動觸發 (用戶主動調用)
- [ ] 定時執行 (Cron job)
- [ ] 事件驅動 (Git hook/Webhook)

**條件示例**: `git status 有未提交的變更`

## 相依工具

列出此 skill 依賴的外部工具或命令：

- `git` - 版本控制系統
- `node` - JavaScript 執行環境
- `npm` - 套件管理工具

## 執行流程

```
開始
  ↓
[步驟 1]: 驗證輸入參數
  ↓
[步驟 2]: 檢查前置條件 (git status 等)
  ↓
[步驟 3]: 執行核心邏輯
  ↓
[步驟 4]: 返回結果
  ↓
結束
```

### 流程詳細

#### 步驟 1: 驗證輸入
- 檢查必填參數是否存在
- 驗證參數格式和有效性

#### 步驟 2: 前置條件檢查
- 檢查必要的工具是否可用
- 驗證當前環境狀態

#### 步驟 3: 執行核心邏輯
- 執行主要功能
- 處理可能的異常

#### 步驟 4: 返回結果
- 返回成功訊息和資料
- 返回失敗訊息和錯誤碼

## 輸入參數

| 參數名 | 類型 | 必填 | 說明 | 範例 |
|--------|------|------|------|------|
| param1 | string | ✅ | 參數1描述 | `value1` |
| param2 | number | ❌ | 參數2描述 | `123` |

## 輸出結果

| 欄位 | 類型 | 說明 | 範例 |
|------|------|------|------|
| success | boolean | 操作是否成功 | `true` |
| data | object | 返回資料 | `{ id: '123' }` |
| error | string | 錯誤訊息 | `"param1 是必填項"` |

## 錯誤處理

| 錯誤碼 | 錯誤訊息 | 原因 | 解決方案 |
|--------|--------|------|---------|
| E001 | param1 是必填項 | 缺少必填參數 | 檢查輸入參數 |
| E002 | Git 不可用 | 系統未安裝 Git | 安裝 Git |
| E003 | 操作失敗 | 執行過程中出錯 | 查看詳細錯誤日誌 |

## 使用範例

### 基本使用

```typescript
import { executeSkill } from './skills/manifest.js'

const result = await executeSkill('[skill-id]', {
  param1: 'value1'
})

if (result.success) {
  console.log(result.data)
} else {
  console.error(result.error)
}
```

### 進階用法

```typescript
const result = await executeSkill('[skill-id]', {
  param1: 'value1',
  param2: 123
})
```

## 注意事項

- ⚠️ 注意事項 1
- ⚠️ 注意事項 2
- ⚠️ 修改系統檔案時要謹慎

## 測試

執行此 skill 的測試：

```bash
pnpm test -- skills/[skill-id]/scripts/*.test.ts
```

## 相關文件

- `reference.md` - 補充參考資訊、專有名詞、填寫範例
- `template/` - 輸出模板（如果需要固定格式）
- `scripts/` - 執行過程需要跑的程式碼
