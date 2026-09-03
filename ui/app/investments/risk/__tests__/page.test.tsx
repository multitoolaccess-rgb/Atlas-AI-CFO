import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import InvestmentRiskPage from '@/app/investments/risk/page'
import { getInvestmentPortfolioBaseline, previewInvestmentRiskScenario } from '@/lib/investmentRisk'

vi.mock('@/components/layout/PageLayout', () => ({ default: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/components/ui/PageHeader', () => ({ default: ({ title, description }: { title: string; description?: string }) => <header><h1>{title}</h1><p>{description}</p></header> }))
vi.mock('@/lib/investmentRisk', () => ({
  getInvestmentPortfolioBaseline: vi.fn(),
  previewInvestmentRiskScenario: vi.fn(),
}))

const baseline = {
  schema_version: 'InvestmentPortfolioBaseline/v1' as const,
  baseline_id: 'portfolio-baseline:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  as_of: '2026-09-01T00:00:00Z',
  as_known_at: '2026-09-01T00:00:00Z',
  capability: 'current_only' as const,
  positions: [{ position_id: 11, security: { security_id: 'sec:aapl', instrument_type: 'equity', symbol: 'AAPL', currency: null, state: 'resolved' }, quantity: '1', market_value: '100', currency: 'USD', market_value_state: 'available' as const, cost_basis: '80', cost_basis_state: 'available' as const, as_of: '2026-09-01T00:00:00Z', source_id: 'holding:11', source_hash: 'a'.repeat(64) }],
  total_value: '100',
  currency: 'USD',
  metrics: [
    { name: 'position_count', value: '1', unit: 'count', currency: null, state: 'available' as const, limitation: null },
    { name: 'total_value', value: '100', unit: 'currency', currency: 'USD', state: 'available' as const, limitation: null },
    { name: 'portfolio_volatility', value: null, unit: 'ratio', currency: null, state: 'unavailable' as const, limitation: 'portfolio volatility methodology is not approved for UI-11' },
  ],
  completeness: 'complete' as const,
  omissions: [],
  freshness: 'available' as const,
  methodology_version: 'ui11-current-portfolio/v1',
  calculation_version: 'ui11-baseline/v1',
  source_ids: ['holding:11'],
  source_hashes: ['a'.repeat(64)],
  baseline_hash: 'b'.repeat(64),
}

const scenario = {
  schema_version: 'InvestmentRiskScenario/v1' as const,
  scenario_id: 'investment-risk-scenario:' + 'c'.repeat(32),
  baseline_id: baseline.baseline_id,
  baseline_hash: baseline.baseline_hash,
  inputs: { schema_version: 'InvestmentRiskScenarioRequest/v1' as const, baseline_id: baseline.baseline_id, position_id: 11, market_value_delta: '25' },
  metrics: [{ name: 'hypothetical_total_value', value: '125', unit: 'currency', currency: 'USD', state: 'available' as const, limitation: null }],
  source_ids: baseline.source_ids,
  source_hashes: baseline.source_hashes,
  as_of: baseline.as_of,
  as_known_at: baseline.as_known_at,
  evaluated_at: '2026-09-01T00:01:00Z',
  methodology_version: 'ui11-exposure-preview/v1',
  calculation_version: 'ui11-scenario/v1',
  hypothetical: true as const,
  predictive: false as const,
  result_hash: 'd'.repeat(64),
  limitations: ['Current-only baseline'],
  warnings: ['Hypothetical analysis only'],
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(getInvestmentPortfolioBaseline).mockResolvedValue(baseline)
  vi.mocked(previewInvestmentRiskScenario).mockResolvedValue(scenario)
})

describe('UI-11 risk and scenario view', () => {
  it('renders current-only baseline, unavailable methods, and privacy-safe positions', async () => {
    render(<InvestmentRiskPage />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Current portfolio context' })).toBeInTheDocument())
    expect(screen.getByText('current only')).toBeInTheDocument()
    expect(screen.getByText('portfolio volatility methodology is not approved for UI-11')).toBeInTheDocument()
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.queryByText('Brokerage')).not.toBeInTheDocument()
    expect(screen.queryByText('account:1')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /buy|sell|execute|order|rebalance/i })).not.toBeInTheDocument()
  })

  it('submits a server-backed hypothetical preview with explicit safety labels', async () => {
    render(<InvestmentRiskPage />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Current portfolio context' })).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Value delta'), { target: { value: '25' } })
    fireEvent.click(screen.getByRole('button', { name: 'Preview change' }))
    await waitFor(() => expect(screen.getByText('Hypothetical analysis only · not a prediction')).toBeInTheDocument())
    expect(previewInvestmentRiskScenario).toHaveBeenCalledWith({ baseline_id: baseline.baseline_id, position_id: 11, market_value_delta: '25' })
    expect(screen.getByText('USD 125')).toBeInTheDocument()
  })

  it('renders a recoverable unavailable state', async () => {
    vi.mocked(getInvestmentPortfolioBaseline).mockRejectedValue(new Error('unavailable'))
    render(<InvestmentRiskPage />)
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Portfolio context unavailable' })).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})
