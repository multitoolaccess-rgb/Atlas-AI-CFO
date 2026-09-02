import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'

const candidate = {
  candidate_id: 'discovery:a',
  universe: 'sp500',
  security: { security_id: 'sec:ui09:sp500:aapl', symbol: 'AAPL', instrument_type: 'equity', state: 'resolved' },
  status: 'candidate',
  reason: 'Member of the approved sp500 discovery universe',
  source: 'server:ui09:sp500-universe',
  as_of: '2026-01-01T00:00:00Z',
  freshness: 'unknown',
  methodology_version: 'ui09-universe-membership/v1',
  metrics: {},
  metric_states: {},
  recommendation_id: null,
  detail_available: true,
}

test.describe('UI-09 opportunity discovery', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/v1/investments/discovery**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ schema_version: 'InvestmentDiscovery/v1', universe: 'sp500', as_of: '2026-01-01T00:00:00Z', methodology_version: 'ui09-universe-membership/v1', source_scope: 'server-owned-current-only', omitted_count: 0, candidates: [candidate] }) })
    })
  })

  test('renders discovery with accessible controls and no horizontal overflow', async ({ page }) => {
    await page.goto('/investments/discovery')
    await expect(page.getByRole('heading', { name: 'Opportunity discovery' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'S&P 500' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'AAPL' })).toBeVisible()
    for (const width of [390, 768, 1440]) {
      await page.setViewportSize({ width, height: 900 })
      const overflow = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }))
      expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1024)
    }
  })

  test('has no serious or critical accessibility violations', async ({ page }) => {
    await page.goto('/investments/discovery')
    await page.addScriptTag({ content: readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8') })
    const result = await page.evaluate(async () => {
      const axe = (window as unknown as { axe: { run: () => Promise<{ violations: Array<{ impact?: string | null }> }> } }).axe
      return axe.run()
    })
    expect(result.violations.filter((violation) => violation.impact === 'serious' || violation.impact === 'critical')).toEqual([])
  })
})
