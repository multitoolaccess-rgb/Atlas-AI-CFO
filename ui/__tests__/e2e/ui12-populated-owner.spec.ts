import { readFileSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'

/**
 * UI-12 populated-owner data proof (GAP-13).
 *
 * The frozen-surface certification spec (ui12-trust-certification.spec.ts)
 * exercises the routes with a synthetic 401 backend — that proves the
 * safe recovery states, but not that the routes render REAL data. This
 * spec seeds a deterministic synthetic single-owner dataset via route
 * interception (hermetic — no backend, no network) and proves every
 * certified route renders populated content without horizontal overflow,
 * sensitive-text leakage, or execution affordances.
 *
 * The dataset is deliberately small and stable: one account, two
 * holdings, one recommendation, one goal/scenario, one Scout run, one
 * market brief. Assertions target rendered DOM, never exact API shapes.
 */

const OWNER = {
  profile: { id: 1, email: 'alex@example.com', full_name: 'Alex' },
  summary: {
    total_balance: 14900,
    total_income_month: 6000,
    total_expenses_month: 4200,
    accounts_count: 1,
    transactions_count: 12,
    last_sync: '2026-09-04T00:00:00Z',
  },
  accounts: [
    { id: 1, account_name: 'Brokerage', account_type: 'investment', current_balance: 14900, is_active: true },
  ],
  holdings: [
    { id: 101, account_id: 1, account_name: 'Brokerage', symbol: 'AAPL', description: 'Apple Inc.', quantity: 10, last_price: 940, current_value: 9400, cost_basis_total: 7420, type: 'Stock' },
    { id: 102, account_id: 1, account_name: 'Brokerage', symbol: 'VTI', description: 'Vanguard Total Stock Market ETF', quantity: 25, last_price: 220, current_value: 5500, cost_basis_total: null, type: 'ETF' },
  ],
  valuation: {
    schema_version: 'portfolio-valuation/v1',
    grand_total: 14900,
    currency: 'USD',
    accounts: [
      { account_id: 1, account_name: 'Brokerage', account_type: 'investment', total: 14900, positions_count: 2, allocation_pct: 100 },
    ],
    holdings: [
      { holding_id: 101, symbol: 'AAPL', description: 'Apple Inc.', value: 9400, allocation_pct: 63.1, gain_pct: 26.7 },
      { holding_id: 102, symbol: 'VTI', description: 'Vanguard Total Stock Market ETF', value: 5500, allocation_pct: 36.9, gain_pct: null },
    ],
    types: [
      { type: 'Stock', total: 9400, allocation_pct: 63.1 },
      { type: 'ETF', total: 5500, allocation_pct: 36.9 },
    ],
    computed_at: '2026-09-04T00:00:00Z',
  },
}

const RECOMMENDATION = {
  schema_version: 'InvestmentRecommendationList/v1',
  items: [
    {
      recommendation_id: 'rec:populated:1',
      owner_id: 1,
      security_id: 'sec:populated:aapl',
      symbol: 'AAPL',
      recommendation_type: 'BUY',
      status: 'active',
      recommendation_hash: 'h'.repeat(64),
      committee_finding_id: 'fin:populated:1',
      recommendation_as_of: '2026-09-01T00:00:00Z',
      thesis: 'Apple trades at a reasonable multiple with durable cash generation.',
      conviction: 'moderate',
      risks: ['valuation concentration'],
      invalidation_conditions: ['guidance cut'],
      review_after: '2026-10-01T00:00:00Z',
    },
  ],
}

const EVIDENCE_PACKET = {
  schema_version: 'InvestmentEvidencePacket/v1',
  packet_id: 'evp:populated:1',
  packet_hash: 'e'.repeat(64),
  owner_id: 1,
  subject_security_id: 'sec:populated:aapl',
  analysis_as_of: '2026-09-01T00:00:00Z',
  items: [
    { evidence_id: 'ev:1', category: 'fundamentals', subject_security_id: 'sec:populated:aapl', reference: { source: 'synthetic' }, excerpt: 'Synthetic fundamentals excerpt', numeric_value: '12.5' },
  ],
}

const COMMITTEE = {
  schema_version: 'InvestmentCommitteeResponse/v1',
  finding: {
    finding_id: 'fin:populated:1',
    run_id: 'run:populated:1',
    subject_security_id: 'sec:populated:aapl',
    analysis_as_of: '2026-09-01T00:00:00Z',
    thesis: 'Committee thesis: synthetic analysis of Apple.',
    uncertainty: 'low',
    dissent: [],
    methodology_version: 'committee/v1',
  },
  finding_hash: 'f'.repeat(64),
  as_of: '2026-09-01T00:00:00Z',
}

const GOALS = [
  { id: 1, name: 'Retirement', target_amount: 1000000, current_amount: 500000 },
]

const SCENARIO_LIST = {
  schema_version: 'atlas-scenario-list/v1',
  scenarios: [
    {
      scenario_id: 'scn:populated:1',
      goal_id: 'goal:retirement',
      name: 'Base case',
      lifecycle: 'active',
      comparison: {
        baseline_ending_net_worth: '500000.00',
        scenario_ending_net_worth: '520000.00',
        difference_from_baseline: '20000.00',
        baseline_target_reached: false,
        scenario_target_reached: false,
        baseline_target_gap: '500000.00',
        scenario_target_gap: '480000.00',
        target_amount: '1000000.00',
      },
    },
  ],
}

const MARKET_BRIEF = {
  brief_id: 'brief:populated:1',
  title: 'Market Pulse',
  report_window: 'latest',
  generated_at: '2026-09-04T00:00:00Z',
  as_of: '2026-09-04T00:00:00Z',
  warnings: [],
  sections: [
    { name: 'Rates', citations: [], content: ['Synthetic market context for human review.'] },
  ],
  actions: [
    { action: 'watch', why: 'Synthetic review item from the seeded owner brief.', evidence: ['synthetic-source'], risks: [] },
  ],
}

const BRIEFS = [
  { brief_id: 'brief:populated:1', title: 'Market Pulse', report_window: 'latest', generated_at: '2026-09-04T00:00:00Z' },
]

const DISCOVERY_CANDIDATES = [
  {
    candidate_id: 'discovery:populated:aapl',
    universe: 'sp500',
    security: { security_id: 'sec:populated:aapl', symbol: 'AAPL', instrument_type: 'equity', state: 'resolved' },
    status: 'candidate',
    reason: 'Member of the approved sp500 discovery universe',
    source: 'server:ui09:sp500-universe',
    as_of: '2026-09-04T00:00:00Z',
    freshness: 'unknown',
    methodology_version: 'ui09-universe-membership/v1',
    metrics: {},
    metric_states: {},
    recommendation_id: 'rec:populated:1',
    detail_available: true,
  },
]

const SCOUT_RUNS = [
  {
    schema_version: 'InvestmentScoutRunSummary/v1',
    run_id: 'run:scout:populated:1',
    security_id: 'sec:populated:aapl',
    symbol: 'AAPL',
    state: 'ready',
    as_of: '2026-09-04T00:00:00Z',
    source_count: 2,
    result_hash: 'x'.repeat(64),
  },
]

const RISK_BASELINE = {
  schema_version: 'InvestmentPortfolioBaseline/v1',
  baseline_id: 'base:populated:1',
  as_of: '2026-09-04T00:00:00Z',
  as_known_at: '2026-09-04T00:00:00Z',
  capability: 'portfolio_baseline',
  positions: [
    {
      position_id: 'pos:populated:1',
      security: { security_id: 'sec:populated:aapl', symbol: 'AAPL', state: 'resolved' },
      market_value: '9400.00',
      market_value_state: 'available',
      currency: 'USD',
      exposure_percentage: '63.09',
      exposure_state: 'available',
      source_id: 'holding:101',
      source_hash: 's'.repeat(64),
      as_of: '2026-09-04T00:00:00Z',
    },
  ],
  total_value: '14900.00',
  currency: 'USD',
  metrics: [
    { name: 'position_count', label: 'Positions', value: '2', state: 'available' },
    { name: 'observed_position_count', label: 'Observed values', value: '2', state: 'available' },
  ],
  completeness: 'complete',
  omissions: [],
  freshness: 'current',
  methodology_version: 'ui11-risk-baseline/v1',
  calculation_version: 'ui11-risk-baseline-calc/v1',
  source_ids: ['holding:101', 'holding:102'],
}

function json(route: Route, body: unknown) {
  return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
}

async function awaitEntranceSettled(page: Page) {
  // Framer-motion entrance fades keep elements below full opacity while
  // they animate; axe measures color contrast against the CURRENT
  // (mid-animation) opacity, which produces false-positive
  // color-contrast findings. Wait until every inline-opacity element in
  // the main landmark reaches opacity 1 before running axe.
  await expect.poll(() => page.evaluate(() => {
    const els = Array.from(document.querySelectorAll<HTMLElement>('#main-content [style*="opacity"]'))
    return els.every((el) => {
      const o = parseFloat(el.style.opacity || '1')
      return o >= 1
    })
  }), { timeout: 5000, message: 'entrance animations did not settle' }).toBe(true)
}

async function installPopulatedBackend(page: Page) {
  await page.route('**/health', (route) => json(route, { status: 'ok' }))
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    const method = route.request().method()

    if (path === '/api/dashboard/summary') return json(route, OWNER.summary)
    if (path === '/api/accounts/') return json(route, OWNER.accounts)
    if (path === '/api/holdings/') return json(route, OWNER.holdings)
    if (path === '/api/holdings/summary') return json(route, OWNER.valuation)
    if (path === '/api/profile/') return json(route, OWNER.profile)
    if (path === '/api/goals/') return json(route, GOALS)
    if (path.startsWith('/api/v1/goals/') && path.endsWith('/scenarios')) return json(route, SCENARIO_LIST)
    if (path.startsWith('/api/v1/goals/') && path.endsWith('/decision-history')) {
      return json(route, { schema_version: 'atlas-decision-history-envelope/v1', history: [] })
    }
    if (path.startsWith('/api/v1/scenarios/compare')) return json(route, { schema_version: 'atlas-scenario-comparison/v1', comparisons: [] })
    if (path.startsWith('/api/v1/scenarios/')) return json(route, { schema_version: 'atlas-scenario/v1', scenario: SCENARIO_LIST.scenarios[0] })
    if (path === '/api/v1/investments/discovery' || path.startsWith('/api/v1/investments/discovery?')) {
      return json(route, {
        schema_version: 'InvestmentDiscovery/v1',
        universe: 'sp500',
        as_of: '2026-09-04T00:00:00Z',
        methodology_version: 'ui09-universe-membership/v1',
        source_scope: 'server-owned-current-only',
        omitted_count: 0,
        candidates: DISCOVERY_CANDIDATES,
      })
    }
    if (path.startsWith('/api/v1/investments/discovery/')) return json(route, { candidate: DISCOVERY_CANDIDATES[0] })
    if (path === '/api/v1/investments/recommendations') return json(route, RECOMMENDATION)
    if (path.includes('/recommendations/') && path.endsWith('/evidence')) return json(route, EVIDENCE_PACKET)
    if (path.includes('/recommendations/') && path.endsWith('/decisions')) return json(route, { schema_version: 'InvestmentDecisionList/v1', items: [] })
    if (path.includes('/recommendations/') && path.endsWith('/outcomes')) return json(route, { schema_version: 'InvestmentOutcomeList/v1', items: [] })
    if (path.includes('/committee/findings/')) return json(route, COMMITTEE)
    if (path === '/api/v1/market-briefs') return json(route, { briefs: BRIEFS })
    if (path === '/api/v1/market-briefs/pulse') return json(route, { pulse: 'stable', as_of: '2026-09-04T00:00:00Z' })
    if (path.startsWith('/api/v1/market-briefs/generate')) return json(route, { brief_id: 'brief:populated:1', replayed: false, brief: MARKET_BRIEF })
    if (path.startsWith('/api/v1/market-briefs/')) return json(route, { brief: MARKET_BRIEF })
    if (path === '/api/v1/investments/scout/runs' && method === 'GET') return json(route, SCOUT_RUNS)
    if (path.startsWith('/api/v1/investments/scout/runs/')) return json(route, SCOUT_RUNS[0])
    if (path === '/api/v1/investments/portfolio-risk/baseline') return json(route, RISK_BASELINE)
    if (path === '/api/v1/investments/portfolio-risk/scenarios/preview') {
      return json(route, {
        schema_version: 'RiskScenarioPreview/v1',
        hypothetical: true,
        as_of: '2026-09-04T00:00:00Z',
        evaluated_at: '2026-09-04T00:00:00Z',
        result_hash: 'r'.repeat(64),
        methodology_version: 'ui11-risk-preview/v1',
        calculation_version: 'ui11-risk-preview-calc/v1',
        metrics: [{ name: 'impact', label: 'Impact', value: '25.00', state: 'available' }],
        limitations: [],
        warnings: [],
      })
    }
    if (path === '/api/v1/investments/assistant/context' || path === '/api/v1/investments/assistant/query' || path === '/api/v1/investments/scout/research') {
      return json(route, { schema_version: 'assistant/v1', ok: true })
    }
    // Unknown endpoints resolve to an empty list so routes degrade to
    // their (already certified) empty states rather than error banners.
    return json(route, [])
  })
}

const POPULATED_ROUTES = [
  { path: '/investments', heading: 'Command Center', expectText: 'Start with the signal' },
  { path: '/investments/discovery', heading: 'Opportunity discovery', expectText: 'AAPL' },
  { path: '/investments/brief', heading: 'Daily Investment Brief', expectText: 'What matters today' },
  { path: '/investments/recommendations', heading: 'Recommendation review', expectText: 'BUY' },
  { path: '/investments/assistant', heading: 'Investment Scout', expectText: /scout|research|question/i },
  { path: '/investments/scout', heading: 'Investment Context Scout', expectText: 'AAPL' },
  { path: '/investments/risk', heading: 'Risk and scenario views', expectText: 'AAPL' },
  { path: '/scenario-lab', heading: 'Scenario Lab', expectText: 'Retirement' },
  { path: '/decisions', heading: 'Decisions', expectText: 'No recommendations to review' },
  { path: '/market-intelligence', heading: /market intelligence/i, expectText: 'Market Pulse' },
  { path: '/portfolio', heading: 'Portfolio', expectText: 'AAPL' },
] as const

test.describe('UI-12 populated single-owner data proof', () => {
  test.beforeEach(async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await installPopulatedBackend(page)
  })

  test('every certified route renders populated owner data without overflow or leaks', async ({ page }) => {
    const executionRequests: string[] = []
    page.on('request', (request) => {
      if (/broker|order|trade|transfer|rebalance|execute|money-movement/i.test(request.url())) executionRequests.push(request.url())
    })

    for (const route of POPULATED_ROUTES) {
      await page.setViewportSize({ width: 390, height: 844 })
      await page.goto(`${route.path}${route.path.includes('?') ? '&' : '?'}skip-splash=1`, { waitUntil: 'domcontentloaded' })
      await expect(page.locator('#main-content h1').first()).toBeVisible()
      await expect(page.locator('#main-content h1').first()).toContainText(route.heading)

      // Populated proof: the route renders the seeded dataset, not the
      // empty or error state.
      await expect(page.locator('#main-content')).toContainText(route.expectText)

      const layout = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
        sensitiveText: document.body.innerText,
      }))
      expect(layout.scrollWidth, `${route.path} populated horizontal overflow`).toBeLessThanOrEqual(layout.clientWidth)
      expect(layout.sensitiveText).not.toMatch(/account:\d+|account_number|hashed_password|api[_-]?key/i)
      await expect(page.getByRole('button', { name: /^(buy|sell|execute|place order|trade|rebalance|transfer|move money)/i })).toHaveCount(0)
      await expect(page.getByRole('link', { name: /^(buy|sell|execute|place order|trade|rebalance|transfer|move money)/i })).toHaveCount(0)
    }

    expect(executionRequests).toEqual([])
  })

  test('portfolio defaults to read-only with mutation controls gated behind manage mode', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/portfolio?skip-splash=1', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('#main-content h1').first()).toContainText('Portfolio')

    // Populated holdings render in the default read-only view.
    await expect(page.locator('#main-content')).toContainText('AAPL')
    await expect(page.locator('#main-content')).toContainText('VTI')
    // Server-owned totals render (GAP-12): allocation %, gain %, total.
    await expect(page.locator('#main-content')).toContainText('63.1%')

    // Read-only by default (GAP-11): mutation controls are absent.
    await expect(page.getByRole('button', { name: 'Manage portfolio' })).toBeVisible()
    await expect(page.getByRole('button', { name: /Import Portfolio/ })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Refresh Prices' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Add Holding' })).toHaveCount(0)
    await expect(page.locator('#auto-refresh-minutes')).toHaveCount(0)
    await expect(page.locator('[data-testid^="holding-edit-"]')).toHaveCount(0)
    await expect(page.locator('[data-testid^="holding-delete-"]')).toHaveCount(0)

    // Manage mode reveals the gated mutation controls.
    await page.getByRole('button', { name: 'Manage portfolio' }).click()
    // The file input inside the import label also exposes role=button,
    // so target the rendered Button element explicitly.
    await expect(page.locator('button', { hasText: 'Import Portfolio' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Refresh Prices' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Add Holding' })).toBeVisible()
    await expect(page.locator('#auto-refresh-minutes')).toBeVisible()
    await expect(page.locator('[data-testid^="holding-edit-"]').first()).toBeVisible()

    // No horizontal overflow in either mode.
    const layout = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }))
    expect(layout.scrollWidth).toBeLessThanOrEqual(layout.clientWidth)
  })

  test('recommendation review shows committee and evidence context for the seeded recommendation', async ({ page }) => {
    await page.goto('/investments/recommendations?skip-splash=1', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('#main-content h1').first()).toContainText('Recommendation review')
    await expect(page.locator('#main-content')).toContainText('BUY')
    await expect(page.locator('#main-content')).toContainText('moderate')
    await expect(page.locator('#main-content')).toContainText('durable cash generation')

    await page.getByRole('button', { name: 'Load committee and history' }).first().click()
    await expect(page.locator('#main-content')).toContainText('Committee thesis')
    await expect(page.locator('#main-content')).toContainText('low')

    await page.getByRole('button', { name: 'Review evidence' }).first().click()
    await expect(page.locator('#main-content')).toContainText('Category: fundamentals')
  })

  test('accessibility: no serious or critical violations on populated routes', async ({ page }) => {
    for (const route of POPULATED_ROUTES) {
      await page.setViewportSize({ width: 390, height: 844 })
      await page.goto(`${route.path}${route.path.includes('?') ? '&' : '?'}skip-splash=1`, { waitUntil: 'domcontentloaded' })
      // Guarantee the page shell is hydrated before axe runs — the main
      // landmark is absent during the brief splash/loading window.
      await expect(page.locator('#main-content h1').first()).toBeVisible()
      await awaitEntranceSettled(page)
      await page.addScriptTag({ content: readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8') })
      const result = await page.evaluate(async () => {
        const axe = (window as unknown as {
          axe: { run: (context: Element) => Promise<{ violations: Array<{ id: string; impact?: string | null }> }> }
        }).axe
        const main = document.querySelector('main')
        if (!main) throw new Error('Expected main landmark')
        return axe.run(main)
      })
      expect(
        result.violations.filter((violation) => violation.impact === 'serious' || violation.impact === 'critical'),
        `${route.path} populated serious/critical accessibility findings`,
      ).toEqual([])
    }
  })
})