/**
 * Auto Commit Skill - scripts 主入口點
 */

import { execute } from './execute.js'
import type { AutoCommitInput, AutoCommitOutput } from './types.js'

/**
 * 執行自動提交
 */
export async function autoCommit(input: AutoCommitInput): Promise<AutoCommitOutput> {
  return await execute(input)
}

export default { autoCommit }
