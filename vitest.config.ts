import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'node',
    include: ['skills/auto-commit/scripts/**/*.test.ts'],
    exclude: ['node_modules', 'dist']
  }
})
