/**
 * Deterministic browser journey for the Phase 5 operational archive.
 * All API responses are intercepted synthetic fixtures: this test never
 * starts a provider request, reads a personal portfolio, or sends email.
 */
import { expect, test } from '@playwright/test'

const brief = {
  generated_at: '2026-08-11T12:00:00Z',
  sections: [
    { name: 'portfolio_changes', content: ['AAPL: 10'], citations: [{ provider: 'synthetic', source_url: 'https://source.test/quote', freshness: 'fresh' }] },
    { name: 'earnings', content: ['upcoming: AAPL earnings on 2026-08-12'], citations: [{ provider: 'synthetic', source_url: 'https://source.test/earnings', freshness: 'fresh' }] },
  ],
  warnings: ['SEC filings omitted: no authoritative holding-to-CIK mapping.'],
  actions: [{ action: 'Review AAPL', why: 'Deterministic review only.', goal_linkage: 'No goal linkage is inferred.', evidence: ['AAPL'], expected_impact: 'No execution or return is implied.', risks: ['Market data may be incomplete.'], alternatives: ['Do nothing.'], confidence: 'low', approval_requirement: 'explicit_user_approval_required' }],
}

async function installBriefRoutes(page: import('@playwright/test').Page, unavailable = false) {
  let briefs: Array<{ brief_id: string; report_window: string; generated_at: string }> = []
  await page.route('**/api/v1/market-briefs', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ briefs }) }))
  await page.route('**/api/v1/market-briefs/generate', route => {
    if (unavailable) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ code: 'market_brief_unavailable' }) })
    expect(route.request().postDataJSON()).toEqual({ report_window: 'latest' })
    briefs = [{ brief_id: 'brief-1', report_window: 'latest', generated_at: brief.generated_at }]
    return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ brief_id: 'brief-1', replayed: false, brief }) })
  })
  await page.route('**/api/profile/**', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 1, email: 'synthetic@example.test', full_name: 'Synthetic User' }) }))
}

async function authenticateSyntheticBrowser(page: import('@playwright/test').Page, request: import('@playwright/test').APIRequestContext) {
  // Use the isolated Rules Service's test-only dev-login endpoint once, then
  // seed the browser token before React mounts. This avoids relying on timing
  // of the visual bootstrap splash while keeping all brief endpoints mocked.
  const login = await request.post('http://localhost:8000/api/auth/devlogin?sub=alex')
  expect(login.ok(), 'isolated test auth bootstrap should succeed').toBeTruthy()
  const token = (await login.json()).token as string
  await page.addInitScript((value) => window.localStorage.setItem('fc_session_token', value), token)
}

test('Market Briefs is discoverable and generates a synthetic archived detail', async ({ page, request }) => {
  await authenticateSyntheticBrowser(page, request)
  await installBriefRoutes(page)
  await page.goto('/market-briefs')
  await expect(page.getByRole('link', { name: /market briefs/i })).toBeVisible()
  await expect(page.getByText(/no market briefs exist yet/i)).toBeVisible()
  await page.getByRole('button', { name: /^generate brief$/i }).click()
  await expect(page.getByText(/generated and added to the archive/i)).toBeVisible()
  await expect(page.getByText('AAPL: 10')).toBeVisible()
  await expect(page.getByText(/upcoming: AAPL earnings/i)).toBeVisible()
  await expect(page.getByRole('link', { name: /source: synthetic/i }).first()).toHaveAttribute('href', 'https://source.test/quote')
  await expect(page.getByLabel(/data quality warnings/i)).toContainText('SEC filings omitted: no authoritative holding-to-CIK mapping.')
  await expect(page.getByRole('heading', { name: /actions to review/i })).toBeVisible()
  await expect(page.getByText('Review AAPL')).toBeVisible()
})

test('Market Briefs explains fail-closed generation unavailability', async ({ page, request }) => {
  await authenticateSyntheticBrowser(page, request)
  await installBriefRoutes(page, true)
  await page.goto('/market-briefs')
  await page.getByRole('button', { name: /^generate brief$/i }).click()
  await expect(page.getByText(/local operator to enable the required server-side configuration/i)).toBeVisible()
})
