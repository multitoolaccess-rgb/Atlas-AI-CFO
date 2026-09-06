/**
 * Phase A+B+C regression suite — locks in the existence of the floating
 * time-range bar on all 9 migrated pages:
 *   A+B: expenses, income, budgeting, debts (already-proxied)
 *   C:   activity, goals, universe, accounts, portfolio (new)
 *
 * Without this suite, a future refactor that accidentally removes
 * the bar or drops the provider wrap from any of these pages would
 * slip through CI and surface later as a user-visible
 * "range selector missing" bug.
 *
 * What this suite guards (per migrated page):
 *   1. The bar's "Range" label is in the DOM.
 *   2. All 8 TimeRangeSelector presets render as role="radio" elements.
 *   3. YTD is the default aria-checked preset on mount.
 *   4. Clicking 30D flips aria-checked (URL-sync contract).
 *
 * What this suite does NOT guard (intentional — covered elsewhere):
 *   - Bar internals (FloatingTimeRangeBar.test.tsx).
 *   - URL-syncing behavior on real router (Playwright e2e in plans).
 *   - Per-page data hooks honoring timeRange (covered by FE/BE
 *     contract tests for the ranged endpoints).
 *
 * Mocking strategy: jsdom can't host real Next.js App Router, fetch,
 * chart libraries, or 3D tilt cards, so the deep mocks below isolate
 * each page to its bar-rendering path. The bar itself is REAL — that's
 * the whole point of the migration.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

// ---- Hoisted mocks ----------------------------------------------------

// 1. App-router stubs — global mock lives in vitest.setup.ts


// 2. Page-layout chrome — render bare children.
vi.mock('@/components/layout/PageLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('@/components/layout/Sidebar', () => ({ default: () => null }))
vi.mock('@/components/layout/Header', () => ({ default: () => null }))

// 3. The atlas API — return safe resolved defaults so each page's
// loadData() resolves to the empty branch and the page renders a
// non-throwing dashboard instead of an infinite loading skeleton.
vi.mock('@/lib/api', () => ({
  rulesService: {
    getExpenseBreakdown: () =>
      Promise.resolve({ total_expenses: 0, by_category: [], by_group: [], trend: [] }),
    getIncomeBreakdown: () =>
      Promise.resolve({ total_income: 0, by_category: [], by_group: [], trend: [] }),
    getDebtsSummary: () =>
      Promise.resolve({
        debts: [],
        total_debt: 0,
        blended_apr: 0,
        total_monthly_minimum: 0,
      }),
    getBudgetStatus: () =>
      Promise.resolve({
        totals: { planned: 0, actual: 0, remaining: 0, percent_used: 0 },
        categories: [],
        period_txn_count: 0,
        latest_data_month: null,
      }),
    listBudgets: () => Promise.resolve([]),
    listCategories: () => Promise.resolve([]),
    listTransactions: () => Promise.resolve([]),
    // Phase C — activity, goals, universe, accounts, portfolio
    listGoals: () => Promise.resolve([]),
    getDashboardSummary: () =>
      Promise.resolve({
        total_balance: 0,
        total_income_month: 0,
        total_expenses_month: 0,
        accounts_count: 0,
        transactions_count: 0,
        import_batches_count: 0,
        last_sync: null,
        last_import_at: null,
        user_goals: [],
      }),
    listAccounts: () => Promise.resolve([]),
    listHoldings: () => Promise.resolve([]),
    getProfile: () => Promise.resolve({ full_name: 'Test User' }),
    listFamilyMembers: () => Promise.resolve([]),
    autoCategorizeAll: () => Promise.resolve({ categorized: 0, total: 0, skipped: 0 }),
    createMerchantRule: () => Promise.resolve({}),
    updateTransaction: () => Promise.resolve({}),
    categorizeWithLlm: () => Promise.resolve({ suggestions: [] }),
    resolveDuplicate: () => Promise.resolve({ message: 'Resolved' }),
    resolveAllDuplicates: () => Promise.resolve({ message: 'Resolved all' }),
    createGoal: () => Promise.resolve({}),
    updateGoal: () => Promise.resolve({}),
    deleteGoal: () => Promise.resolve({}),
    createAccount: () => Promise.resolve({}),
    updateAccount: () => Promise.resolve({}),
    deleteAccount: () => Promise.resolve({}),
    createHolding: () => Promise.resolve({}),
    updateHolding: () => Promise.resolve({}),
    deleteHolding: () => Promise.resolve({}),
    refreshPrices: () => Promise.resolve({ prices_updated: 0, holdings: [] }),
    importPortfolio: () => Promise.resolve({ holdings_count: 0, account_ids: [], total_value: 0, accounts_created: 0 }),
    getAnalystRatings: () => Promise.resolve({ recommendation_trends: [] }),
    getBatchAnalystRatings: () => Promise.resolve({ results: [] }),
    createBudget: () => Promise.resolve({}),
  },
  classifyCashflow: () => ({ incomeEffect: 0, expenseEffect: 0 }),
  CREDIT_ACCOUNT_TYPES: new Set(),
  ACCOUNT_SOURCE_LABELS: {},
  // Phase 2 pages import the default API client through api_phase2.
  // Keep the seam present even though these shallow page tests render
  // empty data and do not exercise forecast reads.
  default: {
    get: () => Promise.resolve({ data: { forecasts: [] } }),
    post: () => Promise.resolve({ data: {} }),
  },
}))

// 4. Heavy page-specific components — render null so vibratory
// data deps don't crash jsdom. The bar is the only thing this
// suite asserts about.
vi.mock('@/components/charts/BreakdownDonut', () => ({ default: () => null }))
vi.mock('@/components/charts/VerticalBarChart', () => ({ default: () => null }))
vi.mock('@/components/charts/TreemapChart', () => ({ default: () => null }))
vi.mock('@/components/charts/ChartDonut', () => ({ default: () => null }))
vi.mock('@/components/dashboard/MerchantSpendTable', () => ({ default: () => null }))
vi.mock('@/components/dashboard/InsightsBanner', () => ({ default: () => null }))
vi.mock('@/components/dashboard/DrilldownDrawer', () => ({ default: () => null }))
vi.mock('@/components/dashboard/DebtTable', () => ({ default: () => null }))
vi.mock('@/components/dashboard/PayoffProjectionChart', () => ({ default: () => null }))
vi.mock('@/components/dashboard/PayoffComparison', () => ({ default: () => null }))
vi.mock('@/components/dashboard/BudgetCategoryCard', () => ({ default: () => null }))
vi.mock('@/components/dashboard/HeroSummary', () => ({ default: () => null }))
vi.mock('@/components/dashboard/FinancialPlans', () => ({
  default: () => null,
  GOAL_PROJECTION_ANNUAL_RETURN: 0.07,
}))
vi.mock('@/components/charts/AnimatedRadialProgress', () => ({ default: () => null }))
vi.mock('@/components/universe/FinancialUniverse', () => ({ default: () => null }))
vi.mock('@/components/imports/ImportStatementUpload', () => ({ default: () => null }))

// 5. Shell wrappers — render bare children so page DOM is shallow.
vi.mock('@/components/dashboard/ExpandableCard', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('@/components/cards/AnimatedKPICard', () => ({ default: () => null }))
vi.mock('@/components/ui/TiltCard', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('@/components/ui/AnimatedSection', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('@/components/ui/AnimatedPageSection', () => ({
  // Defensive: Debts wraps content in AnimatedPageSection (likely uses
  // IntersectionObserver). Render bare children so a future refactor that
  // adds visibility-gated animations can't silently regress Debts render.
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

// ---- Page imports (must come AFTER the mocks so vi.mock hoisting wins) -

import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import ExpensesPage from '@/app/expenses/page'
import IncomePage from '@/app/income/page'
import BudgetingPage from '@/app/budgeting/page'
import DebtsPage from '@/app/debts/page'
import ActivityPage from '@/app/activity/page'
import GoalsPage from '@/app/goals/page'
import UniversePage from '@/app/universe/page'
import AccountsPage from '@/app/accounts/page'
import PortfolioPage from '@/app/portfolio/page'

beforeEach(() => {
  cleanup()
  window.history.replaceState(window.history.state, '', '/')
})

// ---- Suite ------------------------------------------------------------

const MIGRATED_PAGES: Array<[string, React.ComponentType]> = [
  // Phase A+B — already-proxied pages
  ['expenses', ExpensesPage],
  ['income', IncomePage],
  ['debts', DebtsPage],
  // Phase C — newly migrated pages
  ['activity', ActivityPage],
  ['goals', GoalsPage],
  ['universe', UniversePage],
  ['accounts', AccountsPage],
  ['portfolio', PortfolioPage],
]

// Budgeting keys by month (BE budget contract), so it deliberately shows
// only the authoritative month "Period" control and NOT the date-window
// Range selector — the old dual control was a dead Range no-op next to
// the real Period input (consistency fix). Guarded separately below.

const ALL_PRESETS = ['7D', '30D', '90D', 'MTD', 'QTD', 'YTD', '1Y', 'All']

describe.each(MIGRATED_PAGES)(
  'Floating time-range bar — /%s page',
  (_path, Page) => {
    it('renders the bar with the "Range" label (invariant 1)', () => {
      render(<Page />)
      // Floating bar exact label; not the period input or anything else
      expect(screen.getByText(/^Range$/)).toBeInTheDocument()
    })

    it('exposes all 8 TimeRangeSelector presets as role="radio" (invariant 2)', () => {
      // Component-level preset-by-preset coverage lives in
      // FloatingTimeRangeBar.test.tsx; this assertion is the
      // migration-level smoke check that each consumer still gets
      // every preset rendered (e.g. a future refactor that strips
      // some presets in the consumers' provider wrap would fail).
      render(<Page />)
      for (const preset of ALL_PRESETS) {
        expect(
          screen.getByRole('radio', { name: new RegExp(`^${preset}$`, 'i') }),
        ).toBeInTheDocument()
      }
    })

    it('YTD preset is the default — aria-checked="true" on mount (invariant 3)', () => {
      render(<Page />)
      const ytd = screen.getByRole('radio', { name: /^YTD$/ }) as HTMLButtonElement
      // No URL ?range=... in jsdom default — AtlasFilterProvider
      // therefore falls back to YTD per its design.
      expect(ytd.getAttribute('aria-checked')).toBe('true')
    })

    it('clicking 30D flips aria-checked (URL-sync contract is live)', async () => {
      // The mock router discards `params.set('range', ...)`, but the
      // context's own React state still flips IN-MEMORY after the
      // click — observable via the TimeRangeSelector's aria-checked.
      // This is the real wiring check: "Range", "30D", and YTD's
      // aria-checked are all on the same component instance; if the
      // context wiring broke (e.g. someone reverted to an in-memory
      // AtlasFilterProvider stub), YTD would stay checked and 30D
      // would stay unchecked.
      render(<Page />)
      const ytd = screen.getByRole('radio', { name: /^YTD$/ }) as HTMLButtonElement
      const thirty = screen.getByRole('radio', { name: /^30D$/ }) as HTMLButtonElement
      expect(ytd.getAttribute('aria-checked')).toBe('true')
      fireEvent.click(thirty)
      // React state update is async; waitFor retries until both
      // assertions are simultaneously true.
      await waitFor(() => {
        expect(thirty.getAttribute('aria-checked')).toBe('true')
        expect(ytd.getAttribute('aria-checked')).toBe('false')
      })
    })
  },
)

describe('Floating time-range bar — /budgeting page (month-period contract)', () => {
  it('renders a month Period selector consistent with the range-bar styling', () => {
    render(<BudgetingPage />)
    // The month selector drives every budget read/write (getBudgetStatus,
    // listBudgets, createBudget). It reuses the range-bar pill language:
    // chevron navigation + This/Last month quick pills.
    expect(screen.getByText('Period')).toBeInTheDocument()
    expect(screen.getByText('This month')).toBeInTheDocument()
    expect(screen.getByText('Last month')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous month' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next month' })).toBeInTheDocument()
    // The date-window Range presets stay intentionally absent: budgeting
    // keys by YYYY-MM, so 7D/90D would be a dead control.
    expect(screen.queryByText(/^Range$/)).not.toBeInTheDocument()
    expect(
      screen.queryByRole('radio', { name: /^(7D|30D|90D|MTD|QTD|YTD|1Y|All)$/ }),
    ).not.toBeInTheDocument()
  })
})
