/**
 * Deterministic browser journey for the Phase 5 operational archive.
 * All API responses are intercepted synthetic fixtures: this test never
 * starts a provider request, reads a personal portfolio, or sends email.
 */
import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'

const brief = {
  generated_at: '2026-08-11T12:00:00Z',
  as_of: '2026-08-11T12:00:00Z',
  market_data_basis: 'prior_close',
  provider_readiness: { provider: 'market_data', status: 'ready' },
  portfolio_daily_change: '10',
  coverage: {
    eligible_holding_count: 1,
    covered_holding_count: 1,
    omitted_holding_count: 0,
    coverage_basis: 'value_weighted',
    coverage_percentage: '1',
    minimum_required_percentage: '0.8',
    omitted_symbols: [],
    omissions: [],
  },
  sections: [
    { name: 'portfolio_changes', content: ['AAPL: 10'], citations: [{ provider: 'synthetic', source_url: 'https://source.test/quote', freshness: 'fresh' }] },
    { name: 'earnings', content: ['upcoming: AAPL earnings on 2026-08-12'], citations: [{ provider: 'synthetic', source_url: 'https://source.test/earnings', freshness: 'fresh' }] },
  ],
  warnings: ['SEC filings omitted: no authoritative holding-to-CIK mapping.'],
  actions: [{ action: 'Review AAPL', why: 'Deterministic review only.', goal_linkage: 'No goal linkage is inferred.', evidence: ['AAPL'], expected_impact: 'No execution or return is implied.', risks: ['Market data may be incomplete.'], alternatives: ['Do nothing.'], confidence: 'low', approval_requirement: 'explicit_user_approval_required' }],
}

async function installBriefRoutes(page: import('@playwright/test').Page, unavailable = false, fixture = brief, initialBriefs: Array<{ brief_id: string; report_window: string; generated_at: string }> = []) {
  const state = { generated: 0 }
  let briefs = [...initialBriefs]
  await page.route('**/api/v1/market-briefs', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ briefs }) }))
  await page.route('**/api/v1/market-briefs/*', route => {
    const id = route.request().url().split('/').pop()
    if (!id || id === 'generate') return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ brief: fixture, brief_id: id }) })
  })
  await page.route('**/api/v1/market-briefs/generate', route => {
    state.generated += 1
    if (unavailable) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ code: 'market_brief_generation_unavailable', reason_code: 'provider_configuration_missing' }) })
    expect(route.request().postDataJSON()).toEqual({ report_window: 'latest' })
    briefs = [{ brief_id: 'brief-1', report_window: 'latest', generated_at: fixture.generated_at }]
    return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ brief_id: 'brief-1', replayed: false, brief: fixture }) })
  })
  await page.route('**/api/profile/**', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 1, email: 'synthetic@example.test', full_name: 'Synthetic User' }) }))
  return state
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

test('Market Intelligence auto-generates on first visit and renders the synthetic archived detail', async ({ page, request }) => {
  await authenticateSyntheticBrowser(page, request)
  const state = await installBriefRoutes(page)
  // The legacy URL remains a bookmark-compatible redirect; Market Intelligence
  // is the single authoritative destination and no Market Briefs nav link is
  // reintroduced.
  await page.goto('/market-briefs')
  await expect(page).toHaveURL(/\/market-intelligence$/)
  await expect(page.getByRole('link', { name: /market briefs/i })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: /market intelligence/i })).toBeVisible()
  // Empty archive: the brief is generated automatically once on first visit.
  await expect(page.getByText(/generated and added to the archive/i)).toBeVisible()
  expect(state.generated).toBe(1)
  // Manual Generate remains the explicit refresh path.
  await page.getByRole('button', { name: /^generate brief$/i }).click()
  await expect(page.getByText(/generated and added to the archive/i)).toBeVisible()
  expect(state.generated).toBe(2)
  await expect(page.getByText('AAPL: 10')).toBeVisible()
  await expect(page.getByText(/upcoming: AAPL earnings/i)).toBeVisible()
  await expect(page.getByRole('link', { name: /synthetic source/i }).first()).toHaveAttribute('href', 'https://source.test/quote')
  await expect(page.getByText(/prior close/i).first()).toBeVisible()
  await expect(page.getByRole('heading', { name: /data-quality limitations/i })).toBeVisible()
  await expect(page.getByText('SEC filings omitted: no authoritative holding-to-CIK mapping.')).toBeVisible()
  await expect(page.getByRole('heading', { name: /actions to review/i })).toBeVisible()
  await expect(page.getByText('Review AAPL')).toBeVisible()
  await expect(page.getByText('100%').first()).toBeVisible()

  const axeSource = readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8')
  await page.addScriptTag({ content: axeSource })
  const axeResult = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (context: Element) => Promise<{ violations: Array<{ impact?: string | null }> }> } }).axe
    const root = document.querySelector('main')
    if (!root) throw new Error('Market Brief main landmark was not rendered')
    return axe.run(root)
  })
  expect(axeResult.violations.filter(violation => violation.impact === 'serious' || violation.impact === 'critical')).toEqual([])

})

test('Market Intelligence header stays full-bleed and overflow-free on mobile', async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await authenticateSyntheticBrowser(page, request)
  await installBriefRoutes(page)
  await page.goto('/market-briefs')
  await expect(page.getByRole('heading', { name: /market intelligence/i })).toBeVisible()
  const mobileLayout = await page.evaluate(() => {
    const header = document.querySelector('header#header')
    const root = document.documentElement
    if (!header) throw new Error('Market Intelligence header was not rendered')
    return { headerWidth: Math.round(header.getBoundingClientRect().width), viewportWidth: window.innerWidth, scrollWidth: root.scrollWidth, clientWidth: root.clientWidth }
  })
  expect(mobileLayout.headerWidth).toBe(mobileLayout.viewportWidth)
  expect(mobileLayout.scrollWidth).toBeLessThanOrEqual(mobileLayout.clientWidth)
})

test('degraded provider status remains accessible in dark mode', async ({ page, request }) => {
  await authenticateSyntheticBrowser(page, request)
  await installBriefRoutes(page, false, { ...brief, provider_readiness: { provider: 'market_data', status: 'degraded' } })
  await page.goto('/market-briefs')
  await page.getByRole('button', { name: /^generate brief$/i }).click()
  await expect(page.getByText('Coverage limited', { exact: true })).toBeVisible()
  // Keep the axe fixture deterministic by honoring a reduced-motion test surface.
  await page.addStyleTag({ content: '*, *::before, *::after { transition: none !important; animation: none !important; }' })
  await page.getByRole('button', { name: /switch to dark mode/i }).click()
  await expect(page.getByRole('button', { name: /switch to light mode/i })).toBeVisible()
  const axeSource = readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8')
  await page.addScriptTag({ content: axeSource })
  const axeResult = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (context: Element) => Promise<{ violations: Array<{ id: string; impact?: string | null }> }> } }).axe
    const root = document.querySelector('main')
    if (!root) throw new Error('Market Brief main landmark was not rendered')
    return axe.run(root)
  })
  expect(axeResult.violations.filter(violation => violation.impact === 'serious' || violation.impact === 'critical')).toEqual([])
})

test('Market Briefs explains fail-closed generation unavailability', async ({ page, request }) => {
  await authenticateSyntheticBrowser(page, request)
  await installBriefRoutes(page, true)
  await page.goto('/market-briefs')
  await page.getByRole('button', { name: /^generate brief$/i }).click()
  await expect(page.getByText(/ask the local operator to configure the provider/i)).toBeVisible()
})

test('return visits reopen the cached brief without regenerating', async ({ page, request }) => {
  await authenticateSyntheticBrowser(page, request)
  const state = await installBriefRoutes(page, false, brief, [{ brief_id: 'brief-1', report_window: 'latest', generated_at: brief.generated_at }])
  await page.goto('/market-briefs')
  // The cached brief is fetched and opened on mount — zero provider calls.
  await expect(page.getByText('AAPL: 10')).toBeVisible()
  await expect(page.getByText(/upcoming: AAPL earnings/i)).toBeVisible()
  expect(state.generated).toBe(0)
})
