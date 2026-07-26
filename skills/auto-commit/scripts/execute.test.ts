/**
 * Auto Commit - 執行邏輯單元測試
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { validateInput, generateCommitMessage, splitCommitsByType, generateChangesSummary, generateCommitMessageWithChanges } from './execute.ts'
import type { AutoCommitInput } from './types.js'

describe('Auto Commit - 執行邏輯', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('validateInput', () => {
    it('應該在 type 為空時拋出錯誤', () => {
      const input = { description: 'test', body: '- change' } as AutoCommitInput

      expect(() => validateInput(input)).toThrow('E001')
    })

    it('應該在無效的 type 時拋出錯誤', () => {
      const input: AutoCommitInput = {
        type: 'invalid' as unknown as AutoCommitInput['type'],
        description: 'test',
        body: '- change'
      }

      expect(() => validateInput(input)).toThrow('E002')
    })

    it('應該在 description 為空時拋出錯誤', () => {
      const input: AutoCommitInput = {
        type: 'feat',
        description: '',
        body: '- change'
      }

      expect(() => validateInput(input)).toThrow('E003')
    })

    it('應該在 body 為空時拋出錯誤', () => {
      const input = {
        type: 'feat',
        description: 'test'
      } as any

      expect(() => validateInput(input)).toThrow('E003-1')
    })

    it('應該接受有效的輸入', () => {
      const input: AutoCommitInput = {
        type: 'feat',
        description: 'test',
        body: '- change 1\n- change 2'
      }

      expect(() => validateInput(input)).not.toThrow()
    })
  })

  describe('generateCommitMessage', () => {
    it('應該生成簡單的提交訊息', () => {
      const input: AutoCommitInput = {
        type: 'feat',
        description: '新增功能',
        body: '- 新增登入頁面\n- 新增註冊功能'
      }

      const message = generateCommitMessage(input)

      expect(message).toContain('feat: 新增功能')
      expect(message).toContain('- 新增登入頁面')
    })

    it('應該生成包含 scope 的提交訊息', () => {
      const input: AutoCommitInput = {
        type: 'fix',
        scope: 'auth',
        description: '修復登入',
        body: '- 修正 token 過期判斷\n- 優化錯誤訊息'
      }

      const message = generateCommitMessage(input)

      expect(message).toContain('fix(auth): 修復登入')
      expect(message).toContain('- 修正 token 過期判斷')
    })

    it('應該包含 body、breaking change 和 issues', () => {
      const input: AutoCommitInput = {
        type: 'feat',
        scope: 'api',
        description: '重構 API',
        body: '- 使用 Bearer token\n- 新增 rate limiting',
        breaking: 'API key 認證已棄用',
        issues: ['#123', '#456']
      }

      const message = generateCommitMessage(input)

      expect(message).toContain('feat(api): 重構 API')
      expect(message).toContain('- 使用 Bearer token')
      expect(message).toContain('BREAKING CHANGE: API key 認證已棄用')
      expect(message).toContain('Closes #123, #456')
    })
  })

  describe('splitCommitsByType', () => {
    it('應該根據檔案路徑推測 commit 類型', () => {
      const files = [
        'src/utils.ts',
        'src/__tests__/utils.test.ts',
        'README.md',
        'src/styles.css',
        'package.json'
      ]

      const splits = splitCommitsByType(files, 'feat')

      expect(splits.length).toBeGreaterThan(1)
      const typeArray = splits.map(s => s.type)
      expect(typeArray).toContain('test')
      expect(typeArray).toContain('docs')
      expect(typeArray).toContain('style')
      expect(typeArray).toContain('chore')
    })

    it('應該分組相同類型的檔案', () => {
      const files = ['src/a.test.ts', 'src/b.test.ts', 'README.md']

      const splits = splitCommitsByType(files, 'feat')
      const testSplit = splits.find(s => s.type === 'test')

      expect(testSplit?.files?.length).toBe(2)
    })
  })

  describe('generateChangesSummary', () => {
    it('應該生成單個檔案的改動摘要', () => {
      const files = ['src/utils.ts']
      const summary = generateChangesSummary(files)

      expect(summary).toContain('- feat: src/utils.ts')
    })

    it('應該生成多檔案的改動摘要', () => {
      const files = ['src/a.test.ts', 'src/b.test.ts', 'README.md']
      const summary = generateChangesSummary(files)

      expect(summary.some(s => s.includes('test: 2 files'))).toBe(true)
      expect(summary.some(s => s.includes('docs: README.md'))).toBe(true)
    })
  })

  describe('generateCommitMessageWithChanges', () => {
    it('應該生成包含改動摘要的提交訊息', () => {
      const input: AutoCommitInput = {
        type: 'feat',
        description: '新增功能',
        includeChanges: true
      }
      const files = ['src/feature.ts', 'src/feature.test.ts']

      const message = generateCommitMessageWithChanges(input, files)

      expect(message).toContain('feat: 新增功能')
      expect(message).toContain('- feat:')
      expect(message).toContain('- test:')
    })

    it('應該在沒有檔案時不添加摘要', () => {
      const input: AutoCommitInput = {
        type: 'feat',
        description: '新增功能'
      }

      const message = generateCommitMessageWithChanges(input, [])

      expect(message).toBe('feat: 新增功能')
    })
  })
})