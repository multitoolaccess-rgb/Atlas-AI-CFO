import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import FinancialUniverse, { buildBodies } from '../FinancialUniverse'
import type { Account, Goal, DebtItem } from '@/lib/api'

const accounts: Account[] = [
  {
    id: 1,
    account_name: 'Checking',
    account_type: 'checking',
    current_balance: 5000,
    is_active: true,
    family_member_id: 1,
  },
  {
    id: 2,
    account_name: 'Investment',
    account_type: 'investment',
    current_balance: 25000,
    is_active: true,
    family_member_id: 1,
  },
]

const goals: Goal[] = [
  {
    id: 1,
    name: 'Vacation',
    target_amount: 3000,
    priority: 1,
    is_archived: false,
  },
]

const debts: DebtItem[] = [
  {
    account_id: 3,
    account_name: 'Credit Card',
    account_type: 'credit_card',
    balance: -1200,
    interest_rate: 0.18,
    minimum_payment: 50,
    credit_limit: 5000,
    term_months: null,
    utilization: 0.24,
  },
]

describe('FinancialUniverse', () => {
  let originalMatchMedia: typeof window.matchMedia

  beforeEach(() => {
    originalMatchMedia = window.matchMedia
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
  })

  afterEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: originalMatchMedia,
    })
  })

  it('renders the universe scene and nodes', () => {
    render(<FinancialUniverse accounts={accounts} goals={goals} debts={debts} />)

    expect(screen.getByTestId('financial-universe')).toBeInTheDocument()
    expect(screen.getByTestId('universe-scene')).toBeInTheDocument()
    expect(screen.getByTestId('universe-node-account-1')).toBeInTheDocument()
    expect(screen.getByTestId('universe-node-goal-1')).toBeInTheDocument()
    expect(screen.getByTestId('universe-node-debt-3')).toBeInTheDocument()
  })

  it('shows a focus panel when a node is clicked', () => {
    render(<FinancialUniverse accounts={accounts} goals={goals} debts={debts} />)

    fireEvent.click(screen.getByTestId('universe-node-account-1'))
    expect(screen.getByText('Checking')).toBeInTheDocument()
    expect(screen.getByText('5,000')).toBeInTheDocument()
  })

  it('builds bodies with correct 3D positions', () => {
    const bodies = buildBodies(accounts, goals, debts)
    expect(bodies).toHaveLength(4)

    const checking = bodies.find((b) => b.id === 'account-1')
    expect(checking).toBeDefined()
    expect(checking?.type).toBe('account')
    expect(typeof checking?.x).toBe('number')
    expect(typeof checking?.y).toBe('number')
    expect(typeof checking?.z).toBe('number')
  })

  it('renders empty state when no data is provided', () => {
    render(<FinancialUniverse accounts={[]} goals={[]} debts={[]} />)
    expect(screen.getByTestId('financial-universe')).toBeInTheDocument()
    expect(screen.getByText(/0 celestial bodies/)).toBeInTheDocument()
  })
})
