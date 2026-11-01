/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite'
import { cwd } from 'node:process'
import react from '@vitejs/plugin-react'
import { parseDeploymentEnvironment, parseLogLevel } from './src/logging/domain'

export default defineConfig(({ mode }) => {
  parseLogLevel(loadEnv(mode, cwd(), 'VITE_').VITE_LOG_LEVEL)
  return {
    define: { 'import.meta.env.APP_ENV': JSON.stringify(parseDeploymentEnvironment(loadEnv(mode, cwd(), '').ENV)) ?? 'undefined' },
    plugins: [react()],
    test: {
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
      css: true,
      coverage: {
        provider: 'v8',
        include: ['src/**/*.{ts,tsx}'],
        exclude: [
          'src/**/*.d.ts',
          'src/api/types.ts',
          'src/main.tsx',
          'src/mocks/**',
          'src/test/**',
        ],
        reporter: ['text', 'html', 'json', 'lcov', 'cobertura'],
        thresholds: {
          statements: 100,
          branches: 100,
          functions: 100,
          lines: 100,
        },
      },
    },
  }
})
