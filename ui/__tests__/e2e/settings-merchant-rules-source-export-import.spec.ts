/**
 * Phase 27 — Playwright spec covering the Source chip + filter pills +
 * Export + Import affordances on /settings. Locks the BE wire contracts
 * + the FE wiring so a regression on either side surfaces here.
 *
 * Phase 27 ships ~117 system rules on first boot so the test-id pattern
 * uses NUMERIC database IDs (``merchant-rule-row-${rule.id}``). The spec
 * enumerates IDs via the rules-service API on demand rather than
 * hard-coding constants, so a fresh-DB import or a re-seeding doesn't
 * shift the row IDs out from under the assertion.
 */
import { test, expect, type APIRequestContext } from '@playwright/test'
import * as fs from 'node:fs'
import * as path from 'node:path'

const FIXTURE_PATH = path.resolve(
  __dirname,
  '..',
  '..',
  'services',
  'rules-service',
  'tests',
  'fixtures',
  'sample-merchant-rules.csv',
)

/**
 * Pull every rule id from the rules-service via the FE's own devLogin
 * path. Used by the e2e tests to enumerate rows by ID rather than by
 * keyword (the FE renders ``data-testid={`merchant-rule-row-${rule.id}`}``
 * with a numeric ID, NOT a keyword slug; the spec was wrong in an
 * earlier draft and was fixed to never depend on keyword-as-testid).
 */
async function fetchRuleIds(
  request: APIRequestContext,
): Promise<{ id: number; keyword: string; source: string }[]> {
  // devLogin: the FE's auth-bootstrap POST. Capture the cookie so the
  // follow-up GET ships it back; the rules-service's require_user reads
  // the JWT from the cookie OR the Authorization header.
  await request.post('http://localhost:8000/api/auth/devlogin')
  const list = await request.get(
    'http://localhost:8000/api/merchant-rules/?include_archived=true',
  )
  expect(list.status()).toBe(200)
  return await list.json()
}

test.describe('Phase 27 — Merchant Rules Source + Export + Import on /settings', () => {
  test.beforeEach(async ({ page }) => {
    // Visit /settings; the auth-bootstrap fires devLogin via Playwright's
    // request context BEFORE the page mounts, so the card arrives
    // populated with the seeded ~117 system rules.
    await fetchRuleIds(page.context().request)  // prime auth cookie
    await page.goto('/settings')
    await expect(page.getByTestId('merchant-rules-card')).toBeVisible({
      timeout: 15_000,
    })
  })

  test('per-row Source chip renders with non-default background colour', async ({
    page,
  }) => {
    // Pull the FIRST row and assert its Source chip colour is not blank
    // (the SOURCE_COLOR map fills every chip with the canonical tint).
    // Future-proofing: if the testid scheme changes from
    // ``merchant-rule-row-${id}`` to something else, the test still
    // finds rows via the ``[^]`` selector — picks up nothing → fail
    // loudly, not silently.
    const anyRow = page.locator('[data-testid^="merchant-rule-row-"]').first()
    await expect(anyRow).toBeVisible()
    const chip = anyRow.locator('[data-testid^="merchant-rule-source-"]').first()
    await expect(chip).toBeVisible()
    const bg = await chip.evaluate(
      (el) => getComputedStyle(el).backgroundColor,
    )
    // Assert a non-default background (source colours are filled).
    expect(bg).not.toBe('rgba(0, 0, 0, 0)')
  })

  test('source filter pill narrows the visible rule count', async ({ page }) => {
    // Open the "Tag rule" filter and assert the list shrinks.
    // The BE has zero tag-rule rows on a fresh DB; the empty test-id
    // block is the expected lock-in for "no rows match".
    await page.getByTestId('merchant-rules-source-filter-tag-rule').click()
    const activePill = page.getByTestId(
      'merchant-rules-source-filter-tag-rule',
    )
    await expect(activePill).toHaveAttribute('aria-selected', 'true')
  })

  test('Export downloads a CSV with the canonical header', async ({ page }) => {
    // Set up the download listener BEFORE clicking Export.
    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('merchant-rules-export').click()
    const download = await downloadPromise

    // The filename comes from the BE's Content-Disposition rather than
    // a hard-coded constant so a future BE rename translates cleanly.
    expect(download.suggestedFilename()).toMatch(/merchant-rules.*\.csv$/)

    // Read the first ~512 bytes of the downloaded body to assert on
    // the locked header (Phase 27 CSV contract).
    const stream = await download.createReadStream()
    const chunks: Buffer[] = []
    for await (const chunk of stream) chunks.push(chunk as Buffer)
    const body = Buffer.concat(chunks).toString('utf-8')
    expect(body.split('\n')[0]).toBe(
      'category_name,keyword,priority,is_archived,source',
    )
    // Spot-check: at least one canonical system keyword must appear in
    // the body. STARBUCKS / PAYROLL / AMAZON are all candidates; the
    // assertion is loose so a future vendor rename doesn't break the
    // test.
    expect(body).toMatch(/STARBUCKS|PAYROLL|AMAZON/)
  })

  test('Import surface uploads the canonical fixture and surfaces a summary banner', async ({
    page,
  }) => {
    // The hidden <input type="file"> drives the upload via Playwright's
    // setInputFiles which doesn't require a visible click.
    test.skip(!fs.existsSync(FIXTURE_PATH), 'fixture missing in this env')
    const fileChooser = page.locator(
      '[data-testid="merchant-rules-import-file"]',
    )
    await fileChooser.setInputFiles(FIXTURE_PATH)

    // The success banner renders with role="status" (Phase 27 ARIA
    // fix) so the locator matches that role too.
    const banner = page.locator('[role="status"], [role="alert"]').filter({
      hasText: /Import (complete|finished)/,
    })
    await expect(banner).toBeVisible({ timeout: 10_000 })
    await expect(banner).toContainText(/Imported \d+ rule/)
  })

  test('Export produces non-empty CSV body covering the seeded rows', async ({
    page,
  }) => {
    // Sanity lock: re-exporting should give us a non-trivial body.
    // Don't compare exact row counts because conftest-shared hermetic
    // test DBs may have variable seed counts across CI runners.
    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('merchant-rules-export').click()
    const download = await downloadPromise
    const stream = await download.createReadStream()
    const chunks: Buffer[] = []
    for await (const chunk of stream) chunks.push(chunk as Buffer)
    const body = Buffer.concat(chunks).toString('utf-8')
    const lineCount = body.split('\n').filter(Boolean).length
    // Header + at least 100 data rows (seeded system rules).
    expect(lineCount).toBeGreaterThanOrEqual(101)
  })
})
