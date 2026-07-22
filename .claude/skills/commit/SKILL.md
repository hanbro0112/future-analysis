---
name: commit
description: 產生符合 Conventional Commits 規範的 Git commit 訊息並執行 git commit，要求 body 必填且以繁體中文條列式說明改動。當使用者要求「commit」「幫我提交」「產生 commit 訊息」時使用此 skill。
---

# Auto Commit

## Commit 訊息格式

```
{type}({scope}): {description}

- {改動說明 1}
- {改動說明 2}
- {改動說明 3}
```

- `description` 是一行簡短摘要（祈使句、繁體中文）。
- **body 必填**，用條列式（`- ...`）以繁體中文清楚描述具體改動，依重要性由主到次排列。不要寫「修改了代碼」這種模糊描述——要讓人不看 diff 也知道改了什麼。
- `scope` 選填，通常對應受影響的模組/目錄。
- body 點數不限，該列多少就列多少，但每點一行講完、不要長句堆疊細節或解釋原因/背景。只列「改了什麼」，不列「為什麼」「怎麼運作」；細節留給 code 本身或 PR 說明。
- working tree 裡的變更一律合成**一個 commit** 提交，不要因為主題不同就拆成多個 commit。

### Commit Type

| Type | 說明 |
|------|------|
| `feat` | 新增功能 |
| `fix` | 修復錯誤 |
| `docs` | 文檔變更 |
| `style` | 程式碼格式調整（不影響邏輯） |
| `refactor` | 重構程式碼 |
| `perf` | 效能優化 |
| `test` | 測試相關 |
| `chore` | 雜項變更（依賴、設定等） |
| `ci` | CI/CD 變更 |

### 範例

✅ 好的 body：
```
fix(strategy): 修復多空比不更新的問題

- 當 tick_type 為 0 時，根據價格變動推測內外盤
- 價格上漲判定為外盤（買進），下跌判定為內盤（賣出）
- 價格不變時均分到買賣雙方
```

❌ 不好的 body：
```
fix: 修復問題

- 更新了一些邏輯
```

## 標準流程

1. 用 `git status` / `git diff --staged` 確認暫存區的變更內容。
2. 依上方格式撰寫 commit 訊息（description + 條列式 body）。
3. 用 heredoc 執行 `git commit`，避免多行訊息在 shell 中跳脫出錯：
   ```bash
   git commit -m "$(cat <<'EOF'
   feat(auth): 新增 OAuth 登入

   - 新增 Google OAuth 登入流程
   - 整合 Firebase Auth 驗證
   EOF
   )"
   ```
4. 回報 commit hash 給使用者。
