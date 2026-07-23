/**
 * [Skill 名稱] - scripts 主入口點
 */

import { execute } from './execute.js'
import type { [SkillName]Input, [SkillName]Output } from './types.js'

/**
 * 執行此 Skill
 */
export async function [skillNameInCamelCase](input: [SkillName]Input): Promise<[SkillName]Output> {
  return await execute(input)
}

export default { [skillNameInCamelCase] }
