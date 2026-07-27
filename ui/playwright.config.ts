/**
 * Playwright config for browser smoke tests.
 *
 * The smoke test (ui/__tests__/e2e/dashboard.spec.ts) starts the
 * Next.js dev server on :3000 and the rules-service backend on
 * :8000 before running. The smoke test asserts:
 *   1. The dashboard route loads without console errors   *   2. The sidebar shows the "Atlas" brand
 *   3. The dark mode toggle works (class toggle + localStorage)
 *   4. The Financial Plans section renders with the 3 stat cards
 *
 * Install: `npx playwright install chromium` (one-time)
 * Run:     `npx playwright test`
 */
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './__tests__/e2e',
  fullyParallel: false, // smoke test only — sequential is fine
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    headless: true,
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // The smoke test is allowed to start its own servers; the dev-server
  // config below is unused by default (the smoke test's beforeAll
  // handles backend startup) but kept for `npx playwright test --ui`
  // or future expansions.
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
