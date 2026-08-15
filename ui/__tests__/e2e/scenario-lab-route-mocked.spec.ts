import { test, expect, type Page } from '@playwright/test'

const scenarioId = '11111111-1111-4111-8111-111111111111'
const baselineId = '22222222-2222-4222-8222-222222222222'

function comparison() {
  return {
    schema_version: 'atlas-scenario-comparison/v1', baseline_forecast_id: baselineId, baseline_version_number: 1, baseline_input_state_hash: 'a'.repeat(64), currency: 'USD',
    ending_net_worth: '120000.00', difference_from_baseline: '1000.00', target_amount: '150000.00', target_gap: '30000.00', target_reached: true,
    contribution_difference: '3000.00', one_time_liquidity_consumed: '0.00',
    deterministic_bands: Object.fromEntries(['conservative', 'base', 'optimistic'].map((band) => [band, { baseline_ending_net_worth: '119000.00', scenario_ending_net_worth: '120000.00', difference_from_baseline: '1000.00', baseline_target_reached: false, scenario_target_reached: true, baseline_target_gap: '31000.00', scenario_target_gap: '30000.00', target_amount: '150000.00' }])),
    timing_impact: { contribution_start_date: null, contribution_stop_date: null, one_time_outflow_date: null, one_time_outflow_boundary_index: null },
    assumptions: { annual_return_rates: { conservative: '0.02', base: '0.04', optimistic: '0.06' }, annual_inflation_rate: '0.02', contribution_timing: 'end_of_month', period: 'monthly', rounding_rule: 'ROUND_HALF_EVEN', probability: false },
    source_freshness: { data_as_of: '2026-08-14', data_age_days: 0, max_data_age_days: 30 }, warnings: ['Deterministic scenario bands are not probabilities or guarantees.'], limitations: ['USD-only synthetic fixture.'],
  }
}

function envelope(lifecycle: 'active' | 'archived' = 'active') {
  return { schema_version: 'atlas-scenario-envelope/v1', scenario_id: scenarioId, version_id: '33333333-3333-4333-8333-333333333333', version_number: 1, goal_id: 42, baseline_forecast_id: baselineId, baseline_version_number: 1, baseline_input_state_hash: 'a'.repeat(64), scenario_input_hash: 'b'.repeat(64), model_version: 'model-v1', calculation_version: 'calc-v1', currency: 'USD', lifecycle_state: lifecycle, created_at: '2026-08-14T00:00:00Z', input: { schema_version: 'atlas-scenario-lab/v1', baseline_forecast_id: baselineId, baseline_version_number: 1, baseline_input_state_hash: 'a'.repeat(64), scenario: { monthly_contribution_delta: '250.00' } }, result: { schema_version: 'atlas-scenario-lab/v1', model_version: 'model-v1', calculation_version: 'calc-v1', currency: 'USD', scenario_input_hash: 'b'.repeat(64), canonical_inputs: { monthly_contribution_delta: '250.00' }, deterministic_bands: {}, source_freshness: comparison().source_freshness, assumptions: comparison().assumptions }, comparison: comparison(), recommendation_reference: null, etag: 'etag-1' }
}

async function installMocks(page: Page, options: { enabled?: boolean; baseline?: boolean; incompatible?: boolean; seedScenario?: boolean; unexpected?: boolean } = {}) {
  let hasScenario = options.seedScenario === true
  await page.route('**/api/**', (route) => route.fallback())
  await page.route('**/api/goals/', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([{ id: 42, name: 'Retirement', target_amount: 150000, priority: 1, is_archived: false }]) }))
  await page.route('**/api/v1/goals/42/scenarios**', async (route) => {
    if (route.request().method() === 'POST') {
      if (options.enabled === false) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ code: 'scenario_generation_unavailable', message: 'disabled' }) })
      if (options.baseline === false) return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ code: 'scenario_baseline_unavailable', message: 'missing' }) })
      hasScenario = true
      return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(envelope()) })
    }
    if (options.enabled === false) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ code: 'scenario_generation_unavailable', message: 'disabled' }) })
    if (options.unexpected) return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'synthetic unexpected failure' }) })
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ schema_version: 'atlas-scenario-list/v1', items: hasScenario ? [{ scenario_id: scenarioId, goal_id: 42, version_number: 1, baseline_forecast_id: baselineId, baseline_version_number: 1, currency: 'USD', lifecycle_state: 'active', created_at: '2026-08-14T00:00:00Z', ending_net_worth: '120000.00', difference_from_baseline: '1000.00', target_reached: true }] : [], next_cursor: null }) })
  })
  await page.route('**/api/v1/scenarios/compare', async (route) => {
    if (options.incompatible) return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ code: 'scenario_comparison_incompatible', message: 'incompatible' }) })
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ schema_version: 'atlas-scenario-comparison-set/v1', baseline_forecast_id: baselineId, baseline_version_number: 1, scenarios: [{ scenario_id: scenarioId, version_number: 1, comparison: comparison() }] }) })
  })
  await page.route(`**/api/v1/scenarios/${scenarioId}/archive`, (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ schema_version: 'atlas-scenario-archive/v1', scenario_id: scenarioId, lifecycle_state: 'archived', archived_at: '2026-08-14T00:00:00Z' }) }))
  await page.route(`**/api/v1/scenarios/${scenarioId}`, (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(envelope()) }))
  await page.route('**/api/auth/**', (route) => route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'Synthetic auth response' }) }))
}

async function openScenarioLab(page: Page, options?: { enabled?: boolean; baseline?: boolean; incompatible?: boolean; seedScenario?: boolean; unexpected?: boolean }) {
  await installMocks(page, options)
  await page.goto('/scenario-lab?skip-splash=1')
  await page.waitForLoadState('domcontentloaded')
  await expect(page.getByTestId('scenario-lab-page')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Scenario Lab', level: 1 })).toBeVisible()
}

test.describe('Scenario Lab frontend-owned route-mocked journey', () => {
  test('generates, reloads, compares, and archives a persisted server result', async ({ page }) => {
    await openScenarioLab(page)
    await page.getByRole('button', { name: 'Switch to dark mode' }).click()
    await expect(page.locator('html')).toHaveClass(/dark/)
    await page.getByLabel('Monthly contribution change').fill('250.00')
    const request = page.waitForRequest((request) => request.url().includes('/api/v1/goals/42/scenarios') && request.method() === 'POST')
    await page.getByRole('button', { name: 'Generate scenario' }).click()
    const mutation = await request
    expect(mutation.headers()['idempotency-key']).toBeTruthy()
    await expect(page.getByRole('heading', { name: 'What this change means against the baseline' })).toBeVisible()
    await expect(page).toHaveURL(/scenario-lab\?.*goal=42&scenario=/)
    await expect(page.getByText('Deterministic range comparison')).toBeVisible()
    await expect(page.getByText(/browser does not calculate projections/i)).toBeVisible()

    await page.reload()
    await expect(page.getByRole('heading', { name: 'What this change means against the baseline' })).toBeVisible()
    await page.getByRole('button', { name: 'Comparisons' }).click()
    await expect(page).toHaveURL(/view=comparisons/)
    await page.getByRole('checkbox').check()
    await page.getByRole('button', { name: 'Compare selected scenarios' }).click()
    await expect(page.getByRole('table', { name: /selected Scenario Lab comparison/i })).toBeVisible()
    await page.getByRole('button', { name: 'Archive' }).click()
    await expect(page.getByRole('heading', { name: 'Immutable scenario history' })).toBeVisible()
    await page.getByRole('button', { name: /Archive scenario/ }).click()
    await expect(page.getByText(/immutable server version/i)).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBeTruthy()
  })

  test('shows disabled and missing-baseline recovery without local estimates', async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
    await openScenarioLab(page, { enabled: false })
    await expect(page.getByText('Disabled by server')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Generate scenario' })).toBeDisabled()
    // Browser network diagnostics may still report the HTTP response itself;
    // the regression guard is that Atlas does not emit its own API Error for
    // this explicitly handled server-owned availability state.
    expect(consoleErrors.filter((message) => /\[cashflix\] API Error/i.test(message))).toEqual([])
    consoleErrors.length = 0

    await page.goto('/scenario-lab?skip-splash=1')
    await installMocks(page, { baseline: false })
    await page.getByLabel('Monthly contribution change').fill('250.00')
    await page.getByRole('button', { name: 'Generate scenario' }).click()
    await expect(page.getByText(/Generate or refresh an approved baseline forecast/i)).toBeVisible()
    await expect(page.getByRole('alert').filter({ hasText: 'No client-side result was calculated' }).first()).toBeVisible()
  })

  test('keeps unexpected server failures observable', async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
    await openScenarioLab(page, { unexpected: true })
    await expect(page.getByRole('alert').filter({ hasText: 'No client-side result was calculated' }).first()).toBeVisible()
    expect(consoleErrors.some((message) => /API Error|500/i.test(message))).toBeTruthy()
  })

  test('keeps selection keyboard accessible and recovers from incompatible comparison', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await openScenarioLab(page, { seedScenario: true, incompatible: true })
    await page.getByRole('button', { name: 'Collapse sidebar' }).click()
    await page.getByRole('button', { name: 'Comparisons' }).focus()
    await page.keyboard.press('ArrowRight')
    await expect(page.getByRole('button', { name: 'Archive' })).toBeFocused()
    await page.getByRole('button', { name: 'Comparisons' }).click()
    await expect(page.getByRole('heading', { name: 'Compare saved scenarios' })).toBeVisible()
    await page.getByRole('checkbox').check()
    await page.getByRole('button', { name: 'Compare selected scenarios' }).click()
    await expect(page.getByRole('alert').filter({ hasText: 'Choose scenarios from the same goal' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBeTruthy()
  })
})
