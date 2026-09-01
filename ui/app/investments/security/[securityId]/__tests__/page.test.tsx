import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import SecurityResearchPage from '@/app/investments/security/[securityId]/page'
import { rulesService } from '@/lib/api'

vi.mock('@/components/layout/PageLayout', () => ({ default: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/components/ui/PageHeader', () => ({ default: ({ title, description }: { title: string; description?: string }) => <header><h1>{title}</h1><p>{description}</p></header> }))
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return { ...actual, rulesService: { listHoldings: vi.fn(), listAccounts: vi.fn(), getAnalystRatings: vi.fn() } }
})

const account = { id: 1, account_name: 'Brokerage', account_type: 'investment', current_balance: 1500, is_active: true, family_member_id: 1, last_sync: '2026-08-31T12:00:00Z' }
const holding = { id: 11, account_id: 1, symbol: 'AAPL', description: 'Apple', quantity: 5, current_value: 1000, last_price: 200, cost_basis_total: 800, type: 'Stock' }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(rulesService.listHoldings).mockResolvedValue([holding])
  vi.mocked(rulesService.listAccounts).mockResolvedValue([account])
  vi.mocked(rulesService.getAnalystRatings).mockResolvedValue({ symbol: 'AAPL', recommendation_trends: [{ period: '2026-08', strongBuy: 4, buy: 6, hold: 2, sell: 1, strongSell: 0 }], price_target: { targetMean: 240, targetMedian: 238, targetHigh: 280, targetLow: 190 } })
})

describe('Security Research UI-05', () => {
  it('renders canonical identity, price, portfolio context, and analyst data', async () => {
    render(<SecurityResearchPage params={{ securityId: 'sec:issuer-aapl' }} />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'AAPL' })).toBeInTheDocument())
    expect(screen.getByText('sec:issuer-aapl')).toBeInTheDocument()
    expect(screen.getByText('$200.00')).toBeInTheDocument()
    expect(screen.getByText('Brokerage')).toBeInTheDocument()
    expect(screen.getByText('2026-08')).toBeInTheDocument()
    expect(screen.getByText('$240.00')).toBeInTheDocument()
    expect(screen.getAllByText('Unavailable from the current canonical read model.')).toHaveLength(4)
  })

  it('shows an explicit unheld state without fabricating a position', async () => {
    vi.mocked(rulesService.listHoldings).mockResolvedValue([])
    render(<SecurityResearchPage params={{ securityId: 'sec:issuer-msft' }} />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'MSFT' })).toBeInTheDocument())
    expect(screen.getByText('Not currently held')).toBeInTheDocument()
    expect(screen.getByText('Not held')).toBeInTheDocument()
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
  })

  it('preserves partial research and backend error states', async () => {
    vi.mocked(rulesService.getAnalystRatings).mockRejectedValue(new Error('coverage unavailable'))
    render(<SecurityResearchPage params={{ securityId: 'sec:issuer-aapl' }} />)
    await waitFor(() => expect(screen.getByText(/Analyst coverage unavailable/i)).toBeInTheDocument())
    expect(screen.getByText(/Fundamental research/i)).toBeInTheDocument()
  })

  it('does not expose execution controls', async () => {
    render(<SecurityResearchPage params={{ securityId: 'sec:issuer-aapl' }} />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'AAPL' })).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /buy|sell|execute|trade|order|rebalance/i })).not.toBeInTheDocument()
  })
})
