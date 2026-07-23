# 輸出模板範例

此目錄存放 Skill 需要的輸出模板。

## 使用說明

如果你的 Skill 需要生成固定格式的輸出（例如報告、配置檔案、文件），
將模板檔案放在此目錄中。

## 範例

### template-name.txt

```
[模板內容]
```

### template-config.json

```json
{
  "key": "value"
}
```

## 在 scripts/execute.ts 中使用

```typescript
import { readFileSync } from 'fs'
import { join } from 'path'

const templatePath = join(import.meta.dirname, '../template/template-name.txt')
const templateContent = readFileSync(templatePath, 'utf-8')
```
