import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import MarketBriefArchive from '../MarketBriefArchive'
import { generateMarketBrief, getMarketBrief, listMarketBriefs } from '@/lib/marketBriefs'

vi.mock('@/lib/marketBriefs', () => ({
  listMarketBriefs: vi.fn().mockResolvedValue([]),
  getMarketBrief: vi.fn(),
  generateMarketBrief: vi.fn(),
  classifyMarketBriefError: vi.fn((error: { response?: { data?: { reason_code?: string } } }) => {
    const reason = error?.response?.data?.reason_code
    if (reason === 'provider_rate_limited') {
      return { reasonCode: reason, title: 'Provider rate limit reached', message: 'The provider asked Atlas to slow down.', recovery: 'Wait briefly, then retry.', retryable: true }
    }
    if (!error?.response) {
      return { reasonCode: 'provider_transport_failure', title: 'Market data is unreachable', message: 'The provider could not be reached, so no market data was saved.', recovery: 'Check the provider connection and retry.', retryable: true }
    }
    return { reasonCode: 'provider_configuration_missing', title: 'Provider setup needed', message: 'The approved market-data provider is not ready on the server.', recovery: 'Ask the local operator to configure the provider, then retry.', retryable: false }
  }),
}))

afterEach(() => { vi.clearAllMocks() })

const coverage = {
  eligible_holding_count: 2,
  covered_holding_count: 2,
  omitted_holding_count: 0,
  coverage_basis: 'value_weighted' as const,
  coverage_percentage: '1',
  minimum_required_percentage: '0.8',
  omitted_symbols: [],
  omissions: [],
}

const brief = {
  generated_at: '2026-08-11T12:00:00Z',
  as_of: '2026-08-11T12:00:00Z',
  market_data_basis: 'prior_close' as const,
  provider_readiness: { provider: 'market_data', status: 'ready' as const },
  portfolio_daily_change: '10',
  coverage,
  sections: [
    { name: 'portfolio_changes', content: ['AAPL: 10'], citations: [{ provider: 'synthetic', source_url: 'https://source.test/quote', freshness: 'fresh' as const }] },
    { name: 'earnings', content: ['upcoming: AAPL earnings'], citations: [{ provider: 'synthetic', source_url: 'https://source.test/earnings', freshness: 'fresh' as const }] },
    { name: 'data_quality', content: ['SEC filings omitted'], citations: [] },
  ],
  warnings: ['SEC filings omitted'],
  actions: [{ action: 'Review AAPL', why: 'Review only', goal_linkage: 'No goal linkage inferred', evidence: ['AAPL'], expected_impact: 'No execution', risks: ['Incomplete'], alternatives: ['Do nothing'], confidence: 'low' as const, approval_requirement: 'explicit_user_approval_required' }],
}

test('renders an accessible empty archive and generate action', async () => {
  render(<MarketBriefArchive />)
  expect(screen.getByRole('heading', { name: /market intelligence briefs/i })).toBeInTheDocument()
  expect(await screen.findByText(/no saved briefs yet/i)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /generate brief/i })).toBeInTheDocument()
})

test('generates, selects, and archives a server-composed brief without client financial data', async () => {
  vi.mocked(generateMarketBrief).mockResolvedValue({ brief_id: 'generated', replayed: false, brief })
  render(<MarketBriefArchive />)
  fireEvent.click(await screen.findByRole('button', { name: /^generate brief$/i }))
  expect(await screen.findByText(/generated and added/i)).toBeInTheDocument()
  expect(screen.getAllByText(/prior close/i).length).toBeGreaterThan(0)
  expect(screen.getByText(/100% covered/i)).toBeInTheDocument()
  expect(screen.getByText(/upcoming: AAPL earnings/i)).toBeInTheDocument()
  expect(screen.getAllByRole('link', { name: /synthetic source/i })[0]).toHaveAttribute('href', 'https://source.test/quote')
  expect(screen.getByText(/review AAPL/i)).toBeInTheDocument()
  expect(generateMarketBrief).toHaveBeenCalledOnce()
})

test('explains a fail-closed provider configuration response', async () => {
  vi.mocked(generateMarketBrief).mockRejectedValue({ response: { status: 503, data: { reason_code: 'provider_configuration_missing' } } })
  render(<MarketBriefArchive />)
  fireEvent.click(await screen.findByRole('button', { name: /^generate brief$/i }))
  expect(await screen.findByText(/approved market-data provider is not ready/i)).toBeInTheDocument()
  expect(screen.getByText(/ask the local operator to configure/i)).toBeInTheDocument()
})

test('renders a distinct rate-limit recovery state', async () => {
  vi.mocked(generateMarketBrief).mockRejectedValue({ response: { status: 503, data: { reason_code: 'provider_rate_limited' } } })
  render(<MarketBriefArchive />)
  fireEvent.click(await screen.findByRole('button', { name: /^generate brief$/i }))
  expect(await screen.findByText(/provider asked Atlas to slow down/i)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
})

test('clears a prior brief when a later selection fails', async () => {
  vi.mocked(listMarketBriefs).mockResolvedValue([
    { brief_id: 'one', report_window: 'one', generated_at: '2026-08-11T12:00:00Z' },
    { brief_id: 'two', report_window: 'two', generated_at: '2026-08-11T12:00:00Z' },
  ])
  vi.mocked(getMarketBrief).mockResolvedValueOnce({ generated_at: 'one', sections: [], warnings: [] }).mockRejectedValueOnce(new Error('nope'))
  render(<MarketBriefArchive />)
  fireEvent.click(await screen.findByRole('button', { name: /brief for one/i }))
  expect(await screen.findByText(/as of one/i)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /brief for two/i }))
  expect(screen.queryByText(/as of one/i)).not.toBeInTheDocument()
  expect(await screen.findByText(/provider could not be reached/i)).toBeInTheDocument()
})

test('ignores a stale detail response after a newer selection', async () => {
  let firstResolve!: (value: any) => void
  let secondResolve!: (value: any) => void
  vi.mocked(listMarketBriefs).mockResolvedValue([
    { brief_id: 'one', report_window: 'one', generated_at: '2026-08-11T12:00:00Z' },
    { brief_id: 'two', report_window: 'two', generated_at: '2026-08-11T12:00:00Z' },
  ])
  vi.mocked(getMarketBrief).mockImplementationOnce(() => new Promise(resolve => { firstResolve = resolve })).mockImplementationOnce(() => new Promise(resolve => { secondResolve = resolve }))
  render(<MarketBriefArchive />)
  fireEvent.click(await screen.findByRole('button', { name: /brief for one/i }))
  await waitFor(() => expect(firstResolve).toBeTypeOf('function'))
  fireEvent.click(screen.getByRole('button', { name: /brief for two/i }))
  await waitFor(() => expect(secondResolve).toBeTypeOf('function'))
  secondResolve({ generated_at: 'two', sections: [], warnings: [] })
  expect(await screen.findByText(/as of two/i)).toBeInTheDocument()
  firstResolve({ generated_at: 'one', sections: [], warnings: [] })
  await waitFor(() => expect(screen.queryByText(/as of one/i)).not.toBeInTheDocument())
})
