/**
 * [Skill 名稱] 的類型定義
 */

/**
 * [Skill 名稱] 的輸入參數
 */
export interface [SkillName]Input {
  /** 參數1描述 */
  param1: string
  /** 參數2描述 (可選) */
  param2?: number
}

/**
 * [Skill 名稱] 的輸出結果
 */
export interface [SkillName]Output {
  /** 操作是否成功 */
  success: boolean
  /** 返回資料 (成功時) */
  data?: any
  /** 錯誤訊息 (失敗時) */
  error?: string
}
