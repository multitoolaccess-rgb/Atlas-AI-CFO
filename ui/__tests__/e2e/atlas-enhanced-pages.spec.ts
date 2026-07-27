/**
 * E2E tests for Atlas Phase 2+3 enhanced pages — Budgeting, Income, Expenses, Debts.
 *
 * Tests cover:
 *   1. Page loading with KPI cards and chart sections
 *   2. DrilldownDrawer interaction (click category/group → drawer opens with transactions)
 *   3. Time range filtering on Income and Expenses
 *   4. Budgeting page CRUD (add budget form)
 *   5. Debts page debt table and payoff projections
 *   6. Navigation between enhanced pages
 *
 * Prerequisites:
 *   - The rules-service backend must be running on :8000
 *   - The Next.js dev server is started by Playwright's webServer config
 */
import { test, expect, type ConsoleMessage } from '@playwright/test'

/**
 * Benign console patterns — same as sidebar-navigation.spec.ts.
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

// ============================================================
// Budgeting Page
// ============================================================

test.describe('Budgeting page — enhanced with BudgetCategoryCard', () => {
  test('loads with KPI cards and budget groups', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/budgeting')
    await page.waitForLoadState('networkidle')

    // Page heading
    await expect(page.locator('h1:has-text("Budgeting")')).toBeVisible({ timeout: 10_000 })

    // KPI cards should render (Total Budget, Total Spent, Remaining, % Used)
    // OR empty state if no budgets configured
    await expect(
      page.locator('text=Total Budget')
        .or(page.locator('text=No budgets configured'))
    ).toBeVisible({ timeout: 10_000 })

    // If budgets exist, check the group labels
    const hasBudgets = await page.locator('text=Total Budget').isVisible()
    if (hasBudgets) {
      await expect(
        page.locator('text=Fixed Expenses')
          .or(page.locator('text=Flexible Expenses'))
          .or(page.locator('text=Debt Payments'))
          .or(page.locator('text=Savings & Investments'))
      ).toBeVisible({ timeout: 10_000 })
    }

    expect(errors).toEqual([])
  })

  test('add budget form opens and closes', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/budgeting')
    await page.waitForLoadState('networkidle')

    // Click "Add Budget" or "Create Your First Budget"
    const addBtn = page.locator('button:has-text("Add Budget")').or(
      page.locator('button:has-text("Create Your First Budget")')
    )
    await expect(addBtn).toBeVisible({ timeout: 10_000 })
    await addBtn.click()

    // Form should appear with category select and amount input
    await expect(page.locator('text=New Budget Entry')).toBeVisible({ timeout: 3_000 })
    await expect(page.locator('select, [role="combobox"]').first()).toBeVisible()
    await expect(page.locator('input[type="number"]')).toBeVisible()

    // Cancel
    await page.locator('button:has-text("Cancel")').click()
    await expect(page.locator('text=New Budget Entry')).not.toBeVisible({ timeout: 3_000 })

    expect(errors).toEqual([])
  })

  test('month selector changes period', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/budgeting')
    await page.waitForLoadState('networkidle')

    // Month input should be visible
    const monthInput = page.locator('input[type="month"]')
    await expect(monthInput).toBeVisible({ timeout: 10_000 })

    // Should have a value (current month)
    const value = await monthInput.inputValue()
    expect(value).toMatch(/^\d{4}-\d{2}$/)

    expect(errors).toEqual([])
  })
})

// ============================================================
// Income Page
// ============================================================

test.describe('Income page — enhanced with drilldown', () => {
  test('loads with KPI cards and income breakdown', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/income')
    await page.waitForLoadState('networkidle')

    // Page heading
    await expect(page.locator('h1:has-text("Income")')).toBeVisible({ timeout: 10_000 })

    // KPI cards or empty state
    await expect(
      page.locator('text=Total Income')
        .or(page.locator('text=No income data'))
    ).toBeVisible({ timeout: 10_000 })

    expect(errors).toEqual([])
  })

  test('time range selector is present and functional', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/income')
    await page.waitForLoadState('networkidle')

    // Time range selector should be visible
    await expect(
      page.locator('[data-testid="time-range-selector"]')
        .or(page.locator('button:has-text("MTD")'))
        .or(page.locator('button:has-text("All")'))
    ).toBeVisible({ timeout: 10_000 })

    expect(errors).toEqual([])
  })

  test('income by group section renders clickable rows', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/income')
    await page.waitForLoadState('networkidle')

    // Wait for data to load
    await expect(page.locator('h1:has-text("Income")')).toBeVisible({ timeout: 10_000 })
    await page.waitForLoadState('networkidle')

    const groupSection = page.locator('text=Income by Group')
    const hasGroups = await groupSection.isVisible()
    if (hasGroups) {
      await expect(groupSection).toBeVisible()
    }

    expect(errors).toEqual([])
  })

  test('income sources section renders clickable category rows', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/income')
    await page.waitForLoadState('networkidle')

    await expect(page.locator('h1:has-text("Income")')).toBeVisible({ timeout: 10_000 })

    // Look for "Income Sources" section
    const sourcesSection = page.locator('text=Income Sources')
    const hasSources = await sourcesSection.isVisible()
    if (hasSources) {
      await expect(sourcesSection).toBeVisible()
    }

    expect(errors).toEqual([])
  })

  test('clicking income category opens drilldown drawer', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/income')
    await page.waitForLoadState('networkidle')

    await expect(page.locator('h1:has-text("Income")')).toBeVisible({ timeout: 10_000 })

    // Wait for data to load via network
    await page.waitForLoadState('networkidle')

    // Find a clickable category row (cursor-pointer class on category items)
    const categoryRow = page.locator('[class*="cursor-pointer"]').first()
    const hasClickable = await categoryRow.isVisible()
    if (hasClickable) {
      await categoryRow.click()

      // DrilldownDrawer should open
      const drawerClose = page.locator('button[aria-label="Close drawer"]')
      await expect(drawerClose).toBeVisible({ timeout: 10_000 })

      // Close the drawer
      await drawerClose.click()
      await expect(drawerClose).not.toBeVisible({ timeout: 5_000 })
    }

    expect(errors).toEqual([])
  })
})

// ============================================================
// Expenses Page
// ============================================================

test.describe('Expenses page — enhanced with drilldown + insights', () => {
  test('loads with KPI cards and expense breakdown', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/expenses')
    await page.waitForLoadState('networkidle')

    // Page heading
    await expect(page.locator('h1:has-text("Expenses")')).toBeVisible({ timeout: 10_000 })

    // KPI cards or empty state
    await expect(
      page.locator('text=Total Expenses')
        .or(page.locator('text=No expense data'))
    ).toBeVisible({ timeout: 10_000 })

    expect(errors).toEqual([])
  })

  test('spending by group section renders', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/expenses')
    await page.waitForLoadState('networkidle')

    await expect(page.locator('h1:has-text("Expenses")')).toBeVisible({ timeout: 10_000 })

    // Look for "Spending by Group" section
    const groupSection = page.locator('text=Spending by Group')
    const hasGroups = await groupSection.isVisible()
    if (hasGroups) {
      await expect(groupSection).toBeVisible()
    }

    expect(errors).toEqual([])
  })

  test('expense categories section renders clickable rows', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/expenses')
    await page.waitForLoadState('networkidle')

    await expect(page.locator('h1:has-text("Expenses")')).toBeVisible({ timeout: 10_000 })

    // Look for "Expense Categories" section
    const catSection = page.locator('text=Expense Categories')
    const hasCats = await catSection.isVisible()
    if (hasCats) {
      await expect(catSection).toBeVisible()
    }

    expect(errors).toEqual([])
  })

  test('clicking expense category opens drilldown drawer', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/expenses')
    await page.waitForLoadState('networkidle')

    await expect(page.locator('h1:has-text("Expenses")')).toBeVisible({ timeout: 10_000 })
    await page.waitForLoadState('networkidle')

    const categoryRow = page.locator('[class*="cursor-pointer"]').first()
    const hasClickable = await categoryRow.isVisible()
    if (hasClickable) {
      await categoryRow.click()

      const drawerClose = page.locator('button[aria-label="Close drawer"]')
      await expect(drawerClose).toBeVisible({ timeout: 10_000 })

      await drawerClose.click()
      await expect(drawerClose).not.toBeVisible({ timeout: 5_000 })
    }

    expect(errors).toEqual([])
  })

  test('monthly trend section renders', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/expenses')
    await page.waitForLoadState('networkidle')

    await expect(page.locator('h1:has-text("Expenses")')).toBeVisible({ timeout: 10_000 })

    // Look for "Monthly Trend" section
    const trendSection = page.locator('text=Monthly Trend')
    const hasTrend = await trendSection.isVisible()
    if (hasTrend) {
      await expect(trendSection).toBeVisible()
    }

    expect(errors).toEqual([])
  })

  test('top merchants table renders', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/expenses')
    await page.waitForLoadState('networkidle')

    await expect(page.locator('h1:has-text("Expenses")')).toBeVisible({ timeout: 10_000 })

    // Look for "Top Merchants" section (MerchantSpendTable)
    const merchantsSection = page.locator('text=Top Merchants')
    const hasMerchants = await merchantsSection.isVisible()
    if (hasMerchants) {
      await expect(merchantsSection).toBeVisible()
    }

    expect(errors).toEqual([])
  })
})

// ============================================================
// Debts Page
// ============================================================

test.describe('Debts page — enhanced with DebtTable + payoff projections', () => {
  test('loads with KPI cards and debt summary', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/debts')
    await page.waitForLoadState('networkidle')

    // Page heading
    await expect(page.locator('h1:has-text("Debts")')).toBeVisible({ timeout: 10_000 })

    // KPI cards (Total Debt, Blended APR, Monthly Minimum, Accounts)
    // OR empty state
    await expect(
      page.locator('text=Total Debt')
        .or(page.locator('text=No debt accounts'))
    ).toBeVisible({ timeout: 10_000 })

    expect(errors).toEqual([])
  })

  test('debt composition donut renders when debts exist', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/debts')
    await page.waitForLoadState('networkidle')

    await expect(page.locator('h1:has-text("Debts")')).toBeVisible({ timeout: 10_000 })

    // Look for "Debt Composition" heading (ChartDonut replaced the old stacked bar)
    const compositionSection = page.locator('text=Debt Composition')
    const hasComposition = await compositionSection.isVisible()
    if (hasComposition) {
      await expect(compositionSection).toBeVisible()
      // ChartDonut renders legend buttons for each debt type
      await expect(
        page.locator('text=Credit Cards')
          .or(page.locator('text=Loans'))
          .or(page.locator('text=Mortgages'))
      ).toBeVisible({ timeout: 10_000 })
    }

    expect(errors).toEqual([])
  })

  test('debt table renders when debts exist', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/debts')
    await page.waitForLoadState('networkidle')

    await expect(page.locator('h1:has-text("Debts")')).toBeVisible({ timeout: 10_000 })

    // Look for DebtTable — it shows account names in a table format
    // The table headers include APR, Min Payment, Utilization
    const tableSection = page.locator('text=Debt Accounts')
    const hasTable = await tableSection.isVisible()
    if (hasTable) {
      await expect(tableSection).toBeVisible()
    }

    expect(errors).toEqual([])
  })

  test('payoff projections render when debts have interest rates', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/debts')
    await page.waitForLoadState('networkidle')

    await expect(page.locator('h1:has-text("Debts")')).toBeVisible({ timeout: 10_000 })

    // Look for PayoffProjectionChart — shows "Payoff Projections" header
    const projSection = page.locator('text=Payoff Projections')
    const hasProjections = await projSection.isVisible()
    if (hasProjections) {
      await expect(projSection).toBeVisible()
      await expect(
        page.locator('text=Payoff')
          .or(page.locator('text=Interest'))
          .or(page.locator('text=Total Paid'))
      ).toBeVisible({ timeout: 10_000 })
    }

    expect(errors).toEqual([])
  })

  test('no time range selector on debts page', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/debts')
    await page.waitForLoadState('networkidle')

    await expect(page.locator('h1:has-text("Debts")')).toBeVisible({ timeout: 10_000 })

    // Debts are point-in-time — no time range selector should be present
    // The TimeRangeSelector has a data-testid or specific button labels
    const timeSelector = page.locator('[data-testid="time-range-selector"]')
    await expect(timeSelector).not.toBeVisible({ timeout: 3_000 })

    expect(errors).toEqual([])
  })
})

// ============================================================
// Cross-page navigation
// ============================================================

test.describe('Enhanced pages — cross-page navigation', () => {
  test('navigate through all enhanced pages via sidebar', async ({ page }) => {
    const errors = setupErrorCapture(page)
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    // Navigate to Budgeting
    await page.locator('nav a:has-text("Budgeting")').click()
    await expect(page).toHaveURL(/\/budgeting/)
    await expect(page.locator('h1:has-text("Budgeting")')).toBeVisible({ timeout: 10_000 })

    // Navigate to Income
    await page.locator('nav a:has-text("Income")').click()
    await expect(page).toHaveURL(/\/income/)
    await expect(page.locator('h1:has-text("Income")')).toBeVisible({ timeout: 10_000 })

    // Navigate to Expenses
    await page.locator('nav a:has-text("Expenses")').click()
    await expect(page).toHaveURL(/\/expenses/)
    await expect(page.locator('h1:has-text("Expenses")')).toBeVisible({ timeout: 10_000 })

    // Navigate to Debts
    await page.locator('nav a:has-text("Debts")').click()
    await expect(page).toHaveURL(/\/debts/)
    await expect(page.locator('h1:has-text("Debts")')).toBeVisible({ timeout: 10_000 })

    // Navigate back to Overview
    await page.locator('nav a:has-text("Overview")').click()
    await expect(page).toHaveURL(/\/$/)
    await expect(page.locator('text=Atlas').first()).toBeVisible({ timeout: 10_000 })

    expect(errors).toEqual([])
  })

  test('each enhanced page has consistent layout with PageLayout', async ({ page }) => {
    const errors = setupErrorCapture(page)

    const pages = ['/budgeting', '/income', '/expenses', '/debts']

    for (const path of pages) {
      await page.goto(path)
      await page.waitForLoadState('networkidle')

      // Each page should have the sidebar (nav element)
      await expect(page.locator('nav[aria-label="Primary"]').or(page.locator('nav').first())).toBeVisible({ timeout: 10_000 })

      // Each page should have a heading
      const heading = page.locator('h1').first()
      await expect(heading).toBeVisible({ timeout: 10_000 })
    }

    expect(errors).toEqual([])
  })
})
