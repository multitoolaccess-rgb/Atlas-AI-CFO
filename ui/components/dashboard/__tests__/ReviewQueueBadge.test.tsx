import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ReviewQueueBadge from '@/components/dashboard/ReviewQueueBadge'
import type { Transaction } from '@/lib/api'

function makeTxn(overrides: Partial<Transaction> = {}): Transaction {
  return {
    id: 1,
    description: 'Test transaction',
    amount: -50,
    transaction_date: '2026-07-01',
    is_pending: false,
    ...overrides,
  }
}

describe('ReviewQueueBadge', () => {
  it('renders nothing when all transactions are categorized', () => {
    const txns = [
      makeTxn({ category_id: 1, category_name: 'Food' }),
      makeTxn({ id: 2, category_id: 2, category_name: 'Transport' }),
    ]
    const { container } = render(<ReviewQueueBadge transactions={txns} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when transactions array is empty', () => {
    const { container } = render(<ReviewQueueBadge transactions={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('shows count when transactions have no category', () => {
    const txns = [
      makeTxn({ category_id: 1, category_name: 'Food' }),
      makeTxn({ id: 2, category_id: null, category_name: null }),
      makeTxn({ id: 3, category_id: null, category_name: null }),
    ]
    render(<ReviewQueueBadge transactions={txns} />)
    expect(screen.getByText('2 need review')).toBeInTheDocument()
  })

  it('links to the activity page with uncategorized filter', () => {
    const txns = [makeTxn({ category_id: null, category_name: null })]
    render(<ReviewQueueBadge transactions={txns} />)
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '/activity?status=uncategorized')
  })

  it('has accessible aria-label with count', () => {
    const txns = [
      makeTxn({ category_id: null, category_name: null }),
      makeTxn({ id: 2, category_id: null, category_name: null }),
      makeTxn({ id: 3, category_id: null, category_name: null }),
    ]
    render(<ReviewQueueBadge transactions={txns} />)
    expect(screen.getByLabelText('3 transactions need categorization')).toBeInTheDocument()
  })

  it('treats empty string category_name as uncategorized', () => {
    const txns = [makeTxn({ category_id: null, category_name: '' })]
    render(<ReviewQueueBadge transactions={txns} />)
    expect(screen.getByText('1 need review')).toBeInTheDocument()
  })
})
