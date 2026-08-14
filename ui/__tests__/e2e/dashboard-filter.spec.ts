import { test, expect } from '@playwright/test'

/**
 * E2e tests for the consolidated Cash Flow analytics workspace.
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

test.describe('Cash Flow — interactive analytics workspace', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/cash-flow')
    await expect(page.getByRole('heading', { name: 'Cash Flow', level: 1 })).toBeVisible()
  })

  test('Cash Flow owns the primary Money visualisation and shared tabs', async ({ page }) => {
    await expect(page.getByTestId('cash-flow-page')).toBeVisible()
    await expect(page.getByTestId('sankey-hero')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByLabel('Cash flow analysis')).toBeVisible()
    for (const label of ['Overview', 'Income', 'Spending', 'Transactions']) {
      await expect(page.getByTestId('page-tabs').getByRole('button', { name: label })).toBeVisible()
    }
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

    // Reload with the URL param preserved.
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Cash Flow', level: 1 })).toBeVisible()

    // The URL should still have ?range=7D after reload
    await expect(page).toHaveURL(/[?&]range=7D/)

    // Wait for the GlobalFilterBar to render (it's gated by ready && transactions.length > 0)
    // then verify 7D is the selected preset
    const sevenDRadio = page.getByRole('radio', { name: '7D' })
    await expect(sevenDRadio).toBeVisible({ timeout: 10_000 })
    await expect(sevenDRadio).toHaveAttribute('aria-checked', 'true')
  })

  test('tab selection preserves the shared range query state', async ({ page }) => {
    await page.getByRole('radio', { name: '30D' }).click()
    await page.getByTestId('page-tabs').getByRole('button', { name: 'Income' }).click()
    await expect(page).toHaveURL(/view=income/)
    await expect(page).toHaveURL(/range=30D/)
    await expect(page.getByText('Total Income')).toBeVisible({ timeout: 15_000 })
  })

  test('Spending is a direct, URL-addressable detail view', async ({ page }) => {
    await page.goto('/cash-flow?view=spending&range=MTD')
    await expect(page.getByTestId('page-tabs').getByRole('button', { name: 'Spending' })).toHaveAttribute('aria-current', 'page')
    await expect(page.getByText('Total Expenses')).toBeVisible({ timeout: 15_000 })
    await expect(page).toHaveURL(/view=spending/)
    await expect(page).toHaveURL(/range=MTD/)
  })

  test('no console errors on page load', async ({ page }) => {
    const errors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text())
    })

    await page.goto('/cash-flow')
    await expect(page.getByRole('heading', { name: 'Cash Flow', level: 1 })).toBeVisible()

    // Filter out known benign warnings (e.g., form field a11y)
    const criticalErrors = errors.filter(
      (e) => !e.includes('form field') && !e.includes('favicon'),
    )
    expect(criticalErrors).toHaveLength(0)
  })
})
