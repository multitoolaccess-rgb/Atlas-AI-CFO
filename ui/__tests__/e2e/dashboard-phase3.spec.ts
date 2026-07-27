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

test('Category Movers section renders on dashboard', async ({ page }) => {
  await page.goto('/')
  await page.waitForURL('**/')
  await page.waitForLoadState('networkidle')

  // The Category Movers heading should be visible after data loads.
  // It renders whether there are insights or shows an empty state.
  await expect(
    page.locator('h3:has-text("Category Movers")'),
  ).toBeVisible({ timeout: 10_000 })
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

test('RecommendationCard shows data-driven content (not hardcoded)', async ({ page }) => {
  await page.goto('/')
  await page.waitForURL('**/')
  await page.waitForLoadState('networkidle')

  // The AI Insight label should be present on the RecommendationCard.
  await expect(
    page.locator('text=AI Insight').first(),
  ).toBeVisible({ timeout: 10_000 })

  // The recommendation title should be one of the data-driven options,
  // NOT the old hardcoded "Rebalance Emerging Markets".
  const title = page.locator('h3').filter({ hasText: /Boost Your Savings|Almost Funded|Spending Nearing|On Track/ })
  await expect(title.first()).toBeVisible({ timeout: 10_000 })

  // The old hardcoded title should NOT appear.
  const oldTitle = page.locator('text=Rebalance Emerging Markets')
  await expect(oldTitle).toHaveCount(0)
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
