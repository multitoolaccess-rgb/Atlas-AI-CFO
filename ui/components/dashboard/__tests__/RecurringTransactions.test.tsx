import { describe, it, expect, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import RecurringTransactions, { detectRecurring } from '@/components/dashboard/RecurringTransactions'
import type { Transaction } from '@/lib/api'

// jsdom does not provide window.matchMedia — stub it for useThemeMode()
beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  })
})

function makeTxn(overrides: Partial<Transaction> = {}): Transaction {
  return {
    id: 1,
    description: 'TEST MERCHANT',
    amount: -29.99,
    transaction_date: '2026-06-01T12:00:00Z',
    merchant_name: 'TEST MERCHANT',
    is_pending: false,
    category_id: 5,
    category_name: 'Subscriptions',
    account_name: 'Checking',
    account_type: 'checking',
    ...overrides,
  }
}

describe('detectRecurring', () => {
  it('returns empty array for fewer than 2 transactions', () => {
    expect(detectRecurring([makeTxn()])).toEqual([])
    expect(detectRecurring([])).toEqual([])
  })

  it('returns empty array when no pattern is detected', () => {
    // Random transactions with no recurring pattern
    const txns = [
      makeTxn({ id: 1, merchant_name: 'STARBUCKS', transaction_date: '2026-01-01T00:00:00Z' }),
      makeTxn({ id: 2, merchant_name: 'AMAZON', transaction_date: '2026-02-15T00:00:00Z' }),
      makeTxn({ id: 3, merchant_name: 'WALMART', transaction_date: '2026-03-20T00:00:00Z' }),
    ]
    expect(detectRecurring(txns)).toEqual([])
  })

  it('detects monthly subscriptions', () => {
    const txns = [
      makeTxn({ id: 1, merchant_name: 'NETFLIX', amount: -15.99, transaction_date: '2026-01-05T00:00:00Z' }),
      makeTxn({ id: 2, merchant_name: 'NETFLIX', amount: -15.99, transaction_date: '2026-02-05T00:00:00Z' }),
      makeTxn({ id: 3, merchant_name: 'NETFLIX', amount: -15.99, transaction_date: '2026-03-05T00:00:00Z' }),
      makeTxn({ id: 4, merchant_name: 'NETFLIX', amount: -15.99, transaction_date: '2026-04-05T00:00:00Z' }),
    ]
    const result = detectRecurring(txns)
    expect(result).toHaveLength(1)
    expect(result[0].merchant).toBe('NETFLIX')
    expect(result[0].frequency).toBe('monthly')
    expect(result[0].avgAmount).toBeCloseTo(15.99, 1)
    expect(result[0].occurrences).toBe(4)
  })

  it('detects weekly subscriptions', () => {
    const txns = [
      makeTxn({ id: 1, merchant_name: 'GYM WEEKLY', amount: -10, transaction_date: '2026-06-01T00:00:00Z' }),
      makeTxn({ id: 2, merchant_name: 'GYM WEEKLY', amount: -10, transaction_date: '2026-06-08T00:00:00Z' }),
      makeTxn({ id: 3, merchant_name: 'GYM WEEKLY', amount: -10, transaction_date: '2026-06-15T00:00:00Z' }),
      makeTxn({ id: 4, merchant_name: 'GYM WEEKLY', amount: -10, transaction_date: '2026-06-22T00:00:00Z' }),
    ]
    const result = detectRecurring(txns)
    expect(result).toHaveLength(1)
    expect(result[0].frequency).toBe('weekly')
    expect(result[0].frequencyLabel).toBe('Weekly')
  })

  it('sorts results by estimated monthly cost (highest first)', () => {
    const txns = [
      makeTxn({ id: 1, merchant_name: 'CHEAP SUB', amount: -5, transaction_date: '2026-01-01T00:00:00Z' }),
      makeTxn({ id: 2, merchant_name: 'CHEAP SUB', amount: -5, transaction_date: '2026-02-01T00:00:00Z' }),
      makeTxn({ id: 3, merchant_name: 'CHEAP SUB', amount: -5, transaction_date: '2026-03-01T00:00:00Z' }),
      makeTxn({ id: 4, merchant_name: 'EXPENSIVE SUB', amount: -50, transaction_date: '2026-01-01T00:00:00Z' }),
      makeTxn({ id: 5, merchant_name: 'EXPENSIVE SUB', amount: -50, transaction_date: '2026-02-01T00:00:00Z' }),
      makeTxn({ id: 6, merchant_name: 'EXPENSIVE SUB', amount: -50, transaction_date: '2026-03-01T00:00:00Z' }),
    ]
    const result = detectRecurring(txns)
    expect(result).toHaveLength(2)
    expect(result[0].merchant).toBe('EXPENSIVE SUB')
    expect(result[1].merchant).toBe('CHEAP SUB')
  })

  it('skips micro-transactions under $1', () => {
    const txns = [
      makeTxn({ id: 1, merchant_name: 'PENNY', amount: -0.01, transaction_date: '2026-01-01T00:00:00Z' }),
      makeTxn({ id: 2, merchant_name: 'PENNY', amount: -0.01, transaction_date: '2026-02-01T00:00:00Z' }),
      makeTxn({ id: 3, merchant_name: 'PENNY', amount: -0.01, transaction_date: '2026-03-01T00:00:00Z' }),
    ]
    expect(detectRecurring(txns)).toEqual([])
  })

  it('handles positive amounts (refunds/income) by using absolute value', () => {
    const txns = [
      makeTxn({ id: 1, merchant_name: 'DIVIDEND', amount: 100, transaction_date: '2026-01-15T00:00:00Z' }),
      makeTxn({ id: 2, merchant_name: 'DIVIDEND', amount: 100, transaction_date: '2026-02-15T00:00:00Z' }),
      makeTxn({ id: 3, merchant_name: 'DIVIDEND', amount: 100, transaction_date: '2026-03-15T00:00:00Z' }),
    ]
    const result = detectRecurring(txns)
    expect(result).toHaveLength(1)
    expect(result[0].avgAmount).toBeCloseTo(100, 1)
  })
})

describe('RecurringTransactions component', () => {
  it('renders nothing when no subscriptions detected and not loading', () => {
    const { container } = render(
      <RecurringTransactions transactions={[makeTxn()]} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders skeleton when loading', () => {
    render(<RecurringTransactions transactions={[]} loading />)
    // Loading skeleton should have skeleton elements
    expect(document.querySelectorAll('.skeleton').length).toBeGreaterThan(0)
  })

  it('renders nothing when no patterns detected and not loading', () => {
    const { container } = render(
      <RecurringTransactions
        transactions={[
          makeTxn({ id: 1, merchant_name: 'A', transaction_date: '2026-01-01T00:00:00Z' }),
          makeTxn({ id: 2, merchant_name: 'B', transaction_date: '2026-02-01T00:00:00Z' }),
        ]}
      />,
    )
    // Component returns null when no recurring patterns found and not loading
    expect(container.firstChild).toBeNull()
  })

  it('renders detected subscriptions with merchant names', () => {
    const txns = [
      makeTxn({ id: 1, merchant_name: 'NETFLIX', amount: -15.99, transaction_date: '2026-01-05T00:00:00Z' }),
      makeTxn({ id: 2, merchant_name: 'NETFLIX', amount: -15.99, transaction_date: '2026-02-05T00:00:00Z' }),
      makeTxn({ id: 3, merchant_name: 'NETFLIX', amount: -15.99, transaction_date: '2026-03-05T00:00:00Z' }),
    ]
    render(<RecurringTransactions transactions={txns} />)
    // NETFLIX appears in summary cards — use getAllByText
    const netflixElements = screen.getAllByText('NETFLIX')
    expect(netflixElements.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/detected/)).toBeInTheDocument()
  })

  it('has accessible ExpandableCard structure', () => {
    const txns = [
      makeTxn({ id: 1, merchant_name: 'SPOTIFY', amount: -9.99, transaction_date: '2026-01-01T00:00:00Z' }),
      makeTxn({ id: 2, merchant_name: 'SPOTIFY', amount: -9.99, transaction_date: '2026-02-01T00:00:00Z' }),
      makeTxn({ id: 3, merchant_name: 'SPOTIFY', amount: -9.99, transaction_date: '2026-03-01T00:00:00Z' }),
    ]
    render(<RecurringTransactions transactions={txns} />)
    expect(screen.getByText('Subscriptions & Recurring')).toBeInTheDocument()
  })
})
