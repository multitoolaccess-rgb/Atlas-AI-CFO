/**
 * Playwright E2E for Phase 9: upload CSV, see it in history, gate-delete
 * via inline confirm, navigate to /recommendations and load analyst
 * ratings. Mocks the BE analyst-ratings endpoint with a canned payload
 * via ``page.route()`` so the test doesn't depend on a real Finnhub
 * API key.
 *
 * Run via: ``npx playwright install chromium && npx playwright test``
 * (Sequential \u2014 fullyParallel=false in playwright.config.ts.)
 */

import { test, expect, type Page } from '@playwright/test'
import * as path from 'node:path'

// Phase 18 — project-root resolution that's portable across CI + local.
// Spec lives at ``ui/__tests__/e2e/imports-and-analyst.spec.ts``;
// three levels of ``..`` from ``__dirname`` cracks up to the repo root.
// ``PROJECT_ROOT`` env var override is retained for unusual ops scenarios.
const PROJECT_ROOT =
  process.env.PROJECT_ROOT ?? path.resolve(__dirname, '../../..')

test.beforeEach(async ({ page }) => {
  // Mock the analyst-ratings endpoint at the network layer so we don't
  // need a real FINNHUB_API_KEY in the test environment.
  await page.route('**/api/analyst-ratings/*', async (route) => {
    const url = route.request().url()
    const symbol = url.split('/analyst-ratings/').pop() ?? 'AAPL'
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        symbol,
        recommendation_trends: [
          { period: '2025-05', strongBuy: 12, buy: 18, hold: 7, sell: 1, strongSell: 0 },
          { period: '2025-04', strongBuy: 10, buy: 16, hold: 9, sell: 1, strongSell: 0 },
        ],
        price_target: { targetMean: 232.10, targetMedian: 230, targetHigh: 280, targetLow: 165 },
      }),
    })
  })
})

async function login(page: Page) {
  // The dev-login route mints a JWT for settings.local_user. The
  // UI's rulesService.devLogin posts here in setup_login calls.
  await page.goto('/')
  // The auth-bootstrap is owned by the AppShell/profileloader; give
  // it a beat to call /api/auth/devlogin.
  await page.waitForLoadState('networkidle')
}

test('upload CSV, see in history, delete via 2-step confirm', async ({ page }) => {
  await login(page)

  // Navigate to the Accounts tab where ImportStatementUpload lives.
  await page.goto('/accounts')
  await expect(page.locator('h1', { hasText: /accounts/i }).first()).toBeVisible()

  // Pick the file at the file input. Resolved from the project root
  // (PROJECT_ROOT env var or process.cwd()) so the test works on
  // any developer laptop AND in CI without hardcoding an absolute
  // path that breaks on a fresh clone.
  const csvPath = path.join(
    PROJECT_ROOT,
    'services/rules-service/tests/fixtures/sample-bank-statement.csv',
  )
  await page.locator('[data-testid="import-file-input"]').setInputFiles(csvPath)

  await page.locator('[data-testid="import-submit"]').click()

  // Wait for the success banner.
  await expect(page.locator('p[role="status"]')).toContainText(/transaction/i, { timeout: 10000 })

  // Wait for the history row.
  const historyRow = page.locator('[data-testid="import-history-row-1"]')
  await expect(historyRow).toBeVisible({ timeout: 5000 })

  // Click Delete \u2192 inline confirm row appears.
  await page.locator('[data-testid="import-history-delete-1"]').click()
  const confirmRow = page.locator('[data-testid="import-history-confirm-1"]')
  await expect(confirmRow).toBeVisible()

  // Click Cancel \u2192 confirm row hides.
  await page.locator('button:has-text("Cancel")').first().click()
  await expect(confirmRow).toBeHidden()

  // Verify the batch is still in history (Cancel shouldn't have deleted it).
  await expect(historyRow).toBeVisible()

  // Click Delete \u2192 Confirm this time.
  await page.locator('[data-testid="import-history-delete-1"]').click()
  await expect(confirmRow).toBeVisible()
  await page.locator('[data-testid="import-history-confirm-delete-1"]').click()

  // History is now empty (the row was deleted).
  // Wait a beat for the success status / history refresh.
  await page.waitForTimeout(500)
  // The row should be gone from the DOM.
  await expect(historyRow).not.toBeVisible({ timeout: 5000 })
})

test('analyst-ratings panel on /recommendations loads via FE', async ({ page }) => {
  await login(page)
  await page.goto('/recommendations')

  await expect(page.locator('h1', { hasText: /AI Recommendations/i })).toBeVisible()

  // Analyst Insights section is present.
  await expect(page.locator('[data-testid="analyst-section"]')).toBeVisible()

  // Type a ticker + click Load.
  await page.locator('[data-testid="analyst-ticker-input"]').fill('AAPL')
  await page.locator('[data-testid="analyst-load-btn"]').click()

  // Wait for the rendered breakdown.
  await expect(page.locator('[data-testid="analyst-symbol"]')).toContainText(
    'AAPL',
    { timeout: 10000 },
  )
  // Aggregate counts: latest month buy=30, hold=7, sell=1
  await expect(page.locator('[data-testid="analyst-price-target"]')).toContainText(
    '232',
  )
})

/**
 * Phase 18 regression — upload checking_stmt.csv end-to-end via the
 * UI. Locks the no-NameError-on-every-upload regression: a user-uploaded
 * Wells Fargo summary-header CSV must successfully land in the import
 * history + persist 505 transactions + the auto-categorize block
 * must NOT 500 the response (this is exactly the production bug we
 * caught).
 *
 * Uses the SAME fixture the BE tests use
 * (``services/rules-service/tests/fixtures/sample_statements/checking_stmt.csv``)
 * so the e2e flow matches the unit-integration tests' input.
 */
test('upload checking_stmt.csv via UI persists + auto-categorises without 500', async ({ page, request }) => {
  await login(page)
  await page.goto('/accounts')

  const csvPath = path.join(
    PROJECT_ROOT,
    'services/rules-service/tests/fixtures/sample_statements/checking_stmt.csv',
  )

  await page.locator('[data-testid="import-file-input"]').setInputFiles(csvPath)
  await page.locator('[data-testid="import-submit"]').click()

  // The success banner appears — proving the upload completed without
  // a 5xx response. A historical NameError regression bubbled a 500 to
  // the FE; the toast would not appear in that case.
  const status = page.locator('p[role="status"]')
  await expect(status).toBeVisible({ timeout: 15000 })
  await expect(status).toContainText(/transaction|upload/i)

  // Round-trip: a fresh GET against the BE confirms the 505-row batch
  // was actually persisted, not just that the UI shim succeeded.
  const cookieHeader = (await page.context().cookies())
    .map((c) => `${c.name}=${c.value}`)
    .join('; ')
  const batches = await request.get('http://localhost:8000/api/imports/batches', {
    headers: { cookie: cookieHeader },
  })
  expect(batches.status()).toBe(200)
  const body = (await batches.json()) as Array<{ filename: string; saved_transactions: number }>
  const uploaded = body.find((b) => b.filename === 'checking_stmt.csv')
  expect(uploaded, 'checking_stmt.csv batch should appear in history').toBeTruthy()
  expect(uploaded!.saved_transactions).toBe(505)
})
