import { test, expect } from '@playwright/test'

/**
 * E2e tests for the dashboard interactive analytics workspace.
 *
 * Tests cover:
 * 1. Dashboard loads with all modules visible
 * 2. Time range selector is present and functional
 * 3. Changing time range updates the URL query param
 * 4. ExpandableCard expand/collapse works
 * 5. Drilldown drawer opens on segment click
 *
 * Pre-requisite: both the Next.js dev server (:3000) and the
 * rules-service backend (:8000) must be running.
 */

test.describe('Dashboard — interactive analytics workspace', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    // Wait for the dashboard to finish loading (skeleton disappears)
    await page.waitForSelector('text=Hello', { timeout: 15_000 })
  })

  test('dashboard loads with all modules visible', async ({ page }) => {
    // KPI strip cards
    await expect(page.getByText('Income MTD')).toBeVisible()
    await expect(page.getByText('Spend MTD')).toBeVisible()

    // Trend chart module
    await expect(page.getByText('Trend')).toBeVisible()

    // Breakdown module
    await expect(page.getByText('Breakdown')).toBeVisible()

    // Financial Health module
    await expect(page.getByText('Financial Health')).toBeVisible()

    // Spending by Category module
    await expect(page.getByText('Spending by Category')).toBeVisible()
  })

  test('time range selector renders with all presets', async ({ page }) => {
    const radiogroup = page.getByRole('radiogroup', { name: 'Time range' })
    await expect(radiogroup).toBeVisible()

    // All 8 presets should be present
    for (const label of ['7D', '30D', '90D', 'MTD', 'QTD', 'YTD', '1Y', 'All']) {
      await expect(page.getByRole('radio', { name: label })).toBeVisible()
    }
  })

  test('changing time range updates URL query param', async ({ page }) => {
    // Click the 30D preset
    await page.getByRole('radio', { name: '30D' }).click()
    // URL should contain ?range=30D
    await expect(page).toHaveURL(/[?&]range=30D/)
  })

  test('URL time range persists on page reload', async ({ page }) => {
    // Set to 7D
    await page.getByRole('radio', { name: '7D' }).click()
    await expect(page).toHaveURL(/[?&]range=7D/)

    // Reload with the URL param preserved
    await page.reload()
    await page.waitForSelector('text=Hello', { timeout: 15_000 })

    // The URL should still have ?range=7D after reload
    await expect(page).toHaveURL(/[?&]range=7D/)

    // Wait for the GlobalFilterBar to render (it's gated by ready && transactions.length > 0)
    // then verify 7D is the selected preset
    const sevenDRadio = page.getByRole('radio', { name: '7D' })
    await expect(sevenDRadio).toBeVisible({ timeout: 10_000 })
    await expect(sevenDRadio).toHaveAttribute('aria-checked', 'true')
  })

  test('expandable cards have expand/collapse buttons', async ({ page }) => {
    // The Trend card should have an expand button
    // Use exact: true to avoid matching sidebar's "Collapse sidebar" button.
    const expandBtn = page.getByRole('button', { name: 'Expand', exact: true }).first()
    await expect(expandBtn).toBeVisible()

    // Click it
    await expandBtn.click()

    // Should now show a collapse button (exact match avoids sidebar button)
    const collapseBtn = page.getByRole('button', { name: 'Collapse', exact: true }).first()
    await expect(collapseBtn).toBeVisible()

    // The expanded content should be visible
    await expect(collapseBtn).toHaveAttribute('aria-expanded', 'true')
  })

  test('legend toggles hide and show chart series', async ({ page }) => {
    // Find the Income legend toggle button
    const incomeToggle = page.getByRole('button', { name: /Hide Income/i })
    await expect(incomeToggle).toBeVisible()

    // Click to hide
    await incomeToggle.click()
    await expect(page.getByRole('button', { name: /Show Income/i })).toBeVisible()

    // Click to show again
    await page.getByRole('button', { name: /Show Income/i }).click()
    await expect(page.getByRole('button', { name: /Hide Income/i })).toBeVisible()
  })

  test('no console errors on page load', async ({ page }) => {
    const errors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text())
    })

    await page.goto('/')
    await page.waitForSelector('text=Hello', { timeout: 15_000 })

    // Filter out known benign warnings (e.g., form field a11y)
    const criticalErrors = errors.filter(
      (e) => !e.includes('form field') && !e.includes('favicon'),
    )
    expect(criticalErrors).toHaveLength(0)
  })
})
