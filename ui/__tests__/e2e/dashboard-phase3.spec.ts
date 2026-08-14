/**
 * Phase 3 E2E tests — CategoryMovers, AlertsPanel, data-driven RecommendationCard.
 *
 * Prerequisites:
 *   - The rules-service backend must be running on :8000
 *   - The Next.js dev server is started by Playwright's webServer config.
 *
 * These tests verify that the Phase 3 dashboard sections render correctly
 * in a real browser environment with a live backend.
 */
import { test, expect } from '@playwright/test'

test('Cash Flow is the sole authoritative Money-flow visualisation', async ({ page }) => {
  await page.goto('/cash-flow')
  await page.waitForURL('**/cash-flow')
  await page.waitForLoadState('networkidle')
  await expect(page.getByTestId('sankey-hero')).toBeVisible({ timeout: 15_000 })
})

test('Mission Control does not duplicate Cash Flow’s full visualisation', async ({ page }) => {
  await page.goto('/')
  await page.waitForURL('**/')
  await page.waitForLoadState('networkidle')
  await expect(page.getByTestId('mission-control-page')).toBeVisible()
  await expect(page.getByTestId('sankey-hero')).toHaveCount(0)
})

test('Alerts Panel section renders on dashboard', async ({ page }) => {
  await page.goto('/')
  await page.waitForURL('**/')
  await page.waitForLoadState('networkidle')

  // The Alerts & Insights heading should be visible after data loads.
  await expect(
    page.locator('h3:has-text("Alerts & Insights")'),
  ).toBeVisible({ timeout: 10_000 })
})

test('Alerts & Insights keeps its empty state when dashboard source collections are empty', async ({ page }) => {
  await page.route('**/api/dashboard/insights', async (route) => {
    await route.fulfill({ json: { insights: [] } })
  })
  await page.route('**/api/dashboard/anomalies', async (route) => {
    await route.fulfill({ json: { anomalies: [], count: 0 } })
  })
  await page.route('**/api/dashboard/upcoming-bills', async (route) => {
    await route.fulfill({ json: { bills: [], count: 0 } })
  })

  await page.goto('/')
  await page.waitForURL('**/')
  await page.waitForLoadState('networkidle')

  await expect(page.getByRole('heading', { name: 'Alerts & Insights' })).toBeVisible()
  await expect(page.getByText('All clear')).toBeVisible()
})

test('Mission Control keeps the actionable recommendation queue', async ({ page }) => {
  await page.goto('/')
  await page.waitForURL('**/')
  await page.waitForLoadState('networkidle')

  await expect(page.getByTestId('approval-queue')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByRole('heading', { name: 'Approval Queue' })).toBeVisible()
})

test('skip navigation link is accessible', async ({ page }) => {
  await page.goto('/')
  await page.waitForURL('**/')

  // The skip nav link should exist in the DOM (sr-only, not visible by default).
  const skipLink = page.locator('a[href="#main-content"]')
  await expect(skipLink).toBeAttached()

  // The main content should have the target id.
  const mainContent = page.locator('#main-content')
  await expect(mainContent).toBeAttached()
})
