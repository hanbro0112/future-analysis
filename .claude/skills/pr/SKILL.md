---
name: pr
description: 從 dev 分支發送 pull request 到 main 分支，title 與 body 皆保持簡易。當使用者要求「發 PR」「開 pull request」「dev 合併到 main」時使用此 skill。
---

# Dev to Main Pull Request

## 標準流程

1. 確認目前在 `dev` 分支且沒有未提交的變更（`git status`）。
2. `git push origin dev`，確保遠端 `dev` 為最新。
3. 用 `git log main..dev --oneline` 列出領先 main 的 commit，取每個 commit 的 description 作為 body 條列項目（直接沿用 commit 訊息第一行，不額外闡述）。
4. 用 `gh pr create` 建立 PR：
   - `--base main --head dev`
   - **title**：固定格式 `chore: sync dev to main`
   - **body**：簡短一句話 + commit 條列清單

   ```bash
   gh pr create --base main --head dev --title "chore: sync dev to main" --body "$(cat <<'EOF'
   同步 dev 分支變更至 main。

   - {commit description 1}
   - {commit description 2}
   EOF
   )"
   ```
5. 回報 PR URL 給使用者。

## 注意事項

- title 不需要每次客製化，維持固定簡短格式即可。
- body 只列 commit 一行摘要，不要展開說明改動細節或原因。
- 若 `main..dev` 沒有任何新 commit，告知使用者目前沒有可發送的變更，不建立 PR。
