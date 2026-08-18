'use client'

/**
 * Vitest tests for the Phase 28 "Untagged" status filter wiring AND the
 * Phase 30 "Untagged" category filter option on the Activity page.
 *
 * Locks the integration between the FE's filter dropdowns and the
 * BE ``?uncategorized=true`` query param:
 *
 *  - The status dropdown renders an "Untagged" option (Phase 28).
 *  - The category dropdown ALSO renders an "Untagged" option (Phase 30)
 *    — previously only real categories were listed, so selecting "Other"
 *    searched for ``category_id = <Other's id>`` rather than
 *    ``category_id IS NULL``.
 *  - Selecting "Untagged" in the category filter triggers a
 *    ``listTransactions`` call with ``uncategorized: true`` AND without
 *    ``category_id``.
 *  - The category-filter Untagged path is symmetric with the
 *    status-filter Untagged path — both suppress ``category_id`` and
 *    ``is_pending``.
 *
 * Mocking strategy mirrors ``recommendations.test.tsx``:
 *   - ``vi.hoisted`` registers the mock functions so the ``vi.mock``
 *     factory can close over the same references (vi.mock is
 *     hoisted above all top-level declarations).
 *   - Only the methods called on mount + by the test interactions
 *     need to be mocked (the page's other handlers are gated on
 *     user actions we never trigger in this test).
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { EmbeddedMoneyView } from '@/components/money/EmbeddedMoneyView'
import { AtlasFilterProvider } from '@/components/ui/AtlasFilterContext'

const {
  listTransactions,
  listAccounts,
  listCategories,
  autoCategorizeAll,
  createMerchantRule,
  updateTransaction,
  acceptCategoryProposal,
} = vi.hoisted(() => ({
  listTransactions: vi.fn(),
  listAccounts: vi.fn(),
  listCategories: vi.fn(),
  autoCategorizeAll: vi
    .fn()
    .mockResolvedValue({ categorized: 0, skipped: 0, total: 0 }),
  createMerchantRule: vi.fn(),
  updateTransaction: vi.fn(),
  acceptCategoryProposal: vi.fn(),
}))

const { rulesServiceModule } = vi.hoisted(() => ({
  rulesServiceModule: {
    listTransactions: (...args: unknown[]) => listTransactions(...args),
    listAccounts: (...args: unknown[]) => listAccounts(...args),
    listCategories: (...args: unknown[]) => listCategories(...args),
    autoCategorizeAll: (...args: unknown[]) => autoCategorizeAll(...args),
    updateTransaction: (...args: unknown[]) => updateTransaction(...args),
    createCategory: vi.fn(),
    categorizeWithLlm: vi.fn().mockResolvedValue({ suggestions: [] }),
    createMerchantRule: (...args: unknown[]) =>
      createMerchantRule(...args),
    acceptCategoryProposal: (...args: unknown[]) =>
      acceptCategoryProposal(...args),
    // PageLayout's bootstrap `useEffect` (which wraps every page in
    // the chrome shell) calls getProfile() once at mount. Provide a
    // resolved stub so the activity page mounts cleanly even when
    // AuthBootstrapProvider leaves the user without a real token.
    getProfile: vi
      .fn()
      .mockResolvedValue({ id: 1, email: 'alex@test.com', full_name: 'Alex' }),
  },
}))

vi.mock('@/lib/api', () => ({
  rulesService: rulesServiceModule,
  classifyCashflow: (txn: { amount: number; account_type?: string | null; description?: string | null }) => ({
    absoluteAmount: Math.abs(txn.amount),
    kind: txn.amount >= 0 ? 'income' : 'expense',
    bucket: txn.amount >= 0 ? 'earn' : 'spend',
    incomeEffect: txn.amount > 0 ? txn.amount : 0,
    expenseEffect: txn.amount < 0 ? Math.abs(txn.amount) : 0,
  }),
  CREDIT_ACCOUNT_TYPES: new Set(['credit_card']),
  CATEGORY_GROUP_ORDER: ['Income', 'Expenses', 'Debt', 'Investments', 'Transfer'] as const,
  CATEGORY_GROUP_COLORS: { Income: '#059669', Expenses: '#DC2626', Debt: '#F59E0B', Investments: '#0EA5E9', Transfer: '#9CA3AF' },
  CATEGORY_GROUP_LABELS: { Income: 'Income', Expenses: 'Expenses', Debt: 'Debt', Investments: 'Investments', Transfer: 'Transfers' },
}))

vi.mock('@/lib/bookkeeping', () => ({
  computeBookkeepingTotals: () => ({ populatedRows: 0, charges: 0, payments: 0, netDebtDelta: 0 }),
  formatBookkeepingCell: () => ({ debitDisplay: '\u2014', creditDisplay: '\u2014', populated: false }),
}))

import ActivityPage from '../page'

describe('Activity Page — Phase 28 + 30 Untagged filter', () => {
  beforeEach(() => {
    listTransactions.mockReset()
    listAccounts.mockReset()
    listCategories.mockReset()
    autoCategorizeAll.mockReset()
    createMerchantRule.mockReset()
    updateTransaction.mockReset()
    listTransactions.mockResolvedValue([])
    listAccounts.mockResolvedValue([])
    listCategories.mockResolvedValue([])
    autoCategorizeAll.mockResolvedValue({
      categorized: 0,
      skipped: 0,
      total: 0,
    })
    createMerchantRule.mockResolvedValue({ id: 99, keyword: 'TEST' })
    updateTransaction.mockResolvedValue({
      id: 1,
      category_id: 5,
      category_name: 'Food',
    })
  })

  // ── Phase 28 — Status filter ──────────────────────────────────

  it('renders the "Untagged" option in the status filter dropdown', () => {
    render(<ActivityPage />)
    const statusSelect = screen.getByTestId('activity-filter-status')
    const options = Array.from(
      statusSelect.querySelectorAll('option'),
    ) as HTMLOptionElement[]
    const labels = options.map((o) => o.textContent)
    expect(labels).toContain('Untagged')
  })

  it('default "All statuses" does NOT set uncategorized on the call', async () => {
    render(<ActivityPage />)
    await waitFor(() => {
      expect(listTransactions).toHaveBeenCalled()
    })
    const firstCall = listTransactions.mock.calls[0]?.[0] as
      | Record<string, unknown>
      | undefined
    expect(firstCall).toBeDefined()
    expect(firstCall).not.toHaveProperty('uncategorized')
  })

  it('selecting "Untagged" (status) calls listTransactions with uncategorized=true', async () => {
    render(<ActivityPage />)
    await waitFor(() => {
      expect(listTransactions).toHaveBeenCalled()
    })
    listTransactions.mockClear()

    const statusSelect = screen.getByTestId('activity-filter-status')
    fireEvent.change(statusSelect, { target: { value: 'untagged' } })

    await waitFor(() => {
      expect(listTransactions).toHaveBeenCalled()
    })
    const lastCall = listTransactions.mock.calls[
      listTransactions.mock.calls.length - 1
    ]?.[0] as Record<string, unknown> | undefined
    expect(lastCall).toBeDefined()
    expect(lastCall).toMatchObject({ uncategorized: true })
  })

  it('selecting "Untagged" (status) suppresses category_id (mutually exclusive)', async () => {
    render(<ActivityPage />)
    await waitFor(() => {
      expect(listTransactions).toHaveBeenCalled()
    })

    const statusSelect = screen.getByTestId('activity-filter-status')
    fireEvent.change(statusSelect, { target: { value: 'untagged' } })

    await waitFor(() => {
      const calls = listTransactions.mock.calls
      const afterChange = calls.find((args) => {
        const p = args[0] as Record<string, unknown>
        return p && 'uncategorized' in p
      })
      expect(afterChange).toBeDefined()
      const p = afterChange?.[0] as Record<string, unknown>
      expect(p).not.toHaveProperty('category_id')
    })
  })

  // ── Phase 30 — Category filter "Untagged" option ───────────────

  it('renders the "Untagged" option in the category filter dropdown', () => {
    render(<ActivityPage />)
    const catSelect = screen.getByTestId('activity-filter-category')
    const options = Array.from(
      catSelect.querySelectorAll('option'),
    ) as HTMLOptionElement[]
    const labels = options.map((o) => o.textContent)
    // Should include "All categories" (default), "Untagged" (new), and any
    // categories returned by the mock.
    expect(labels).toContain('Untagged')
    expect(labels).toContain('All categories')
  })

  it('selecting "Untagged" (category) calls listTransactions with uncategorized=true', async () => {
    render(<ActivityPage />)
    await waitFor(() => {
      expect(listTransactions).toHaveBeenCalled()
    })
    listTransactions.mockClear()

    const catSelect = screen.getByTestId('activity-filter-category')
    fireEvent.change(catSelect, { target: { value: 'untagged' } })

    await waitFor(() => {
      expect(listTransactions).toHaveBeenCalled()
    })
    const lastCall = listTransactions.mock.calls[
      listTransactions.mock.calls.length - 1
    ]?.[0] as Record<string, unknown> | undefined
    expect(lastCall).toBeDefined()
    expect(lastCall).toMatchObject({ uncategorized: true })
  })

  it('selecting "Untagged" (category) suppresses category_id and is_pending', async () => {
    render(<ActivityPage />)
    await waitFor(() => {
      expect(listTransactions).toHaveBeenCalled()
    })
    listTransactions.mockClear()

    const catSelect = screen.getByTestId('activity-filter-category')
    fireEvent.change(catSelect, { target: { value: 'untagged' } })

    await waitFor(() => {
      expect(listTransactions).toHaveBeenCalled()
    })
    const lastCall = listTransactions.mock.calls[
      listTransactions.mock.calls.length - 1
    ]?.[0] as Record<string, unknown> | undefined
    expect(lastCall).toBeDefined()
    // Mutually exclusive — when uncategorized=true, neither category_id
    // nor is_pending should be in the params.
    expect(lastCall).not.toHaveProperty('category_id')
    expect(lastCall).not.toHaveProperty('is_pending')
  })

  it('both Untagged filters set (status + category) still only sends uncategorized=true once', async () => {
    render(<ActivityPage />)
    await waitFor(() => {
      expect(listTransactions).toHaveBeenCalled()
    })
    listTransactions.mockClear()

    // Set both filters to 'untagged'.
    fireEvent.change(screen.getByTestId('activity-filter-status'), {
      target: { value: 'untagged' },
    })
    fireEvent.change(screen.getByTestId('activity-filter-category'), {
      target: { value: 'untagged' },
    })

    await waitFor(() => {
      expect(listTransactions).toHaveBeenCalled()
    })
    const lastCall = listTransactions.mock.calls[
      listTransactions.mock.calls.length - 1
    ]?.[0] as Record<string, unknown> | undefined
    expect(lastCall).toBeDefined()
    // Only one uncategorized param — the combined isUntagged guard
    // merges both paths before the param is set.
    expect(lastCall).toMatchObject({ uncategorized: true })
    expect(lastCall).not.toHaveProperty('category_id')
  })

  // ── Phase 31 — Editable keyword + auto-categorize after promote ─

  it('promote panel shows an editable keyword input (not readonly text)', async () => {
    listTransactions.mockResolvedValue([
      {
        id: 1,
        description: 'AMAZON.COM PURCHASE',
        merchant_name: 'AMAZON',
        amount: -29.99,
        category_id: null,
        category_name: null,
        account_name: 'Checking',
        account_type: 'checking',
        is_pending: false,
        transaction_date: '2025-06-01T12:00:00Z',
      },
    ])
    render(<ActivityPage />)
    await waitFor(() => {
      expect(listTransactions).toHaveBeenCalled()
    })

    // Click the "Promote to rule" button on row 1.
    const trigger = screen.getByTestId('activity-promote-trigger-1')
    fireEvent.click(trigger)

    // The promote panel should render an <input> for the keyword
    // (Phase 31 changed this from a read-only <p> to an editable field).
    const keywordInput = screen.getByTestId('activity-promote-keyword-input-1')
    expect(keywordInput).toBeDefined()
    // The input should be pre-filled with the merchant name, uppercased.
    expect((keywordInput as HTMLInputElement).value).toBe('AMAZON')
  })

  it('editing the keyword and picking a category passes the edited keyword to createMerchantRule', async () => {
    listTransactions.mockResolvedValue([
      {
        id: 1,
        description: 'AMAZON PRIME MEMBERSHIP',
        merchant_name: 'AMAZON PRIME MEMBERSHIP',
        amount: -14.99,
        category_id: null,
        category_name: null,
        account_name: 'Checking',
        account_type: 'checking',
        is_pending: false,
        transaction_date: '2025-06-01T12:00:00Z',
      },
    ])
    listCategories.mockResolvedValue([
      { id: 5, name: 'Subscriptions', color: '#f59e0b' },
    ])
    render(<ActivityPage />)
    await waitFor(() => {
      expect(listTransactions).toHaveBeenCalled()
    })

    // Open the promote panel.
    fireEvent.click(screen.getByTestId('activity-promote-trigger-1'))

    // Edit the keyword to simplify it from the verbose merchant name.
    const keywordInput = screen.getByTestId(
      'activity-promote-keyword-input-1',
    ) as HTMLInputElement
    fireEvent.change(keywordInput, { target: { value: 'amazon' } })
    expect(keywordInput.value).toBe('amazon')

    // Pick the "Subscriptions" category.
    const option = screen.getByTestId('activity-promote-option-1-5')
    fireEvent.click(option)

    await waitFor(() => {
      // The edited keyword (uppercased) should be passed, not the
      // original 'AMAZON PRIME MEMBERSHIP'.
      expect(createMerchantRule).toHaveBeenCalledWith(
        expect.objectContaining({ keyword: 'AMAZON' }),
      )
    })
  })

  it('autoCategorizeAll is called after promote-to-rule and its result appears in the message', async () => {
    listTransactions.mockResolvedValue([
      {
        id: 1,
        description: 'NETFLIX.COM',
        merchant_name: 'NETFLIX',
        amount: -15.99,
        category_id: null,
        category_name: null,
        account_name: 'Checking',
        account_type: 'checking',
        is_pending: false,
        transaction_date: '2025-06-01T12:00:00Z',
      },
    ])
    listCategories.mockResolvedValue([
      { id: 5, name: 'Subscriptions', color: '#f59e0b' },
    ])
    autoCategorizeAll.mockResolvedValue({
      categorized: 3,
      skipped: 1,
      total: 4,
    })
    render(<ActivityPage />)
    await waitFor(() => {
      expect(listTransactions).toHaveBeenCalled()
    })

    // Promote the NETFLIX row.
    fireEvent.click(screen.getByTestId('activity-promote-trigger-1'))
    fireEvent.click(screen.getByTestId('activity-promote-option-1-5'))

    await waitFor(() => {
      expect(createMerchantRule).toHaveBeenCalled()
      // After rule creation, autoCategorizeAll should be called.
      expect(autoCategorizeAll).toHaveBeenCalled()
      // The success message should include auto-categorize results.
      const banner = screen.getByTestId('activity-auto-tag-message')
      expect(banner.textContent).toContain('tagged 3 of 4')
      expect(banner.textContent).toContain('1 already tagged')
    })
  })
})

describe('Activity Page — categorize toolbar visibility', () => {
  beforeEach(() => {
    listTransactions.mockReset()
    listAccounts.mockReset()
    listCategories.mockReset()
    listTransactions.mockResolvedValue([])
    listAccounts.mockResolvedValue([])
    listCategories.mockResolvedValue([])
  })

  it('renders the AI auto-tag button in the standalone page header', () => {
    render(<ActivityPage />)
    expect(screen.getByTestId('activity-ai-categorize-button')).toBeInTheDocument()
    expect(screen.getByTestId('activity-auto-categorize-button')).toBeInTheDocument()
  })

  it('renders the AI auto-tag button in the embedded Cash Flow view', () => {
    render(
      <AtlasFilterProvider>
        <EmbeddedMoneyView>
          <ActivityPage />
        </EmbeddedMoneyView>
      </AtlasFilterProvider>,
    )
    // The embedded toolbar surfaces the same categorize actions that the
    // standalone page header shows, so LLM auto-tag stays reachable under
    // the canonical information architecture.
    expect(screen.getByTestId('activity-embedded-toolbar')).toBeInTheDocument()
    expect(screen.getByTestId('activity-ai-categorize-button')).toBeInTheDocument()
    expect(screen.getByTestId('activity-auto-categorize-button')).toBeInTheDocument()
  })

  it('embedded view does not render the standalone page header', () => {
    render(
      <AtlasFilterProvider>
        <EmbeddedMoneyView>
          <ActivityPage />
        </EmbeddedMoneyView>
      </AtlasFilterProvider>,
    )
    expect(screen.queryByText('Transaction History')).not.toBeInTheDocument()
  })
})

describe('Activity Page — LLM new-category proposals', () => {
  beforeEach(() => {
    listTransactions.mockReset()
    listAccounts.mockReset()
    listCategories.mockReset()
    autoCategorizeAll.mockReset()
    createMerchantRule.mockReset()
    updateTransaction.mockReset()
    acceptCategoryProposal.mockReset()
    listAccounts.mockResolvedValue([])
    listCategories.mockResolvedValue([])
    autoCategorizeAll.mockResolvedValue({
      categorized: 0,
      skipped: 0,
      total: 0,
    })
    updateTransaction.mockResolvedValue({ id: 1, category_id: 5 })
    // A single untagged transaction the LLM will propose a new
    // category for.
    listTransactions.mockResolvedValue([
      {
        id: 1,
        account_id: 10,
        description: 'PETSMART',
        merchant_name: 'PETSMART',
        amount: -45.0,
        transaction_date: '2026-08-01',
        category_id: null,
        is_duplicate: false,
      },
    ])
  })

  it('renders the propose-new chip and accepts via acceptCategoryProposal', async () => {
    const { categorizeWithLlm } = rulesServiceModule
    ;(categorizeWithLlm as ReturnType<typeof vi.fn>).mockResolvedValue({
      suggestions: [
        {
          txn_id: 1,
          suggested_category: 'Other',
          confidence: 0.92,
          coerced: true,
          is_new: true,
          proposed_category: 'Pet Supplies',
          proposed_parent: 'Shopping',
        },
      ],
    })
    ;(acceptCategoryProposal as ReturnType<typeof vi.fn>).mockResolvedValue({
      transaction_id: 1,
      category_id: 77,
      category_name: 'Pet Supplies',
      category_created: true,
      parent_name: 'Shopping',
      rule_id: 5,
      rule_created: true,
    })

    render(<ActivityPage />)
    // Wait for the untagged row to load (the button is disabled until
    // ``untaggedRows`` is non-empty, and the click handler bails on
    // an empty candidate set).
    await waitFor(() => {
      expect(screen.getByTestId('activity-ai-categorize-button')).not.toBeDisabled()
    })
    fireEvent.click(screen.getByTestId('activity-ai-categorize-button'))

    // The proposal chip renders with the proposed name + parent.
    const chip = await screen.findByTestId('activity-llm-proposal-1')
    expect(chip.textContent).toContain('Pet Supplies')
    expect(chip.textContent).toContain('Shopping')

    fireEvent.click(screen.getByTestId('activity-llm-accept-1'))

    await waitFor(() => {
      expect(acceptCategoryProposal).toHaveBeenCalledWith({
        transaction_id: 1,
        proposed_category: 'Pet Supplies',
        proposed_parent: 'Shopping',
        keyword: 'PETSMART',
      })
    })
    // The suggestion is removed from the panel after accept.
    await waitFor(() => {
      expect(screen.queryByTestId('activity-llm-proposal-1')).not.toBeInTheDocument()
    })
    // The new category list is refreshed so the taxonomy picks it up.
    expect(listCategories).toHaveBeenCalled()
  })

  it('regular (non-proposal) accept still routes through updateTransaction', async () => {
    const { categorizeWithLlm } = rulesServiceModule
    ;(categorizeWithLlm as ReturnType<typeof vi.fn>).mockResolvedValue({
      suggestions: [
        {
          txn_id: 1,
          suggested_category: 'Food & Dining',
          confidence: 0.9,
        },
      ],
    })
    listCategories.mockResolvedValue([
      { id: 3, name: 'Food & Dining', group: 'Expenses' },
    ])

    render(<ActivityPage />)
    await waitFor(() => {
      expect(screen.getByTestId('activity-ai-categorize-button')).not.toBeDisabled()
    })
    fireEvent.click(screen.getByTestId('activity-ai-categorize-button'))

    await screen.findByTestId('activity-llm-accept-1')
    fireEvent.click(screen.getByTestId('activity-llm-accept-1'))

    await waitFor(() => {
      expect(updateTransaction).toHaveBeenCalled()
    })
    expect(acceptCategoryProposal).not.toHaveBeenCalled()
  })
})
