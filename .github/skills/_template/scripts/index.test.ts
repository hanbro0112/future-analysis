/**
 * [Skill 名稱] - scripts 整合測試
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { [skillNameInCamelCase] } from './index.js'
import type { [SkillName]Input } from './types.js'

describe('[Skill 名稱] scripts 整合測試', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('應該成功執行', async () => {
    const input: [SkillName]Input = {
      param1: 'test-value'
    }

    const result = await [skillNameInCamelCase](input)

    expect(result.success).toBe(true)
  })

  it('應該在驗證失敗時返回錯誤', async () => {
    const input = {
      param1: ''
    } as [SkillName]Input

    const result = await [skillNameInCamelCase](input)

    expect(result.success).toBe(false)
    expect(result.error).toBeDefined()
  })
})
