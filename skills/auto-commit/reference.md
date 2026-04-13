# Auto Commit - 參考資訊

## Conventional Commits 規範

Conventional Commits 是一種提交訊息規範，便於自動化產生 CHANGELOG 和版本號。

### 完整格式

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

### 完整範例

```
feat(api): 新增用戶認證端點

實現了 JWT token 認證機制，支援 refresh token。
新增了 /auth/login 和 /auth/refresh 端點。

BREAKING CHANGE: 舊的 /authenticate 端點已移除
Closes #123, #456
```

## 提交類型

| 類型 | 說明 | 範例 |
|------|------|------|
| **feat** | 新功能 | `feat: 新增用戶登入` |
| **fix** | 修復 Bug | `fix: 修復密碼驗證邏輯` |
| **docs** | 文件相關 | `docs: 更新 API 文檔` |
| **style** | 代碼風格 | `style: 調整縮進` |
| **refactor** | 重構代碼 | `refactor: 簡化認證邏輯` |
| **perf** | 效能優化 | `perf: 優化查詢速度` |
| **test** | 測試相關 | `test: 新增登入測試` |
| **chore** | 維護任務 | `chore: 升級依賴` |
| **ci** | CI/CD 相關 | `ci: 新增 GitHub Action` |

## 常見問題

### Q: 什麼時候應該使用 Breaking Change?

A: 當改動會導致現有用戶代碼無法正常運作時。例如移除 API 端點、改變參數格式等。

### Q: description 應該多長?

A: 保持簡潔，通常 50 個字符以內。詳細說明應放在 body 中。

### Q: 一次提交可以解決多個 Issue 嗎?

A: 可以，使用逗號分隔：`Closes #123, #456`

### Q: 如何修改已推送的提交訊息?

A: 
```bash
git commit --amend -m "新訊息"
git push --force-with-lease
```
⚠️ 不推薦在共享分支上進行此操作

## 延伸閱讀

- [Conventional Commits 官方文檔](https://www.conventionalcommits.org/zh-hans/)
- [Semantic Versioning](https://semver.org/)
