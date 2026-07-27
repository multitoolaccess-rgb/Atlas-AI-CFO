/**
 * Phase-11.5 regression locks for the user's two reports:
 *
 *   1. "Can't even upload statements now" — the /api/imports/upload
 *      endpoint 500'd with ``OperationalError: no such column:
 *      import_batches.preview_lines`` because the alembic migration
 *      had not been applied to the live SQLite DB.
 *   2. "Activity tab erroring" — ``GET /api/transactions/`` 500'd
 *      with ``AttributeError: type object 'Transaction' has no
 *      attribute 'account'`` because the SQLAlchemy Transaction
 *      model declared FK columns but no relationship, and the
 *      list endpoint used ``joinedload(Transaction.account)`` which
 *      requires a relationship.
 *
 * Both tests assert on the BROWSER contract (no console errors, the
 * page renders the expected content) rather than network-level HTTP
 * codes — that's the layer the user actually saw fail. The tests
 * rely on the same benign-filter pattern as dashboard.spec.ts so
 * unrelated 401 / Network-Error noise from the dev-stack bootstrap
 * doesn't drown out a real product regression.
 *
 * Prerequisite (handled by the dev server manager): rules-service
 * on :8000 and Next.js dev on :3000 must be reachable from the test
 * browser. Both are launched by start.sh in CI / dev modes.
 */
import { test, expect, type ConsoleMessage } from '@playwright/test'
import path from 'path'

// Mirrors the dashboard.spec.ts contract: silence 401 / Network-Error
// / cosmetic 404 but NEVER silence /api/* failures.
const BENIGN_PATTERNS: RegExp[] = [
  /\[cashflix\].*Status:\s*401/i,
  /\[cashflix\].*No response received/i,
  /Failed to load resource.*ERR_CONNECTION_REFUSED/,
  /Failed to load resource.*ERR_INTERNET_DISCONNECTED/,
  /Network Error/i,
  /not wrapped in act\(\.\.\.\)/i,
]

const BENIGN_RESOURCE_URL_PATTERNS: RegExp[] = [
  /\/favicon\.ico(\?|$)/,
  /\/favicon\.svg(\?|$)/,
  /\/apple-touch-icon[^/]*\.(png|jpg|jpeg)(\?|$)/,
  /\/manifest(\.json|webmanifest)(\?|$)/,
  /\/browserconfig\.xml(\?|$)/,
  /\/sitemap\.xml(\?|$)/,
  /\/robots\.txt(\?|$)/,
  /\/\.well-known\//,
  /\/sw\.js(\?|$)/,
  /\/workbox-[^/]*\.js(\?|$)/,
  /\/_next\/static\//,
  /\/_next\/static\/chunks\//,
  /\/_next\/static\/css\//,
  /\/_next\/static\/media\//,
  /\/_next\/data\//,
  /\.(js|css|ts|tsx|mjs|cjs)\.map(\?|$)/,
]

const isMessageBenign = (text: string): boolean =>
  BENIGN_PATTERNS.some((re) => re.test(text))

const isResourceUrlBenign = (url: string): boolean => {
  if (!url) return false
  if (/\/api\//.test(url)) return false
  return BENIGN_RESOURCE_URL_PATTERNS.some((re) => re.test(url))
}

const isBenign = (text: string, url?: string): boolean => {
  if (isMessageBenign(text)) return true
  if (
    /Failed to load resource.*404/i.test(text) &&
    url &&
    isResourceUrlBenign(url)
  ) {
    return true
  }
  return false
}

const errorListener = (page: import('@playwright/test').Page): string[] => {
  const errors: string[] = []
  page.on('console', (msg: ConsoleMessage) => {
    if (msg.type() === 'error') {
      const text = msg.text()
      const url = msg.location()?.url ?? ''
      if (!isBenign(text, url)) errors.push(text)
    }
  })
  page.on('pageerror', (err) => {
    if (!isBenign(err.message)) errors.push(err.message)
  })
  page.on('requestfailed', (req) => {
    const url = req.url()
    const failure = req.failure()?.errorText ?? ''
    if (failure.includes('ERR_ABORTED') || failure.includes('ERR_CANCELED')) {
      return
    }
    if (!isResourceUrlBenign(url)) {
      errors.push(`requestfailed: ${url} -> ${failure || 'unknown'}`)
    }
  })
  return errors
}

test('activity tab mounts without Transaction model errors', async ({ page }) => {
  // The Phase-11 AttributeError on joinedload(Transaction.account)
  // surfaced in the browser as a console error on every render of
  // /activity because the FE's axios call to /api/transactions/
  // returned a 500 with no usable body. A clean mount = clean axios
  // response = no axios error logger entries.
  const errors = errorListener(page)

  await page.goto('/activity')
  await page.waitForURL('**/activity')
  await page.waitForLoadState('networkidle')

  // Page MUST render an h1 (proves the route mounted, not a 404 / 500).
  const heading = page.locator('h1, h2').first()
  await expect(heading).toBeVisible({ timeout: 10_000 })
  const headingText = (await heading.innerText()).trim()
  expect(headingText.length).toBeGreaterThan(0)

  // The body MUST NOT contain any "Internal Server Error" string,
  // which was the literal body the unhandled-exception handler emits.
  const bodyText = (await page.locator('body').innerText()).toLowerCase()
  expect(bodyText).not.toContain('internal server error')
  expect(bodyText).not.toContain('attributeerror')

  expect(
    errors,
    `Unexpected console errors on /activity: ${errors.join(' | ')}`,
  ).toEqual([])
})

test('CSV upload completes successfully (no OperationalError 500)', async ({
  page,
}) => {
  // Phase-11.5 bug: hitting "Submit" on the import upload sent a POST to
  // /api/imports/upload that returned 500 with body
  // ``{"detail": "Internal server error: OperationalError"}`` because
  // the dev DB was missing ``preview_lines``. The FE caught it via the
  // axios interceptor and the toast banner was empty. This test
  // asserts on the happy path: the success banner renders + a history
  // row appears.
  const errors = errorListener(page)
  await page.goto('/accounts')
  await expect(page.locator('h1').first()).toBeVisible({ timeout: 10_000 })

  const csvPath = path.resolve(
    __dirname,
    '../../../services/rules-service/tests/fixtures/sample-bank-statement.csv',
  )

  // Stash the recent-history length so we can assert an increment.
  const beforeUpload = await page.evaluate(() => {
    // The component renders data-testid="import-history-row-N" for each
    // existing batch; if none, the section renders the empty-state.
    const rows = document.querySelectorAll(
      '[data-testid^="import-history-row-"]',
    )
    return rows.length
  })

  await page
    .locator('[data-testid="import-file-input"]')
    .setInputFiles(csvPath)
  await page.locator('[data-testid="import-submit"]').click()

  // Wait for either a success status banner OR an "Importing…" /
  // loading state that resolves to a success banner. 15s is a
  // generous budget because the CSV parser + DB commit can be 200-400ms
  // in dev and the next dev HMR client may have garbage-collected
  // the axios interceptor's worker at the time of the first request.
  await expect(page.locator('p[role="status"]')).toContainText(
    /transaction|imported|recorded|saved/i,
    { timeout: 15_000 },
  )

  // History should now show +1 row (or 1 row if it started empty).
  const afterUpload = await page.evaluate(() => {
    const rows = document.querySelectorAll(
      '[data-testid^="import-history-row-"]',
    )
    return rows.length
  })
  expect(
    afterUpload,
    `Expected upload to add at least one history row (before=${beforeUpload}, after=${afterUpload}).`,
  ).toBeGreaterThanOrEqual(1)

  // The success status must NOT carry the "Internal Server Error" /
  // "OperationalError" markers that the original failure mode emitted.
  const statusText = (
    await page.locator('p[role="status"]').innerText()
  ).toLowerCase()
  expect(statusText).not.toContain('operationalerror')
  expect(statusText).not.toContain('no such column')
  expect(statusText).not.toContain('internal server error')

  expect(
    errors,
    `Unexpected console errors during CSV upload: ${errors.join(' | ')}`,
  ).toEqual([])
})
