/**
 * Auto Commit Skill 的類型定義
 */

export type CommitType = 'feat' | 'fix' | 'docs' | 'style' | 'refactor' | 'perf' | 'test' | 'chore' | 'ci'

/**
 * Auto Commit 的輸入參數
 */
export interface AutoCommitInput {
  /** 提交類型 (feat, fix, docs 等) */
  type: CommitType
  /** 提交範疇 (可選) */
  scope?: string
  /** 提交描述 (必填) */
  description: string
  /** 詳細說明 (必填，使用條列式格式) */
  body: string
  /** Breaking changes (可選) */
  breaking?: string
  /** 相關 issue (可選，例如 #123) */
  issues?: string[]
  /** 是否拆分 commit 按照 commit 類型前綴 */
  splitByType?: boolean
  /** 是否自動添加改動摘要到提交訊息 */
  includeChanges?: boolean
}

/**
 * Auto Commit 的輸出結果
 */
export interface AutoCommitOutput {
  /** 操作是否成功 */
  success: boolean
  /** 生成的提交訊息 */
  message?: string
  /** 提交哈希值 (成功時返回) */
  commitHash?: string
  /** 多個 commit 的哈希值 (拆分時返回) */
  commitHashes?: string[]
  /** 錯誤訊息 (失敗時返回) */
  error?: string
}

/**
 * 拆分後的 commit 訊息
 */
export interface SplitCommit {
  /** Commit 類型前綴 (feat, fix, docs 等) */
  type: CommitType
  /** Commit 訊息 */
  message: string
  /** 相關的檔案列表 */
  files?: string[]
}
