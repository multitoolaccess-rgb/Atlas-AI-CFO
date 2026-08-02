import { readFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const GOAL = {
  id: 42,
  name: 'Retirement by 55',
  target_amount: 15000000,
  horizon_years: 20,
  priority: 10,
  is_archived: false,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: null,
  target_date: null,
  notes: null,
}

const FORECAST_ID = '11111111-1111-4111-8111-111111111111'
const VERSION_ID = '22222222-2222-4222-8222-222222222222'
const RECOMMENDATION_ID = FORECAST_ID

const FORECAST = {
  id: FORECAST_ID,
  goal_id: GOAL.id,
  user_id: 1,
  currency: 'USD',
  kind: 'goal_projection',
  latest_version_number: 3,
  latest_version_id: VERSION_ID,
  etag: `${FORECAST_ID}-v3`,
  created_at: '2026-08-01T00:00:00.000000Z',
  updated_at: null,
  links: [
    { rel: 'self', href: `/api/v1/forecasts/${FORECAST_ID}` },
    { rel: 'goal', href: `/api/goals/${GOAL.id}` },
  ],
}

const VERSION = {
  id: VERSION_ID,
  forecast_id: FORECAST_ID,
  version_number: 3,
  ending_balance: '4500000.00',
  target_decision: {
    rounded_ending_balance: '4500000.00',
    rounded_target_amount: '15000000.00',
    target_status: false,
    decision_etag: `${FORECAST_ID}-v3`,
  },
  drivers: { data_age_days: 4, max_data_age_days: 14 },
  scenarios: [
    { name: 'conservative', annual_return_rate: '0.0400', ending_balance: '3200000.00' },
    { name: 'base', annual_return_rate: '0.0600', ending_balance: '4500000.00' },
    { name: 'optimistic', annual_return_rate: '0.0900', ending_balance: '6800000.00' },
  ],
  assumption_snapshot: { decision_window: 'q3-2026', contribution_amount: '1500.00' },
  provenance_snapshot: { source_aggregation: 'finlynq-state/v1' },
  data_as_of: '2026-07-28T00:00:00.000000Z',
  calculated_at: '2026-08-01T00:00:00.000000Z',
  model_version: 'atlas-projection/v1',
  calculation_version: 'atlas-calculation-decimal/v1',
  input_state_hash: 'a'.repeat(64),
}

const RECOMMENDATION = {
  schema_version: 'atlas-derived-recommendation/v1',
  recommendation_kind: 'increase_contribution',
  action_verb: 'Increase',
  why_now: 'Your projection falls short at the current contribution cadence.',
  linked_goal_id: GOAL.id,
  forecast_id: FORECAST_ID,
  forecast_etag: `${FORECAST_ID}-v3`,
  evidence_references: {
    forecast_id: FORECAST_ID,
    model_version: 'atlas-projection/v1',
    calculation_version: 'atlas-calculation-decimal/v1',
    input_state_hash: 'a'.repeat(64),
    data_as_of: VERSION.data_as_of,
  },
  expected_impact_range: { min_delta_decimal: '12000.00', max_delta_decimal: '32000.00' },
  risks: ['liquidity_reduction'],
  confidence: 'medium',
  assumptions_reference: 'b'.repeat(64),
  expiration: '2026-08-02T00:00:00.000000Z',
  issuer: 'atlas-deterministic-rules/v1',
  links: [
    { rel: 'self', href: `/api/v1/forecasts/${FORECAST_ID}/recommendation` },
    { rel: 'forecast', href: `/api/v1/forecasts/${FORECAST_ID}` },
    { rel: 'decide', href: `/api/v1/recommendations/${RECOMMENDATION_ID}/decisions` },
  ],
}

const JOURNAL_ENTRY = {
  schema_version: 'atlas-decision-journal-entry/v1',
  journal_entry_id: '33333333-3333-4333-8333-333333333333',
  recommendation_id: RECOMMENDATION_ID,
  action_taken: 'accept',
  decided_at: '2026-08-01T00:01:00.000000Z',
  decision_etag: `${FORECAST_ID}-v3-d1`,
  links: [{ rel: 'self', href: '/api/v1/decisions/33333333-3333-4333-8333-333333333333' }],
}

test('goal forecast → recommendation → explanation → retry-safe decision', async ({ page, request }) => {
  const login = await request.post('http://localhost:8000/api/auth/devlogin?sub=alex')
  expect(login.ok(), 'test-only auth bootstrap should succeed').toBeTruthy()
  const token = (await login.json()).token as string
  await page.addInitScript((value) => {
    window.localStorage.setItem('fc_session_token', value)
  }, token)

  const decisionKeys: string[] = []
  let decisionAttempts = 0

  await page.route('**/api/goals/', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([GOAL]) }))
  await page.route('**/api/profile/', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 1, email: 'alex@test.com', full_name: 'Alex' }) }))
  await page.route('**/api/dashboard/summary', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ total_balance: 0, total_income_month: 0, total_expenses_month: 0, accounts_count: 0, transactions_count: 0, import_batches_count: 0, user_goals: [GOAL] }),
  }))
  await page.route('**/api/v1/forecasts?**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ forecasts: [FORECAST] }) }))
  await page.route(`**/api/v1/forecasts/${FORECAST_ID}/versions/${VERSION.version_number}`, (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(VERSION) }))
  await page.route(`**/api/v1/forecasts/${FORECAST_ID}/recommendation`, (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RECOMMENDATION) }))
  await page.route(`**/api/v1/recommendations/${RECOMMENDATION_ID}/decisions`, async (route) => {
    decisionKeys.push(route.request().headers()['idempotency-key'] ?? '')
    decisionAttempts += 1
    if (decisionAttempts === 1) {
      await route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ code: 'unknown', message: 'temporary upstream failure' }) })
      return
    }
    await route.fulfill({ status: 201, contentType: 'application/json', headers: { location: '/api/v1/decisions/33333333-3333-4333-8333-333333333333', etag: `"${JOURNAL_ENTRY.journal_entry_id}-d1"` }, body: JSON.stringify(JOURNAL_ENTRY) })
  })

  await page.goto('/goals')
  await expect(page.getByRole('heading', { name: 'Financial Goals' })).toBeVisible()
  await expect(page.getByTestId('forecast-projected')).toHaveText('4,500,000.00')
  await expect(page.getByTestId('forecast-target')).toHaveText('15,000,000')
  await expect(page.getByTestId('forecast-timestamp')).toContainText('2026-08-01')
  await expect(page.getByTestId('forecast-timestamp')).toContainText('4 days')

  await page.getByTestId('why-this-toggle').click()
  await expect(page.getByTestId('why-this-panel')).toBeVisible()
  await expect(page.getByTestId('forecast-version')).toHaveText('#3')
  await expect(page.getByTestId('forecast-hash')).toContainText('aaaaaaaa')
  await expect(page.getByTestId('why-this-panel')).toContainText('atlas-projection/v1')
  await expect(page.getByTestId('why-this-panel')).toContainText('atlas-calculation-decimal/v1')
  await expect(page.getByTestId('why-this-panel')).toContainText('input state hash')

  await expect(page.getByTestId('action-verb')).toHaveText('Increase')
  await expect(page.getByTestId('impact-range')).toContainText('12,000.00')
  await expect(page.getByTestId('impact-range')).toContainText('32,000.00')
  await expect(page.getByTestId('confidence-tag')).toHaveText('Medium confidence')
  await expect(page.getByTestId('risks-list')).toContainText('Liquidity reduction')
  await page.getByTestId('assumptions-toggle').click()
  await expect(page.getByTestId('assumptions-panel')).toContainText('bbbbbbbb')

  await expect(page.getByText('Gap remaining')).toBeVisible()
  await page.getByTestId('assumptions-toggle').focus()
  await expect(page.getByTestId('assumptions-toggle')).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByTestId('rec-accept')).toBeFocused()
  await expect(page.getByTestId('rec-accept')).toHaveCSS('outline-width', '2px')
  await page.keyboard.press('Tab')
  await expect(page.getByTestId('rec-reject')).toBeFocused()
  await expect(page.getByTestId('rec-reject')).toHaveCSS('outline-width', '2px')
  await page.keyboard.press('Tab')
  await expect(page.getByTestId('rec-defer')).toBeFocused()
  await expect(page.getByTestId('rec-defer')).toHaveCSS('outline-width', '2px')

  const axeSource = readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8')
  await page.addScriptTag({ content: axeSource })
  const assertNoSeriousOrCriticalViolations = async () => {
    const axeResult = await page.evaluate(async () => {
      const root = document.querySelector('[data-testid="latest-forecast-section"]')
      if (!root) throw new Error('Phase 2 forecast section is missing')
      const axe = (window as unknown as { axe: { run: (context: Element) => Promise<{ violations: Array<{ impact?: string | null }> }> } }).axe
      return axe.run(root)
    })
    const seriousOrCritical = axeResult.violations.filter((violation) =>
      violation.impact === 'serious' || violation.impact === 'critical',
    )
    expect(seriousOrCritical, JSON.stringify(seriousOrCritical)).toHaveLength(0)
  }
  await assertNoSeriousOrCriticalViolations()

  await page.getByTestId('rec-accept').focus()
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('decision-error')).toContainText('response was not confirmed')
  await page.getByTestId('decision-retry').click()
  await expect(page.getByTestId(`recommendation-recorded-${FORECAST_ID}`)).toBeVisible()
  expect(decisionAttempts).toBe(2)
  expect(decisionKeys[0]).toBeTruthy()
  expect(decisionKeys[1]).toBe(decisionKeys[0])

  await assertNoSeriousOrCriticalViolations()

  await page.goto('/')
  await expect(page.getByText('Financial Plans')).toBeVisible()
})
