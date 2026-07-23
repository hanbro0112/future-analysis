/**
 * Skill Registry - 所有 AI Agent Skills 的中央註冊表
 */

import type { CommitInput, CommitOutput } from './auto-commit/types.js'

/**
 * Skill 定義介面
 */
export interface SkillDefinition<T = unknown, R = unknown> {
  /** Skill 名稱 */
  name: string
  /** Skill 描述 */
  description: string
  /** 動態載入 Skill 的 handler */
  handler: () => Promise<{ default: unknown }>
  /** 輸入參數架構 */
  inputs?: Record<string, string>
  /** 輸出參數架構 */
  outputs?: Record<string, string>
}

/**
 * Skill Registry - 中央註冊表
 */
export const skillRegistry: Record<string, SkillDefinition<unknown, unknown>> = {
  'auto-commit': {
    name: '自動提交',
    description: '自動生成並提交符合 Conventional Commits 規範的提交訊息',
    handler: () => import('./auto-commit/scripts/index.js'),
    inputs: {
      type: 'CommitType (feat|fix|docs|style|refactor|perf|test|chore|ci) - 必填',
      scope: 'string - 提交範疇 (可選)',
      description: 'string - 簡短描述 - 必填',
      body: 'string - 詳細說明 (可選)',
      breaking: 'string - Breaking changes 說明 (可選)',
      issues: 'string[] - 相關 issue 編號 (可選)'
    },
    outputs: {
      success: 'boolean - 操作是否成功',
      message: 'string - 生成的提交訊息',
      commitHash: 'string - 提交哈希值 (成功時)',
      error: 'string - 錯誤訊息 (失敗時)'
    }
  }
}

/**
 * 執行指定的 Skill
 * @param skillName - Skill 名稱
 * @param input - 輸入參數
 * @returns Skill 執行結果
 */
export async function executeSkill(skillName: string, input: unknown): Promise<unknown> {
  const skillDef = skillRegistry[skillName]

  if (!skillDef) {
    return {
      success: false,
      error: `Skill "${skillName}" 不存在`
    }
  }

  try {
    const skill = await skillDef.handler()
    if (typeof skill.default === 'function') {
      const fn = skill.default as (value: unknown) => Promise<unknown>
      return await fn(input)
    }

    if (typeof skill.default === 'object' && skill.default !== null && 'autoCommit' in skill.default) {
      const defaultObject = skill.default as { autoCommit?: (value: unknown) => Promise<unknown> }
      const handler = defaultObject.autoCommit
      if (typeof handler === 'function') {
        return await handler(input)
      }
    }

    return {
      success: false,
      error: `Skill "${skillName}" 的 default 匯出型別不支援`
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    return {
      success: false,
      error: `執行 Skill "${skillName}" 失敗: ${errorMessage}`
    }
  }
}

/**
 * 取得所有可用的 Skill 列表
 */
export function listSkills(): Array<{ name: string; description: string }> {
  return Object.entries(skillRegistry).map(([key, skill]) => ({
    name: key,
    description: skill.description
  }))
}

/**
 * 取得指定 Skill 的詳細資訊
 */
export function getSkillInfo(skillName: string): SkillDefinition<unknown, unknown> | null {
  return skillRegistry[skillName] || null
}
