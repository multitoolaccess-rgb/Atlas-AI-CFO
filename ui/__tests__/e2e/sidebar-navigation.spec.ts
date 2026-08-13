/**
 * E2E tests for Atlas Phase 1 sidebar restructure and new pages.
 *
 * Tests:
 *   1. Sidebar groups render with correct labels (Money, Wealth, Tools, System)
 *   2. New nav items appear (Budgeting, Income, Expenses, Debts)
 *   3. Group headers toggle collapse/expand
 *   4. Each new page loads without console errors
 *   5. Navigation between pages works correctly
 *
 * Prerequisites:
 *   - The rules-service backend must be running on :8000
 *   - The Next.js dev server is started by Playwright's webServer config
 */
import { test, expect, type ConsoleMessage } from '@playwright/test'

/**
 * Benign console patterns — same as dashboard.spec.ts.
 */
const BENIGN_PATTERNS: RegExp[] = [
  /\[cashflix\].*Status:\s*401/i,
  /\[cashflix\].*No response received/i,
  /Failed to load resource.*ERR_CONNECTION_REFUSED/,
  /Failed to load resource.*ERR_INTERNET_DISCONNECTED/,
  /Network Error/i,
  /not wrapped in act\(\.\.\.\)/i,
]

const BENIGN_RESOURCE_URL_PATTERNS: RegExp[] = [
  /\/favicon\.ico(\?|$)/,
  /\/favicon\.svg(\?|$)/,
  /\/apple-touch-icon[^/]*\.(png|jpg|jpeg)(\?|$)/,
  /\/manifest(\.json|webmanifest)(\?|$)/,
  /\/_next\/static\//,
  /\/_next\/static\/chunks\//,
  /\/_next\/static\/css\//,
  /\/_next\/static\/media\//,
  /\/_next\/data\//,
  /\.(js|css|ts|tsx|mjs|cjs)\.map(\?|$)/,
]

const isMessageBenign = (text: string): boolean =>
  BENIGN_PATTERNS.some((re) => re.test(text))

const isResourceUrlBenign = (url: string): boolean => {
  if (!url) return false
  if (/\/api\//.test(url)) return false
  return BENIGN_RESOURCE_URL_PATTERNS.some((re) => re.test(url))
}

const isBenign = (text: string, url?: string): boolean => {
  if (isMessageBenign(text)) return true
  if (/Failed to load resource.*404/i.test(text) && url && isResourceUrlBenign(url)) {
    return true
  }
  return false
}

/** Attach console error listeners and return the error accumulator. */
function setupErrorCapture(page: import('@playwright/test').Page): string[] {
  const errors: string[] = []
  page.on('console', (msg: ConsoleMessage) => {
    if (msg.type() === 'error') {
      const text = msg.text()
      const url = msg.location()?.url ?? ''
      if (!isBenign(text, url)) errors.push(text)
    }
  })
  page.on('pageerror', (err) => {
    if (!isBenign(err.message)) errors.push(err.message)
  })
  page.on('requestfailed', (req) => {
    const url = req.url()
    const failure = req.failure()?.errorText ?? ''
    if (failure.includes('ERR_ABORTED') || failure.includes('ERR_CANCELED')) return
    if (!isResourceUrlBenign(url)) {
      errors.push(`requestfailed: ${url} -> ${failure || 'unknown'}`)
    }
  })
  return errors
}

// -------- Sidebar structure --------

test('sidebar has grouped navigation with 4 group headers', async ({ page }) => {
  const errors = setupErrorCapture(page)
  await page.goto('/')
  await page.waitForLoadState('networkidle')

  // Group headers should be visible
  await expect(page.locator('text=Money').first()).toBeVisible({ timeout: 10_000 })
  await expect(page.locator('text=Wealth').first()).toBeVisible()
  await expect(page.locator('text=Tools').first()).toBeVisible()
  await expect(page.locator('text=System').first()).toBeVisible()

  // New nav items should be visible
  await expect(page.locator('text=Budgeting').first()).toBeVisible()
  await expect(page.locator('text=Income').first()).toBeVisible()
  await expect(page.locator('text=Expenses').first()).toBeVisible()
  await expect(page.locator('text=Debts').first()).toBeVisible()

  // Original items still present
  await expect(page.locator('text=Overview').first()).toBeVisible()
  await expect(page.locator('text=Portfolio').first()).toBeVisible()
  await expect(page.locator('text=Goals').first()).toBeVisible()

  expect(errors).toEqual([])
})

test('group headers toggle collapse/expand', async ({ page }) => {
  const errors = setupErrorCapture(page)
  await page.goto('/')
  await page.waitForLoadState('networkidle')

  // The Money group should be expanded by default — Budgeting visible
  const budgetingLink = page.locator('nav a:has-text("Budgeting")')
  await expect(budgetingLink).toBeVisible({ timeout: 10_000 })

  // Click the Money group header to collapse
  const moneyHeader = page.locator('button:has-text("Money")')
  await moneyHeader.click()

  // Budgeting should now be hidden (group collapsed)
  await expect(budgetingLink).not.toBeVisible({ timeout: 3_000 })

  // Click again to expand
  await moneyHeader.click()
  await expect(budgetingLink).toBeVisible({ timeout: 3_000 })

  expect(errors).toEqual([])
})

// -------- New page loads --------

test('Budgeting page loads without errors', async ({ page }) => {
  const errors = setupErrorCapture(page)
  await page.goto('/budgeting')
  await page.waitForLoadState('networkidle')

  await expect(page.locator('h1:has-text("Budgeting")')).toBeVisible({ timeout: 10_000 })
  // Wait for the async budget data to finish loading, then verify the
  // content area rendered (KPI strip when budgets exist, empty state otherwise).
  await expect(page.locator('[data-testid="budgeting-loading"]')).toBeHidden({ timeout: 10_000 })
  // Surface backend errors explicitly so failures are actionable.
  await expect(page.locator('[data-testid="budgeting-error"]')).toBeHidden()
  await expect(
    page.locator('[data-testid="budgeting-kpi-strip"]').or(
      page.locator('[data-testid="budgeting-empty-state"]'),
    ),
  ).toBeVisible({ timeout: 10_000 })

  expect(errors).toEqual([])
})

test('Income page loads without errors', async ({ page }) => {
  const errors = setupErrorCapture(page)
  await page.goto('/income')
  await page.waitForLoadState('networkidle')

  await expect(page.locator('h1:has-text("Income")')).toBeVisible({ timeout: 10_000 })
  await expect(page.locator('text=Total Income').or(page.locator('text=No income transactions'))).toBeVisible({ timeout: 5_000 })

  expect(errors).toEqual([])
})

test('Expenses page loads without errors', async ({ page }) => {
  const errors = setupErrorCapture(page)
  await page.goto('/expenses')
  await page.waitForLoadState('networkidle')

  await expect(page.locator('h1:has-text("Expenses")')).toBeVisible({ timeout: 10_000 })
  await expect(page.locator('text=Total Expenses').or(page.locator('text=No expense transactions'))).toBeVisible({ timeout: 5_000 })

  expect(errors).toEqual([])
})

test('Debts page loads without errors', async ({ page }) => {
  const errors = setupErrorCapture(page)
  await page.goto('/debts')
  await page.waitForLoadState('networkidle')

  await expect(page.locator('h1:has-text("Debts")')).toBeVisible({ timeout: 10_000 })
  await expect(
    page.getByText('Total Debt', { exact: true }).first().or(
      page.getByText('No debt accounts', { exact: true }),
    ),
  ).toBeVisible({ timeout: 5_000 })

  expect(errors).toEqual([])
})

// -------- Navigation between pages --------

test('navigating between new pages via sidebar links', async ({ page }) => {
  const errors = setupErrorCapture(page)
  await page.goto('/')
  await page.waitForLoadState('networkidle')

  // Click Budgeting
  await page.locator('nav a:has-text("Budgeting")').click()
  await expect(page).toHaveURL(/\/budgeting/)
  await expect(page.locator('h1:has-text("Budgeting")')).toBeVisible({ timeout: 10_000 })

  // Click Income
  await page.locator('nav a:has-text("Income")').click()
  await expect(page).toHaveURL(/\/income/)
  await expect(page.locator('h1:has-text("Income")')).toBeVisible({ timeout: 10_000 })

  // Click Expenses
  await page.locator('nav a:has-text("Expenses")').click()
  await expect(page).toHaveURL(/\/expenses/)
  await expect(page.locator('h1:has-text("Expenses")')).toBeVisible({ timeout: 10_000 })

  // Click Debts
  await page.locator('nav a:has-text("Debts")').click()
  await expect(page).toHaveURL(/\/debts/)
  await expect(page.locator('h1:has-text("Debts")')).toBeVisible({ timeout: 10_000 })

  // Click back to Overview
  await page.locator('nav a:has-text("Overview")').click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.locator('text=Atlas').first()).toBeVisible({ timeout: 10_000 })

  expect(errors).toEqual([])
})

// -------- Budgeting page CRUD --------

test('Budgeting page add budget form opens and closes', async ({ page }) => {
  const errors = setupErrorCapture(page)
  await page.goto('/budgeting')
  await page.waitForLoadState('networkidle')

  // Click the header "Add Budget" button (empty state has its own CTA)
  const addBtn = page.locator('[data-testid="add-budget-button"]')
  await expect(addBtn).toBeVisible({ timeout: 10_000 })
  await addBtn.click()

  // Form should appear
  await expect(page.locator('text=New Budget Entry')).toBeVisible({ timeout: 3_000 })
  await expect(page.locator('select, [role="combobox"]').first()).toBeVisible()
  await expect(page.locator('input[type="number"]')).toBeVisible()

  // Cancel
  await page.locator('button:has-text("Cancel")').click()
  await expect(page.locator('text=New Budget Entry')).not.toBeVisible({ timeout: 3_000 })

  expect(errors).toEqual([])
})
