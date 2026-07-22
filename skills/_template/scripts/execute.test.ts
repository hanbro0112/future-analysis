/**
 * [Skill 名稱] 單元測試
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { validateInput, checkPreconditions, executeCore, execute } from './execute.ts'
import type { [SkillName]Input } from './types.js'

describe('[Skill 名稱] 執行邏輯', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('validateInput', () => {
    it('應該驗證必填參數', () => {
      const input = {
        param1: ''
      } as [SkillName]Input

      expect(() => validateInput(input)).toThrow('E001')
    })

    it('應該接受有效的輸入', () => {
      const input: [SkillName]Input = {
        param1: 'test-value'
      }

      expect(() => validateInput(input)).not.toThrow()
    })
  })

  describe('execute', () => {
    it('應該成功執行', async () => {
      const input: [SkillName]Input = {
        param1: 'test-value'
      }

      const result = await execute(input)

      expect(result.success).toBe(true)
      expect(result.data).toBeDefined()
    })

    it('應該在驗證失敗時返回錯誤', async () => {
      const input = {
        param1: ''
      } as [SkillName]Input

      const result = await execute(input)

      expect(result.success).toBe(false)
      expect(result.error).toContain('E001')
    })
  })
})
