/**
 * [Skill 名稱] - 執行邏輯
 * 
 * 此檔案包含 Skill 的核心執行邏輯
 */

import type { [SkillName]Input, [SkillName]Output } from './types.js'

/**
 * 驗證輸入參數
 */
export function validateInput(input: [SkillName]Input): void {
  if (!input.param1) {
    throw new Error('E001: param1 是必填項')
  }

  // 其他驗證邏輯
}

/**
 * 檢查前置條件
 */
export async function checkPreconditions(): Promise<void> {
  // 檢查必要的工具是否可用
  // 驗證環境狀態
}

/**
 * 執行核心邏輯
 */
export async function executeCore(input: [SkillName]Input): Promise<any> {
  // 實現具體邏輯
  return {}
}

/**
 * 執行 Skill 的主函數
 */
export async function execute(input: [SkillName]Input): Promise<[SkillName]Output> {
  try {
    // 步驟 1: 驗證輸入
    validateInput(input)

    // 步驟 2: 檢查前置條件
    await checkPreconditions()

    // 步驟 3: 執行核心邏輯
    const result = await executeCore(input)

    // 步驟 4: 返回結果
    return {
      success: true,
      data: result
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    return {
      success: false,
      error: errorMessage
    }
  }
}
