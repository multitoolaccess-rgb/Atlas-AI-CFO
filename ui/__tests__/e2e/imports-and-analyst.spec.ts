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
  await page.goto('/data-connections')
  await expect(page.locator('h1', { hasText: /data connections/i }).first()).toBeVisible()
  await page.getByRole('tab', { name: 'Imports', exact: true }).click()

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

  // Auto-detection intentionally pauses when the synthetic fixture does not
  // identify an account type. Complete that explicit prompt before asserting
  // the finalized success state.
  const typePrompt = page.locator('[data-testid="import-type-prompt"]')
  await expect(typePrompt).toBeVisible({ timeout: 10_000 })
  await page.locator('[data-testid="import-type-prompt-skip"]').click()

  // Warning-bearing imports render the finalized result as a preview card
  // plus an import-warning alert rather than a role=status paragraph.
  await expect(page.locator('[data-testid="import-preview"]')).toBeVisible({ timeout: 10_000 })
  await expect(page.locator('[data-testid="import-preview"]')).toContainText(/Transactions saved/i)
  await expect(page.locator('[data-testid="import-preview"]')).toContainText(/5 txns/i)

  // Wait for the history row.
  const historyRow = page.locator('[data-testid^="import-history-row-"]').filter({
    hasText: 'sample-bank-statement.csv',
  }).first()
  await expect(historyRow).toBeVisible({ timeout: 5_000 })
  const historyTestId = await historyRow.getAttribute('data-testid')
  const batchId = historyTestId?.replace('import-history-row-', '')
  expect(batchId).toBeTruthy()
  await expect(historyRow).toBeVisible({ timeout: 5000 })

  // Click Delete \u2192 inline confirm row appears.
  await page.locator(`[data-testid="import-history-delete-${batchId}"]`).click()
  const confirmRow = page.locator(`[data-testid="import-history-confirm-${batchId}"]`)
  await expect(confirmRow).toBeVisible()

  // Click Cancel \u2192 confirm row hides.
  await page.locator('button:has-text("Cancel")').first().click()
  await expect(confirmRow).toBeHidden()

  // Verify the batch is still in history (Cancel shouldn't have deleted it).
  await expect(historyRow).toBeVisible()

  // Click Delete \u2192 Confirm this time.
  await page.locator(`[data-testid="import-history-delete-${batchId}"]`).click()
  await expect(confirmRow).toBeVisible()
  await page.locator(`[data-testid="import-history-confirm-delete-${batchId}"]`).click()

  // History is now empty (the row was deleted).
  // Wait a beat for the success status / history refresh.
  await page.waitForTimeout(500)
  // The exact deleted batch row should be gone from the DOM. Do not reuse
  // the filename filter here: older synthetic uploads may share the same
  // filename and should remain untouched.
  await expect(
    page.locator(`[data-testid="import-history-row-${batchId}"]`),
  ).toHaveCount(0, { timeout: 5_000 })
})

test('legacy Recommendations opens the canonical Decisions recovery state', async ({ page }) => {
  await login(page)
  await page.goto('/recommendations')

  await expect(page).toHaveURL(/\/decisions\?view=recommendations/)
  await expect(page.getByRole('heading', { name: 'Decisions', level: 1 })).toBeVisible()
  // The derived recommendation read path is server-owned and may be
  // unavailable by policy. The page must show honest recovery copy rather
  // than fabricate a recommendation or expose the retired analyst panel.
  await expect(page.getByRole('heading', { name: 'No recommendations to review' })).toBeVisible()
  await expect(page.getByText(/new recommendations appear only when the server has current evidence/i)).toBeVisible()
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
  await page.goto('/data-connections')
  await page.getByRole('tab', { name: 'Imports', exact: true }).click()

  const csvPath = path.join(
    PROJECT_ROOT,
    'services/rules-service/tests/fixtures/sample_statements/checking_stmt.csv',
  )

  await page.locator('[data-testid="import-file-input"]').setInputFiles(csvPath)
  await page.locator('[data-testid="import-submit"]').click()

  // Complete the explicit account-type prompt raised by this synthetic
  // fixture before asserting the finalized success state.
  await expect(page.locator('[data-testid="import-type-prompt"]')).toBeVisible({ timeout: 10_000 })
  await page.locator('[data-testid="import-type-prompt-skip"]').click()

  // The finalized preview appears — proving the upload completed without
  // a 5xx response. A historical NameError regression bubbled a 500 to
  // the FE; the preview would not appear in that case.
  const preview = page.locator('[data-testid="import-preview"]')
  await expect(preview).toBeVisible({ timeout: 15_000 })
  await expect(preview).toContainText(/Transactions saved/i)
  await expect(preview).toContainText(/505 txns/i)

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
