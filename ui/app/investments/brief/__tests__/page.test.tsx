import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import DailyInvestmentBriefPage from '@/app/investments/brief/page'
import { generateMarketBrief, type MarketBrief } from '@/lib/marketBriefs'

vi.mock('@/components/layout/PageLayout', () => ({ default: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/components/ui/PageHeader', () => ({ default: ({ title, description }: { title: string; description?: string }) => <header><h1>{title}</h1><p>{description}</p></header> }))
vi.mock('@/lib/marketBriefs', async () => {
  const actual = await vi.importActual<typeof import('@/lib/marketBriefs')>('@/lib/marketBriefs')
  return { ...actual, generateMarketBrief: vi.fn() }
})

const brief = {
  schema_version: 'MarketBrief/v2',
  sections: [
    { name: 'Portfolio changes', content: ['Portfolio movement is partial.'], citations: [{ provider: 'Atlas fixture', source_url: 'https://example.test/portfolio', freshness: 'fresh' }] },
    { name: 'Conflicts', content: ['Technical evidence conflicts with the committee view.'], citations: [{ provider: 'Atlas fixture', source_url: 'https://example.test/conflict', freshness: 'stale' }] },
  ],
  warnings: ['One holding has stale evidence.'],
  generated_at: '2026-08-31T12:05:00Z',
  as_of: '2026-08-31T12:00:00Z',
  coverage: { eligible_holding_count: 3, covered_holding_count: 2, omitted_holding_count: 1, coverage_basis: 'position_count', coverage_percentage: '66.7', minimum_required_percentage: '80', omitted_symbols: ['UNKNOWN'], omissions: [] },
  provider_readiness: { provider: 'approved', status: 'degraded' },
  actions: [{ action: 'ADD', why: 'Committee evidence supports review.', goal_linkage: 'portfolio', evidence: ['evidence-1'], expected_impact: 'Unknown', risks: ['concentration'], alternatives: ['WATCH'], confidence: 'medium', approval_requirement: 'Human review' }],
} as MarketBrief

beforeEach(() => { vi.clearAllMocks() })

describe('Daily Investment Brief UI-03', () => {
  it('renders loading then structured brief context and warnings', async () => {
    vi.mocked(generateMarketBrief).mockResolvedValue({ brief_id: 'brief-1', replayed: false, brief })
    render(<DailyInvestmentBriefPage />)
    expect(screen.getByTestId('brief-loading')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Daily Investment Brief' })).toBeInTheDocument())
    expect(screen.getByText('Portfolio movement is partial.')).toBeInTheDocument()
    expect(screen.getByText('One holding has stale evidence.')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('degraded')).toBeInTheDocument()
  })

  it('opens evidence details and filters human review actions', async () => {
    vi.mocked(generateMarketBrief).mockResolvedValue({ brief_id: 'brief-1', replayed: false, brief })
    render(<DailyInvestmentBriefPage />)
    await waitFor(() => expect(screen.getByText('Portfolio movement is partial.')).toBeInTheDocument())
    fireEvent.click(screen.getAllByRole('button', { name: 'Evidence' })[0])
    expect(screen.getByRole('dialog')).toHaveTextContent('Atlas fixture')
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    fireEvent.change(screen.getByLabelText('Filter review actions'), { target: { value: 'watch' } })
    expect(screen.getByText('No review items are available for this brief.')).toBeInTheDocument()
  })

  it('shows an honest unavailable state without creating action controls', async () => {
    vi.mocked(generateMarketBrief).mockRejectedValue({ response: { status: 404, data: {} } })
    render(<DailyInvestmentBriefPage />)
    await waitFor(() => expect(screen.getByTestId('brief-error')).toBeInTheDocument())
    expect(screen.getByText('Investment Brief unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /buy now|sell now|execute|place order|trade|rebalance/i })).not.toBeInTheDocument()
  })
})
