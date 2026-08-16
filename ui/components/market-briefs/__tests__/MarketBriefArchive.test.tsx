import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { useRouter, useSearchParams } from 'next/navigation'
import MarketIntelligenceCenter from '../MarketIntelligenceCenter'
import { fetchMarketPulse, generateMarketBrief, getMarketBrief, listMarketBriefs } from '@/lib/marketBriefs'

vi.mock('@/lib/marketBriefs', () => ({
  listMarketBriefs: vi.fn().mockResolvedValue([]),
  getMarketBrief: vi.fn(),
  generateMarketBrief: vi.fn(),
  fetchMarketPulse: vi.fn(),
  classifyMarketBriefError: vi.fn((error: { response?: { data?: { reason_code?: string, omitted_symbols?: string[] } } }) => {
    const reason = error?.response?.data?.reason_code
    if (reason === 'provider_rate_limited') {
      return { reasonCode: reason, title: 'Provider rate limit reached', message: 'The provider asked Atlas to slow down.', recovery: 'Wait briefly, then retry.', retryable: true }
    }
    if (reason === 'unsupported_symbol') {
      return { reasonCode: reason, title: 'Some holdings are not addressable', message: 'One or more eligible holdings are not supported by the approved provider.', recovery: 'Review the coverage details and correct the holding symbols before retrying.', retryable: false, omittedSymbols: error?.response?.data?.omitted_symbols ?? [] }
    }
    if (reason === 'provider_configuration_missing') {
      return { reasonCode: reason, title: 'Provider setup needed', message: 'The approved market-data provider is not ready on the server.', recovery: 'Ask the local operator to configure the provider, then retry.', retryable: false }
    }
    if (reason === 'insufficient_portfolio_coverage') {
      return { reasonCode: reason, title: 'Portfolio coverage is limited', message: 'The brief includes only holdings the provider can price; the rest are disclosed with reasons.', recovery: 'Review the disclosed omitted holdings and their reasons in the brief.', retryable: false, omittedSymbols: error?.response?.data?.omitted_symbols ?? [] }
    }
    if (!error?.response) {
      return { reasonCode: 'provider_transport_failure', title: 'Market data is unreachable', message: 'The provider could not be reached, so no market data was saved.', recovery: 'Check the provider connection and retry.', retryable: true }
    }
    return { reasonCode: 'provider_configuration_missing', title: 'Provider setup needed', message: 'The approved market-data provider is not ready on the server.', recovery: 'Ask the local operator to configure the provider, then retry.', retryable: false }
  }),
}))

afterEach(() => {
  vi.clearAllMocks()
  vi.mocked(useSearchParams).mockImplementation(() => new URLSearchParams() as any)
  vi.mocked(useRouter).mockImplementation(() => ({ replace: vi.fn(), push: vi.fn(), prefetch: vi.fn() }) as any)
})

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

const holdingEvidence = [{
  symbol: 'AAPL',
  quote: { symbol: 'AAPL', currency: 'USD', current_price: '110', previous_close: '100' },
  profile: { symbol: 'AAPL', company_name: 'Apple Inc.', sector: 'Technology' },
  news: [{ symbol: 'AAPL', headline: 'Apple announces new product line', publisher: 'Synthetic News', source: { provider: 'synthetic', source_url: 'https://source.test/apple', retrieved_at: '2026-08-11T12:00:00Z', freshness: 'fresh' as const } }],
  earnings_events: [{ symbol: 'AAPL', event_date: '2026-08-20T12:00:00Z', source: { provider: 'synthetic', source_url: 'https://source.test/earnings', retrieved_at: '2026-08-11T12:00:00Z', freshness: 'fresh' as const } }],
  earnings_results: [],
  filings: [{ cik: '0000320193', form: '8-K', accession_number: '0000320193-26-000001', filing_date: '2026-08-10T12:00:00Z', source: { provider: 'synthetic', source_url: 'https://source.test/filing', retrieved_at: '2026-08-11T12:00:00Z', freshness: 'fresh' as const } }],
  recommendations: [],
  price_target: null,
  dividends: [],
  materiality: 'high' as const,
  materiality_reason: 'Upcoming earnings plus material company news in the window.',
}]

const brief = {
  generated_at: '2026-08-11T12:00:00Z',
  as_of: '2026-08-11T12:00:00Z',
  market_data_basis: 'prior_close' as const,
  provider_readiness: { provider: 'market_data', status: 'ready' as const },
  portfolio_daily_change: '10',
  coverage,
  holding_evidence: holdingEvidence,
  sections: [
    { name: 'portfolio_changes', content: ['AAPL: 10'], citations: [{ provider: 'synthetic', source_url: 'https://source.test/quote', freshness: 'fresh' as const }] },
    { name: 'earnings', content: ['upcoming: AAPL earnings'], citations: [{ provider: 'synthetic', source_url: 'https://source.test/earnings', freshness: 'fresh' as const }] },
    { name: 'data_quality', content: ['SEC filings omitted'], citations: [] },
  ],
  warnings: ['SEC filings omitted'],
  actions: [{ action: 'Review AAPL', why: 'Review only', goal_linkage: 'No goal linkage inferred', evidence: ['AAPL'], expected_impact: 'No execution', risks: ['Incomplete'], alternatives: ['Do nothing'], confidence: 'low' as const, approval_requirement: 'explicit_user_approval_required' }],
}

const pulse = {
  indices: [{ label: 'S&P 500 (SPY proxy)', symbol: 'SPY', current_price: '450', previous_close: '448', direction: 'up' as const, is_etf_proxy: true, source: { provider: 'synthetic', source_url: 'https://source.test/spy', retrieved_at: '2026-08-11T12:00:00Z', freshness: 'fresh' as const } }],
  news: [{ headline: 'Markets rally on earnings', publisher: 'Synthetic News', source: { provider: 'synthetic', source_url: 'https://source.test/market-news', retrieved_at: '2026-08-11T12:00:00Z', freshness: 'fresh' as const } }],
  earnings_calendar: [{ symbol: 'MSFT', event_date: '2026-08-15T12:00:00Z', source: { provider: 'synthetic', source_url: 'https://source.test/calendar', retrieved_at: '2026-08-11T12:00:00Z', freshness: 'fresh' as const } }],
  scanner: [{ symbol: 'AAPL', currency: 'USD', current_price: '110', previous_close: '100' }, { symbol: 'MSFT', currency: 'USD', current_price: '330', previous_close: '320' }],
  scanned_symbol_count: 2,
  total_universe_size: 502,
  categories_unavailable: [],
  generated_at: '2026-08-11T12:00:00Z',
}

function tab(name: string | RegExp) {
  return screen.getByRole('tab', { name })
}

test('renders an accessible command center with the portfolio empty state and generate action', async () => {
  render(<MarketIntelligenceCenter />)
  expect(screen.getByRole('heading', { name: /market intelligence/i })).toBeInTheDocument()
  expect(await screen.findByText(/generate your first portfolio brief/i)).toBeInTheDocument()
  expect(screen.getByText('Provider not checked')).toBeInTheDocument()
  expect(screen.getByText('Generate a brief to verify current portfolio coverage and market-data availability.')).toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: /generate brief/i }).length).toBeGreaterThanOrEqual(1)
  for (const label of ['My Portfolio', 'Market Pulse', 'Earnings & Events', 'S&P 500 Scanner', 'Archive']) {
    expect(screen.getByRole('tab', { name: label })).toBeInTheDocument()
  }
})

test('announces the checking state and disables duplicate generation', async () => {
  let resolveGeneration!: (value: any) => void
  vi.mocked(generateMarketBrief).mockImplementation(() => new Promise(resolve => { resolveGeneration = resolve }))
  render(<MarketIntelligenceCenter />)
  const button = await screen.findByRole('button', { name: /^generate brief$/i })
  fireEvent.click(button)
  expect((await screen.findAllByText('Checking market data')).length).toBeGreaterThanOrEqual(1)
  expect(screen.getByRole('button', { name: /generating brief/i })).toBeDisabled()
  resolveGeneration({ brief_id: 'generated', replayed: false, brief })
  expect(await screen.findByText(/generated and added/i)).toBeInTheDocument()
})

test('generates a brief, shows the catalyst stream, and switches to My Portfolio', async () => {
  vi.mocked(generateMarketBrief).mockResolvedValue({ brief_id: 'generated', replayed: false, brief })
  render(<MarketIntelligenceCenter />)
  fireEvent.click(await screen.findByRole('button', { name: /^generate brief$/i }))
  expect(await screen.findByText(/generated and added/i)).toBeInTheDocument()
  expect(screen.getByText('Provider ready')).toBeInTheDocument()
  expect(screen.getByText(/provider readiness was verified by the server/i)).toBeInTheDocument()
  expect(screen.getAllByText('100%').length).toBeGreaterThanOrEqual(1)
  expect(screen.getAllByText(/upcoming: AAPL earnings/i).length).toBeGreaterThanOrEqual(1)
  const sourceLinks = screen.getAllByRole('link', { name: /synthetic source/i })
  expect(sourceLinks.some(link => link.getAttribute('href') === 'https://source.test/quote')).toBe(true)
  expect(sourceLinks.some(link => link.getAttribute('href') === 'https://source.test/apple')).toBe(true)
  expect(screen.getByText(/review AAPL/i)).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: /what could move your holdings/i })).toBeInTheDocument()
  expect(screen.getByText('High impact')).toBeInTheDocument()
  expect(screen.getAllByText('AAPL').length).toBeGreaterThanOrEqual(1)
  expect(generateMarketBrief).toHaveBeenCalledOnce()
})

test('shows coverage limited for a degraded server brief', async () => {
  vi.mocked(generateMarketBrief).mockResolvedValue({
    brief_id: 'degraded',
    replayed: false,
    brief: { ...brief, provider_readiness: { provider: 'market_data', status: 'degraded' as const } },
  })
  render(<MarketIntelligenceCenter />)
  fireEvent.click(await screen.findByRole('button', { name: /^generate brief$/i }))
  expect(await screen.findByText('Coverage limited')).toBeInTheDocument()
  expect(screen.getByText(/limited portfolio coverage for this brief/i)).toBeInTheDocument()
})

test('explains a fail-closed provider configuration response', async () => {
  vi.mocked(generateMarketBrief).mockRejectedValue({ response: { status: 503, data: { reason_code: 'provider_configuration_missing' } } })
  render(<MarketIntelligenceCenter />)
  fireEvent.click(await screen.findByRole('button', { name: /^generate brief$/i }))
  expect((await screen.findAllByText(/approved market-data provider is not ready/i)).length).toBeGreaterThanOrEqual(1)
  expect(screen.getByText('Provider unavailable')).toBeInTheDocument()
  expect(screen.getByText(/ask the local operator to configure/i)).toBeInTheDocument()
  expect(screen.queryByText(/raw_provider_error|api key|secret/i)).not.toBeInTheDocument()
})

test('renders a distinct rate-limit recovery state', async () => {
  vi.mocked(generateMarketBrief).mockRejectedValue({ response: { status: 503, data: { reason_code: 'provider_rate_limited' } } })
  render(<MarketIntelligenceCenter />)
  fireEvent.click(await screen.findByRole('button', { name: /^generate brief$/i }))
  expect((await screen.findAllByText(/provider asked Atlas to slow down/i)).length).toBeGreaterThanOrEqual(1)
  expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
})

test('lists the actual omitted symbols instead of a dead review instruction', async () => {
  vi.mocked(generateMarketBrief).mockRejectedValue({
    response: {
      status: 503,
      data: {
        reason_code: 'unsupported_symbol',
        omitted_symbols: ['NON40OJJ2', 'NON40OXLT'],
      },
    },
  })
  render(<MarketIntelligenceCenter />)
  fireEvent.click(await screen.findByRole('button', { name: /^generate brief$/i }))
  const panel = await screen.findByTestId('omitted-symbols')
  expect(panel).toHaveTextContent('NON40OJJ2')
  expect(panel).toHaveTextContent('NON40OXLT')
  // Unsupported symbols are a portfolio/data limitation, not a provider
  // outage — the badge must say "Coverage limited", never "Provider unavailable".
  expect(screen.getByText('Coverage limited')).toBeInTheDocument()
  expect(screen.queryByText('Provider unavailable')).not.toBeInTheDocument()
})

test('labels insufficient portfolio coverage as Coverage limited, not a provider outage', async () => {
  vi.mocked(generateMarketBrief).mockRejectedValue({
    response: {
      status: 503,
      data: {
        reason_code: 'insufficient_portfolio_coverage',
        omitted_symbols: ['FXAIX', 'FNILX'],
      },
    },
  })
  render(<MarketIntelligenceCenter />)
  fireEvent.click(await screen.findByRole('button', { name: /^generate brief$/i }))
  expect(await screen.findByText(/Portfolio coverage is limited/i)).toBeInTheDocument()
  expect(screen.getByText('Coverage limited')).toBeInTheDocument()
  expect(screen.queryByText('Provider unavailable')).not.toBeInTheDocument()
})

test('clears a generation error when an archived brief is opened', async () => {
  vi.mocked(listMarketBriefs).mockResolvedValue([
    { brief_id: 'archived', report_window: 'latest', generated_at: '2026-08-11T12:00:00Z' },
  ])
  vi.mocked(generateMarketBrief).mockRejectedValue({ response: { status: 503, data: { reason_code: 'provider_configuration_missing' } } })
  vi.mocked(getMarketBrief).mockResolvedValue({ ...brief, generated_at: 'archived' })
  render(<MarketIntelligenceCenter />)
  fireEvent.click(await screen.findByRole('button', { name: /^generate brief$/i }))
  expect(await screen.findByText('Provider unavailable')).toBeInTheDocument()
  fireEvent.click(tab(/archive/i))
  fireEvent.click(await screen.findByRole('button', { name: /brief for latest/i }))
  expect(await screen.findByText(/loaded market brief from archived/i)).toBeInTheDocument()
  expect(screen.getByText('Provider ready')).toBeInTheDocument()
  expect(screen.queryByText('Provider unavailable')).not.toBeInTheDocument()
  expect(screen.getByRole('tab', { name: /archive/i })).toHaveAttribute('aria-selected', 'true')
})

test('clears a prior brief when a later selection fails', async () => {
  vi.mocked(listMarketBriefs).mockResolvedValue([
    { brief_id: 'one', report_window: 'one', generated_at: '2026-08-11T12:00:00Z' },
    { brief_id: 'two', report_window: 'two', generated_at: '2026-08-11T12:00:00Z' },
  ])
  vi.mocked(getMarketBrief).mockResolvedValueOnce({ generated_at: 'one', sections: [], warnings: [] }).mockRejectedValueOnce(new Error('nope'))
  render(<MarketIntelligenceCenter />)
  fireEvent.click(tab(/archive/i))
  fireEvent.click(await screen.findByRole('button', { name: /brief for one/i }))
  expect(await screen.findByText(/loaded market brief from one/i)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /brief for two/i }))
  expect(screen.queryByText(/loaded market brief from one/i)).not.toBeInTheDocument()
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
  render(<MarketIntelligenceCenter />)
  fireEvent.click(tab(/archive/i))
  fireEvent.click(await screen.findByRole('button', { name: /brief for one/i }))
  await waitFor(() => expect(firstResolve).toBeTypeOf('function'))
  fireEvent.click(screen.getByRole('button', { name: /brief for two/i }))
  await waitFor(() => expect(secondResolve).toBeTypeOf('function'))
  secondResolve({ generated_at: 'two', sections: [], warnings: [] })
  expect(await screen.findByText(/loaded market brief from two/i)).toBeInTheDocument()
  firstResolve({ generated_at: 'one', sections: [], warnings: [] })
  await waitFor(() => expect(screen.queryByText(/loaded market brief from one/i)).not.toBeInTheDocument())
})

test('renders Market Pulse with truthful ETF proxies and market headlines', async () => {
  vi.mocked(fetchMarketPulse).mockResolvedValue(pulse as any)
  render(<MarketIntelligenceCenter />)
  fireEvent.click(await screen.findByRole('tab', { name: /market pulse/i }))
  expect(await screen.findByRole('heading', { name: /market pulse/i })).toBeInTheDocument()
  expect(screen.getByText(/S&P 500 \(SPY proxy\)/i)).toBeInTheDocument()
  expect(screen.getAllByText(/ETF proxies/i).length).toBeGreaterThanOrEqual(1)
  expect(screen.getByText(/markets rally on earnings/i)).toBeInTheDocument()
  expect(fetchMarketPulse).toHaveBeenCalled()
})

test('Market Pulse surfaces unavailable categories without fabricating data', async () => {
  vi.mocked(fetchMarketPulse).mockResolvedValue({ ...pulse, indices: [], news: [], scanner: [], categories_unavailable: ['indices', 'market_news', 'scanner'] } as any)
  render(<MarketIntelligenceCenter />)
  fireEvent.click(await screen.findByRole('tab', { name: /market pulse/i }))
  expect(await screen.findByText(/some market categories are unavailable/i)).toBeInTheDocument()
  expect(screen.getByText(/Index direction, Market-wide headlines, S&P 500 scanner/i)).toBeInTheDocument()
  expect(screen.getByText(/never fabricates missing market data/i)).toBeInTheDocument()
})

test('S&P 500 Scanner filters the bounded sample by symbol', async () => {
  vi.mocked(fetchMarketPulse).mockResolvedValue(pulse as any)
  render(<MarketIntelligenceCenter />)
  fireEvent.click(await screen.findByRole('tab', { name: /S&P 500 Scanner/i }))
  const search = await screen.findByLabelText(/search scanned symbols/i)
  expect(screen.getByText(/2 of 502 universe symbols/i)).toBeInTheDocument()
  fireEvent.change(search, { target: { value: 'MSFT' } })
  expect(screen.getByText('MSFT')).toBeInTheDocument()
  expect(screen.queryByText('AAPL')).not.toBeInTheDocument()
})

test('Earnings & Events combines portfolio-linked and market calendar evidence', async () => {
  vi.mocked(generateMarketBrief).mockResolvedValue({ brief_id: 'generated', replayed: false, brief })
  vi.mocked(fetchMarketPulse).mockResolvedValue(pulse as any)
  render(<MarketIntelligenceCenter />)
  fireEvent.click(await screen.findByRole('button', { name: /^generate brief$/i }))
  await screen.findByText(/generated and added/i)
  fireEvent.click(screen.getByRole('tab', { name: /Earnings & Events/i }))
  expect(await screen.findByRole('heading', { name: /Earnings & Events/i })).toBeInTheDocument()
  expect(screen.getByText(/portfolio-linked earnings/i)).toBeInTheDocument()
  expect(screen.getByText('MSFT')).toBeInTheDocument()
})

test('opens the bookmarked tab and preserves query state when selecting another view', async () => {
  vi.mocked(useSearchParams).mockImplementation(() => new URLSearchParams('view=pulse&brief=archived') as any)
  const replace = vi.fn()
  vi.mocked(useRouter).mockImplementation(() => ({ replace, push: vi.fn(), prefetch: vi.fn() }) as any)
  vi.mocked(fetchMarketPulse).mockResolvedValue(pulse as any)
  render(<MarketIntelligenceCenter />)
  expect(screen.getByRole('tab', { name: /market pulse/i })).toHaveAttribute('aria-selected', 'true')
  fireEvent.click(screen.getByRole('tab', { name: /archive/i }))
  expect(replace).toHaveBeenCalledWith('?view=archive&brief=archived', { scroll: false })
})

test('keyboard arrow navigation moves between tabs', async () => {
  render(<MarketIntelligenceCenter />)
  const portfolioTab = await screen.findByRole('tab', { name: /my portfolio/i })
  portfolioTab.focus()
  fireEvent.keyDown(portfolioTab, { key: 'ArrowRight' })
  expect(screen.getByRole('tab', { name: /market pulse/i })).toHaveAttribute('aria-selected', 'true')
  const pulseTab = screen.getByRole('tab', { name: /market pulse/i })
  fireEvent.keyDown(pulseTab, { key: 'ArrowLeft' })
  expect(portfolioTab).toHaveAttribute('aria-selected', 'true')
  fireEvent.keyDown(portfolioTab, { key: 'End' })
  expect(screen.getByRole('tab', { name: /archive/i })).toHaveAttribute('aria-selected', 'true')
  fireEvent.keyDown(screen.getByRole('tab', { name: /archive/i }), { key: 'Home' })
  expect(portfolioTab).toHaveAttribute('aria-selected', 'true')
})

test('archive empty state explains where briefs are generated', async () => {
  vi.mocked(listMarketBriefs).mockResolvedValue([])
  render(<MarketIntelligenceCenter />)
  fireEvent.click(await screen.findByRole('tab', { name: /archive/i }))
  expect(await screen.findByText(/no saved briefs yet/i)).toBeInTheDocument()
  expect(screen.getByText(/generate a brief on the My Portfolio tab/i)).toBeInTheDocument()
})

test('pulse refresh refetches the server-owned snapshot', async () => {
  vi.mocked(fetchMarketPulse).mockResolvedValue(pulse as any)
  render(<MarketIntelligenceCenter />)
  fireEvent.click(await screen.findByRole('tab', { name: /market pulse/i }))
  await screen.findByText(/markets rally on earnings/i)
  fireEvent.click(screen.getByRole('button', { name: /refresh pulse/i }))
  expect(fetchMarketPulse).toHaveBeenCalledTimes(2)
  await screen.findByText(/markets rally on earnings/i)
})
