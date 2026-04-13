/**
 * Auto Commit - 整合測試
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { autoCommit } from './index.js'
import type { AutoCommitInput } from './types.js'

describe('Auto Commit - 整合測試', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('應該在驗證失敗時返回錯誤', async () => {
    const input = {
      type: 'invalid',
      description: 'test'
    } as unknown as AutoCommitInput

    const result = await autoCommit(input)

    expect(result.success).toBe(false)
    expect(result.error).toContain('E002')
  })

  it('應該在沒有 description 時返回錯誤', async () => {
    const input: AutoCommitInput = {
      type: 'feat',
      description: ''
    }

    const result = await autoCommit(input)

    expect(result.success).toBe(false)
    expect(result.error).toContain('E003')
  })
})
