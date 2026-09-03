import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'

const baseline = {
  schema_version: 'InvestmentPortfolioBaseline/v1',
  baseline_id: 'portfolio-baseline:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  as_of: '2026-09-01T00:00:00Z',
  as_known_at: '2026-09-01T00:00:00Z',
  capability: 'current_only',
  positions: [{
    position_id: 11,
    security: { security_id: 'sec:aapl', instrument_type: 'equity', symbol: 'AAPL', currency: null, state: 'resolved' },
    quantity: '1', market_value: '100', currency: 'USD', market_value_state: 'available', exposure_percentage: '100', exposure_state: 'available',
    cost_basis: '80', cost_basis_state: 'available', as_of: '2026-09-01T00:00:00Z',
    source_id: 'holding:11', source_hash: 'a'.repeat(64),
  }],
  total_value: '100', currency: 'USD',
  metrics: [
    { name: 'position_count', value: '1', unit: 'count', currency: null, state: 'available', limitation: null },
    { name: 'total_value', value: '100', unit: 'currency', currency: 'USD', state: 'available', limitation: null },
    { name: 'portfolio_volatility', value: null, unit: 'ratio', currency: null, state: 'unavailable', limitation: 'portfolio volatility methodology is not approved for UI-11' },
  ],
  completeness: 'complete', omissions: [], freshness: 'available',
  methodology_version: 'ui11-current-portfolio/v1', calculation_version: 'ui11-baseline/v1',
  source_ids: ['holding:11'], source_hashes: ['a'.repeat(64)], baseline_hash: 'b'.repeat(64),
}

const scenario = {
  schema_version: 'InvestmentRiskScenario/v1',
  scenario_id: 'investment-risk-scenario:' + 'c'.repeat(32),
  baseline_id: baseline.baseline_id, baseline_hash: baseline.baseline_hash,
  inputs: { schema_version: 'InvestmentRiskScenarioRequest/v1', baseline_id: baseline.baseline_id, position_id: 11, market_value_delta: '25' },
  metrics: [
    { name: 'baseline_total_value', value: '100', unit: 'currency', currency: 'USD', state: 'available', limitation: null },
    { name: 'hypothetical_total_value', value: '125', unit: 'currency', currency: 'USD', state: 'available', limitation: null },
  ],
  source_ids: baseline.source_ids, source_hashes: baseline.source_hashes,
  as_of: baseline.as_of, as_known_at: baseline.as_known_at, evaluated_at: '2026-09-01T00:01:00Z',
  methodology_version: 'ui11-exposure-preview/v1', calculation_version: 'ui11-scenario/v1',
  hypothetical: true, predictive: false, result_hash: 'd'.repeat(64),
  limitations: ['Current-only baseline'], warnings: ['Hypothetical analysis only'],
}

async function installRoutes(page: import('@playwright/test').Page) {
  await page.route('**/api/v1/investments/portfolio-risk/baseline', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(baseline) })
  })
  await page.route('**/api/v1/investments/portfolio-risk/scenarios/preview', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(scenario) })
  })
}

test.describe('UI-11 risk and scenario view', () => {
  test('renders safely across desktop and mobile widths', async ({ page }) => {
    await installRoutes(page)
    for (const width of [390, 768, 1024, 1440, 1728]) {
      await page.setViewportSize({ width, height: 900 })
      await page.goto('/investments/risk')
      await expect(page.getByRole('heading', { name: 'Current portfolio context' })).toBeVisible()
      await expect(page.getByText('current only')).toBeVisible()
      await expect(page.getByText('portfolio volatility methodology is not approved for UI-11')).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    }
  })

  test('has no serious or critical accessibility violations', async ({ page }) => {
    await installRoutes(page)
    await page.goto('/investments/risk')
    await page.addScriptTag({ content: readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8') })
    const result = await page.evaluate(async () => {
      const axe = (window as unknown as { axe: { run: () => Promise<{ violations: Array<{ impact?: string | null }> }> } }).axe
      return axe.run()
    })
    expect(result.violations.filter((violation) => violation.impact === 'serious' || violation.impact === 'critical')).toEqual([])
  })

  test('supports keyboard interaction and preserves privacy/no-execution boundaries', async ({ page }) => {
    await installRoutes(page)
    const executionRequests: string[] = []
    page.on('request', (request) => {
      if (/broker|order|trade|transfer|rebalance|execute/i.test(request.url())) executionRequests.push(request.url())
    })
    await page.goto('/investments/risk')
    await expect(page.getByRole('heading', { name: 'Risk and scenario views' })).toBeVisible()
    await page.getByLabel('Value delta').focus()
    await page.keyboard.type('25')
    await expect(page.getByLabel('Value delta')).toHaveValue('25')
    await expect(page.getByText('Brokerage')).toHaveCount(0)
    await expect(page.getByText('account:1')).toHaveCount(0)
    await expect(page.getByRole('button', { name: /buy|sell|execute|order|rebalance/i })).toHaveCount(0)
    await page.getByRole('button', { name: 'Preview change' }).press('Enter')
    await expect(page.getByText('Hypothetical analysis only · not a prediction')).toBeVisible()
    expect(executionRequests).toEqual([])
  })
})
