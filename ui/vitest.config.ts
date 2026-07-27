import { defineConfig } from 'vitest/config'
import { resolve } from 'path'

export default defineConfig({
  resolve: {
    alias: {
      '@': resolve(__dirname, '.'),
    },
  },
  esbuild: {
    // Phase 9: the .tsx components (DarkModeToggle, etc.) use JSX
    // without an explicit `import React from 'react'` line. The
    // classic JSX transform (esbuild default) compiles JSX to
    // `React.createElement(...)` which throws "React is not defined"
    // at runtime. Switching to the automatic transform (the same one
    // Next.js + SWC use in production) compiles JSX to
    // `import { jsx } from 'react/jsx-runtime'` and drops the need
    // for the React import. Tests no longer need either
    // `import React` or `createElement` ceremony.
    jsx: 'automatic',
    jsxImportSource: 'react',
  },
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./vitest.setup.ts'],
    // Phase 9: pattern uses **/ so nested __tests__ folders (e.g.
    // lib/math/__tests__/, components/layout/__tests__/) are picked up
    // alongside the top-level __tests__/ folder.
    include: [
      '__tests__/**/*.test.ts',
      '__tests__/**/*.test.tsx',
      '**/__tests__/**/*.test.ts',
      '**/__tests__/**/*.test.tsx',
    ],
    coverage: {
      // Phase 9.5 CI: the GitHub Actions workflow uploads the lcov
      // report from ui/coverage/ as a 7-day artifact. The provider
      // is @vitest/coverage-v8 (added to devDeps alongside vitest@1.6).
      // `enabled: true` makes coverage always-on so scripts/test.sh
      // (which calls `vitest run` with no --coverage flag) produces
      // the artifact. The ~10-20% perf hit on unit tests is the cost
      // of always-on coverage; flip to `false` if it becomes a
      // bottleneck and pass --coverage explicitly in CI instead.
      enabled: true,
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      reportsDirectory: './coverage',
      include: ['lib/**/*.ts', 'app/**/*.tsx', 'components/**/*.tsx'],
      // Phase 8: enforce 80% line / branch on the api auth+retry surface
      // once tests prove out — for now reporting only.
    },
  },
})
