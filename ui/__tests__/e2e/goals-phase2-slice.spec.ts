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

/**
 * The merged forecast-read client intentionally fails closed until an
 * authoritative forecast collection contract exists. This journey keeps the
 * Goals page honest: it may show goals and persisted decision history, but it
 * must not infer a forecast, recommendation, or decision action from a
 * client-side fixture or an uncontracted endpoint.
 */
test('goals remain honest when the authoritative forecast read is unavailable', async ({ page, request }) => {
  const login = await request.post('http://localhost:8000/api/auth/devlogin?sub=alex')
  expect(login.ok(), 'test-only auth bootstrap should succeed').toBeTruthy()
  const token = (await login.json()).token as string
  await page.addInitScript((value) => {
    window.localStorage.setItem('fc_session_token', value)
  }, token)

  let forecastRequests = 0
  let decisionAttempts = 0
  page.on('request', (request) => {
    if (request.url().includes('/api/v1/forecasts')) forecastRequests += 1
    if (request.url().includes('/api/v1/recommendations/') && request.method() === 'POST') decisionAttempts += 1
  })

  await page.route('**/api/goals/', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify([GOAL]),
  }))
  await page.route('**/api/profile/', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ id: 1, email: 'alex@test.com', full_name: 'Alex' }),
  }))
  await page.route(`**/api/v1/goals/${GOAL.id}/decision-history`, (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ schema_version: 'atlas-decision-history-envelope/v1', history: [] }),
  }))

  await page.goto('/goals')
  const continueToApp = page.getByRole('button', { name: 'Continue to app' })
  if (await continueToApp.isVisible().catch(() => false)) await continueToApp.click()

  await expect(page.getByRole('heading', { name: 'Financial Goals' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Decision history', exact: true })).toBeVisible()
  await expect(page.getByText('No decisions have been recorded for this goal yet.')).toBeVisible()
  await expect(page.getByTestId('latest-forecast-section')).toBeAttached()
  await expect(page.getByTestId('forecast-projected')).toHaveCount(0)
  await expect(page.getByTestId('recommendation-explained-card')).toHaveCount(0)
  expect(forecastRequests, 'Goals must not probe an uncontracted forecast collection route').toBe(0)
  expect(decisionAttempts, 'No decision can be recorded without an authoritative recommendation').toBe(0)
})
