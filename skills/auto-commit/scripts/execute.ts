/**
 * Auto Commit - 執行邏輯
 */

import { execSync } from 'child_process'
import type { AutoCommitInput, AutoCommitOutput, SplitCommit, CommitType } from './types.js'

/**
 * 驗證輸入參數
 * @throws 當輸入無效時拋出錯誤
 */
export function validateInput(input: AutoCommitInput): void {
  if (!input.type) {
    throw new Error('E001: type 是必填項')
  }

  const validTypes: string[] = ['feat', 'fix', 'docs', 'style', 'refactor', 'perf', 'test', 'chore', 'ci']
  if (!validTypes.includes(input.type)) {
    throw new Error(`E002: 無效的 type: ${input.type}。有效值: ${validTypes.join(', ')}`)
  }

  if (!input.description || input.description.trim().length === 0) {
    throw new Error('E003: description 是必填項且不能為空')
  }

  // 驗證 body 必填
  if (!input.body || input.body.trim().length === 0) {
    throw new Error('E003-1: body 是必填項，必須提供詳細的改動說明（使用條列式格式）')
  }

  // 驗證 body 格式（建議使用條列式）
  const hasListFormat = input.body.includes('-') || input.body.includes('*')
  if (!hasListFormat) {
    console.warn('⚠️  建議 body 使用條列式格式（- 或 * 開頭），例如：\n- 改動項目 1\n- 改動項目 2')
  }
}

/**
 * 檢查前置條件
 * @throws 當前置條件不符時拋出錯誤
 */
export async function checkPreconditions(): Promise<void> {
  try {
    // 檢查 git 是否可用
    execSync('git --version', { stdio: 'pipe' })
  } catch {
    throw new Error('E004: Git 不可用或未安裝')
  }

  try {
    // 檢查是否在 git 儲存庫中
    execSync('git rev-parse --git-dir', { stdio: 'pipe' })
  } catch {
    throw new Error('E005: 不在 Git 儲存庫中')
  }

  try {
    // 檢查是否有暫存的變更
    const status = execSync('git status --porcelain', {
      encoding: 'utf-8',
      stdio: 'pipe'
    }).trim()

    if (!status) {
      throw new Error('E006: 沒有暫存的變更可以提交')
    }
  } catch (error) {
    if (error instanceof Error && error.message.startsWith('E006')) {
      throw error
    }
  }
}

/**
 * 生成改動摘要列表
 */
export function generateChangesSummary(files: string[]): string[] {
  const summary: string[] = []
  const categories: Record<string, string[]> = {}

  for (const file of files) {
    const type = detectCommitTypeFromFile(file)
    if (!categories[type]) {
      categories[type] = []
    }
    categories[type].push(file)
  }

  // 按類型生成摘要
  for (const [type, fileList] of Object.entries(categories)) {
    if (fileList.length === 1) {
      summary.push(`- ${type}: ${fileList[0]}`)
    } else {
      summary.push(`- ${type}: ${fileList.length} files`)
    }
  }

  return summary
}

/**
 * 根據 Conventional Commits 規範生成提交訊息
 */
export function generateCommitMessage(input: AutoCommitInput): string {
  let message = input.type

  if (input.scope) {
    message += `(${input.scope})`
  }

  message += `: ${input.description}`

  if (input.body) {
    message += `\n\n${input.body}`
  }

  if (input.breaking) {
    message += `\n\nBREAKING CHANGE: ${input.breaking}`
  }

  if (input.issues && input.issues.length > 0) {
    message += `\n\nCloses ${input.issues.join(', ')}`
  }

  return message
}

/**
 * 生成包含改動摘要的完整提交訊息
 */
export function generateCommitMessageWithChanges(input: AutoCommitInput, stagedFiles: string[]): string {
  let message = generateCommitMessage(input)
  
  if (stagedFiles.length > 0) {
    const changes = generateChangesSummary(stagedFiles)
    if (changes.length > 0) {
      message += `\n${changes.join('\n')}`
    }
  }

  return message
}

/**
 * 執行 git commit 命令
 */
export async function executeCommit(message: string): Promise<string> {
  try {
    // 使用 -m 標誌執行提交
    execSync(`git commit -m "${message.replace(/"/g, '\\"')}"`, {
      stdio: 'pipe',
      encoding: 'utf-8'
    })

    // 取得提交哈希值
    const commitHash = execSync('git rev-parse HEAD', {
      stdio: 'pipe',
      encoding: 'utf-8'
    }).trim()

    return commitHash
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    throw new Error(`E007: Git 提交失敗: ${errorMessage}`)
  }
}

/**
 * 取得暫存的檔案列表
 */
export function getStagedFiles(): string[] {
  try {
    const stagedOutput = execSync('git diff --cached --name-only', {
      encoding: 'utf-8',
      stdio: 'pipe'
    }).trim()

    return stagedOutput.split('\n').filter(file => file.length > 0)
  } catch {
    return []
  }
}

/**
 * 根據 commit 訊息類型前綴拆分檔案
 */
export function splitCommitsByType(files: string[], commitType: CommitType): SplitCommit[] {
  const splits: Map<CommitType, string[]> = new Map()

  // 分析檔案路徑來推測 commit 類型
  for (const file of files) {
    const detectedType = detectCommitTypeFromFile(file)
    if (!splits.has(detectedType)) {
      splits.set(detectedType, [])
    }
    splits.get(detectedType)!.push(file)
  }

  // 轉換為 SplitCommit 陣列
  const splitCommits: SplitCommit[] = []
  splits.forEach((fileList, type) => {
    const message = `${type}: ${commitType === type ? 'primary changes' : `changes in ${fileList[0]}`}`
    splitCommits.push({
      type,
      message,
      files: fileList
    })
  })

  return splitCommits
}

/**
 * 根據檔案路徑推測 commit 類型
 */
function detectCommitTypeFromFile(file: string): CommitType {
  const path = file.toLowerCase()

  if (path.includes('test') || path.includes('spec')) return 'test'
  if (path.includes('readme') || path.includes('doc')) return 'docs'
  if (path.includes('style') || path.includes('.css') || path.includes('.scss')) return 'style'
  if (path.includes('perf')) return 'perf'
  if (path.includes('package.json') || path.includes('lock')) return 'chore'
  if (path.includes('.github') || path.includes('.circleci') || path.includes('ci')) return 'ci'
  if (path.includes('refactor')) return 'refactor'

  return 'feat'
}

/**
 * 部分暫存檔案並執行 commit
 */
export async function executePartialCommit(files: string[], message: string): Promise<string> {
  try {
    // 暫存指定的檔案
    execSync(`git add ${files.map(f => `"${f}"`).join(' ')}`, {
      stdio: 'pipe',
      encoding: 'utf-8'
    })

    // 執行提交
    return await executeCommit(message)
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    throw new Error(`E008: 部分提交失敗: ${errorMessage}`)
  }
}

/**
 * 執行 Auto Commit Skill 的主函數
 */
export async function execute(input: AutoCommitInput): Promise<AutoCommitOutput> {
  try {
    // 步驟 1: 驗證輸入
    validateInput(input)

    // 步驟 2: 檢查前置條件
    await checkPreconditions()

    // 步驟 3: 執行核心邏輯
    const stagedFiles = getStagedFiles()
    
    // 如果需要添加改動摘要
    let commitMessage: string
    if (input.includeChanges) {
      commitMessage = generateCommitMessageWithChanges(input, stagedFiles)
    } else {
      commitMessage = generateCommitMessage(input)
    }

    // 如果需要拆分 commit
    if (input.splitByType) {
      const splits = splitCommitsByType(stagedFiles, input.type)

      if (splits.length > 1) {
        const commitHashes: string[] = []

        for (const split of splits) {
          if (split.files && split.files.length > 0) {
            // 重置暫存區
            execSync('git reset HEAD', { stdio: 'pipe' })

            // 提交每個類型的檔案
            const splitMessage = `${split.type}: ${input.description}`
            const hash = await executePartialCommit(split.files, splitMessage)
            commitHashes.push(hash)
          }
        }

        return {
          success: true,
          message: `拆分為 ${commitHashes.length} 個 commit`,
          commitHashes
        }
      }
    }

    // 步驟 4: 正常提交
    const commitHash = await executeCommit(commitMessage)
    return {
      success: true,
      message: commitMessage,
      commitHash
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    return {
      success: false,
      error: errorMessage
    }
  }
}
