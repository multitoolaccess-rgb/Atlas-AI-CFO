import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import PortfolioIntelligencePage from '@/app/portfolio/intelligence/page'
import { rulesService } from '@/lib/api'

vi.mock('@/components/layout/PageLayout', () => ({ default: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/components/ui/PageHeader', () => ({ default: ({ title, description }: { title: string; description?: string }) => <header><h1>{title}</h1><p>{description}</p></header> }))
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return { ...actual, rulesService: { getDashboardSummary: vi.fn(), listAccounts: vi.fn(), listHoldings: vi.fn() } }
})

const account = { id: 1, account_name: 'Brokerage', account_type: 'investment', current_balance: 1500, is_active: true, family_member_id: 1 }
const holdings = [
  { id: 11, account_id: 1, symbol: 'AAPL', description: 'Apple', quantity: 5, current_value: 1000, last_price: 200, cost_basis_total: 800, type: 'Stock' },
  { id: 12, account_id: 1, symbol: null, description: null, quantity: null, current_value: 0, last_price: null, cost_basis_total: null, type: null },
]

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(rulesService.getDashboardSummary).mockResolvedValue({ total_balance: 1500, total_income_month: 0, total_expenses_month: 0, accounts_count: 1, transactions_count: 0, import_batches_count: 0, last_sync: '2026-08-31T12:00:00Z' })
  vi.mocked(rulesService.listAccounts).mockResolvedValue([account])
  vi.mocked(rulesService.listHoldings).mockResolvedValue(holdings)
})

describe('Portfolio Intelligence UI-04', () => {
  it('renders canonical portfolio context, KPIs, positions, and incomplete data state', async () => {
    render(<PortfolioIntelligencePage />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Portfolio workspace' })).toBeInTheDocument())
    expect(screen.getByText('$1,500.00')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'AAPL' })).toBeInTheDocument()
    expect(screen.getByText('Unresolved security')).toBeInTheDocument()
    expect(screen.getByText(/1 of 2 positions have incomplete market-value coverage/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /buy|sell|execute|trade|order|rebalance/i })).not.toBeInTheDocument()
  })

  it('filters positions and opens a security context drawer', async () => {
    render(<PortfolioIntelligencePage />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'AAPL' })).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Search holdings'), { target: { value: 'missing' } })
    expect(screen.getByText('No holdings match the current filters.')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Search holdings'), { target: { value: 'aapl' } })
    fireEvent.click(screen.getByRole('button', { name: 'AAPL' }))
    expect(screen.getByRole('dialog')).toHaveTextContent('Canonical position context')
    expect(screen.getByRole('link', { name: /View market intelligence/i })).toHaveAttribute('href', '/market-intelligence')
  })

  it('renders an honest backend error state', async () => {
    vi.mocked(rulesService.getDashboardSummary).mockRejectedValue(new Error('backend unavailable'))
    render(<PortfolioIntelligencePage />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Portfolio data unavailable' })).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})
