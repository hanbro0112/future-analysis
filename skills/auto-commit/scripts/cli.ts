#!/usr/bin/env node
/**
 * Auto Commit CLI - 命令行入口
 */

import { parseArgs } from 'node:util'
import { autoCommit } from './index.js'
import type { CommitType } from './types.js'

async function main() {
  try {
    const { values } = parseArgs({
      options: {
        type: { type: 'string', short: 't' },
        scope: { type: 'string', short: 's' },
        description: { type: 'string', short: 'd' },
        body: { type: 'string', short: 'b' },
        breaking: { type: 'string' },
        issues: { type: 'string', multiple: true, short: 'i' },
        splitByType: { type: 'boolean', default: false },
        includeChanges: { type: 'boolean', default: false },
      },
    })

    if (!values.type || !values.description) {
      console.error('❌ 錯誤：type 和 description 是必填參數')
      console.log('\n使用方式：')
      console.log('  tsx cli.ts --type=feat --description="新增功能"')
      console.log('\n選項：')
      console.log('  -t, --type          提交類型 (feat, fix, docs, etc.)')
      console.log('  -s, --scope         提交範疇')
      console.log('  -d, --description   提交描述')
      console.log('  -b, --body          詳細說明（description 和 body 之間空一行）')
      console.log('  --breaking          Breaking changes')
      console.log('  -i, --issues        相關 issue')
      console.log('  --splitByType       按類型拆分提交')
      console.log('  --includeChanges    包含改動摘要')
      console.log('\n範例：')
      console.log('  tsx cli.ts --type=feat --scope=auth --description="新增登入功能" \\')
      console.log('    --body="- 支援 OAuth\\n- 支援 JWT"')
      process.exit(1)
    }

    const result = await autoCommit({
      type: values.type as CommitType,
      scope: values.scope,
      description: values.description,
      body: values.body,
      breaking: values.breaking,
      issues: values.issues,
      splitByType: values.splitByType,
      includeChanges: values.includeChanges,
    })

    if (result.success) {
      console.log('✅ 提交成功！')
      if (result.commitHashes) {
        console.log(`📦 提交哈希: ${result.commitHashes.join(', ')}`)
      } else if (result.commitHash) {
        console.log(`📦 提交哈希: ${result.commitHash}`)
      }
      if (result.message) {
        console.log(`📝 訊息: ${result.message}`)
      }
    } else {
      console.error(`❌ 提交失敗: ${result.error}`)
      process.exit(1)
    }
  } catch (error) {
    console.error('❌ 執行錯誤:', error instanceof Error ? error.message : error)
    process.exit(1)
  }
}

main()
