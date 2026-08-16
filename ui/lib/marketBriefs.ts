import api from './api'

export type MarketBriefReasonCode =
  | 'provider_configuration_missing'
  | 'provider_transport_failure'
  | 'provider_authentication_failed'
  | 'provider_rate_limited'
  | 'unsupported_symbol'
  | 'live_quote_stale'
  | 'prior_close_accepted'
  | 'prior_close_too_old'
  | 'invalid_quote'
  | 'ambiguous_currency'
  | 'insufficient_portfolio_coverage'
  | 'no_market_addressable_holdings'
  | 'market_brief_generation_unavailable'

export type PriceBasis = 'live' | 'prior_close' | 'unusable' | 'unknown'
export type Freshness = 'fresh' | 'stale' | 'unknown'
export type CoverageBasis = 'value_weighted' | 'position_count'
export type EvidenceCategory = 'quote' | 'news' | 'earnings' | 'filings' | 'analyst'

export type CoverageOmission = {
  symbol: string
  evidence_category?: EvidenceCategory
  reason_code: MarketBriefReasonCode
  recovery?: string | null
}

/** Per-holding, per-evidence-category availability for a v2 brief. Records
 *  WHICH evidence category failed for WHICH holding so the UI can explain
 *  a partial brief precisely instead of collapsing it into one message. */
export type EvidenceAvailability = {
  symbol: string
  evidence_category: EvidenceCategory
  reason_code: MarketBriefReasonCode
  recovery?: string | null
}

export type MarketQuoteSnapshot = {
  symbol: string
  currency: string
  current_price: string
  previous_close?: string | null
}

export type CompanyProfile = {
  symbol: string
  cik?: string | null
  company_name?: string | null
  exchange?: string | null
  sector?: string | null
}

export type CompanyNewsItem = {
  symbol: string
  headline: string
  summary?: string | null
  publisher?: string | null
  source: Citation
}

export type EarningsEvent = {
  symbol: string
  event_date: string
  source: Citation
}

export type EarningsResult = {
  symbol: string
  actual?: string | null
  estimate?: string | null
  source: Citation
}

export type SecFilingEvent = {
  cik: string
  form: string
  accession_number: string
  filing_date: string
  source: Citation
}

export type AnalystRecommendation = {
  symbol: string
  period: string
  strong_buy: number
  buy: number
  hold: number
  sell: number
  strong_sell: number
}

export type PriceTarget = {
  symbol: string
  target_high?: string | null
  target_low?: string | null
  target_mean?: string | null
  target_median?: string | null
}

export type DividendEvent = {
  symbol: string
  ex_date?: string | null
  declared_date?: string | null
  record_date?: string | null
  payable_date?: string | null
  amount?: string | null
  source: Citation
}

/** Market Intelligence v2 ranked per-holding intelligence packet. */
export type HoldingEvidence = {
  symbol: string
  quote?: MarketQuoteSnapshot | null
  profile?: CompanyProfile | null
  news: CompanyNewsItem[]
  earnings_events: EarningsEvent[]
  earnings_results: EarningsResult[]
  filings: SecFilingEvent[]
  recommendations: AnalystRecommendation[]
  price_target?: PriceTarget | null
  dividends: DividendEvent[]
  materiality: 'high' | 'watch' | 'informational'
  materiality_reason?: string | null
}

export type MarketIndexQuote = {
  label: string
  symbol: string
  current_price: string
  previous_close?: string | null
  direction: 'up' | 'down' | 'flat' | 'unavailable'
  is_etf_proxy: boolean
  source: Citation
}

export type MarketNewsItem = {
  headline: string
  summary?: string | null
  publisher?: string | null
  source: Citation
}

/** Market Intelligence v2 zero-dollar market-pulse snapshot. */
export type MarketPulseSnapshot = {
  indices: MarketIndexQuote[]
  news: MarketNewsItem[]
  earnings_calendar: EarningsEvent[]
  scanner: MarketQuoteSnapshot[]
  scanned_symbol_count: number
  total_universe_size: number
  categories_unavailable: string[]
  generated_at: string
}

export type CoverageSummary = {
  eligible_holding_count: number
  covered_holding_count: number
  omitted_holding_count: number
  coverage_basis: CoverageBasis
  coverage_percentage: string | null
  minimum_required_percentage: string
  omitted_symbols: string[]
  omissions: CoverageOmission[]
}

export type ProviderReadiness = {
  provider: string
  status: 'ready' | 'degraded' | 'unavailable'
  reason_code?: MarketBriefReasonCode | null
}

export type BriefIndex = {
  brief_id: string
  generated_at: string
  report_window: string
  market_data_basis?: PriceBasis
  provider_status?: ProviderReadiness['status']
  coverage?: CoverageSummary | null
}

export type Citation = {
  provider: string
  source_url: string
  retrieved_at?: string
  published_at?: string | null
  freshness: Freshness
}

export type BriefClaim = {
  text: string
  citation: Citation
}

export type BriefSection = {
  name: string
  content: string[]
  citations: Citation[]
  claims?: BriefClaim[]
}

export type ActionToReview = {
  action: string
  why: string
  goal_linkage: string
  evidence: string[]
  expected_impact: string
  risks: string[]
  alternatives: string[]
  confidence: 'low' | 'medium' | 'high'
  approval_requirement: string
}

export type MarketBrief = {
  schema_version?: string
  calculation_version?: string
  sections: BriefSection[]
  warnings: string[]
  generated_at: string
  as_of?: string
  coverage?: CoverageSummary | null
  market_data_basis?: PriceBasis
  provider_readiness?: ProviderReadiness
  portfolio_daily_change?: string | null
  actions?: ActionToReview[]
  evidence_availability?: EvidenceAvailability[]
  holding_evidence?: HoldingEvidence[]
}

export type MarketBriefErrorState = {
  reasonCode: MarketBriefReasonCode
  title: string
  message: string
  recovery: string
  retryable: boolean
  /** Bounded list of symbols the provider could not address, from the server. */
  omittedSymbols?: string[]
}

const REASON_CODES = new Set<MarketBriefReasonCode>([
  'provider_configuration_missing',
  'provider_transport_failure',
  'provider_authentication_failed',
  'provider_rate_limited',
  'unsupported_symbol',
  'live_quote_stale',
  'prior_close_accepted',
  'prior_close_too_old',
  'invalid_quote',
  'ambiguous_currency',
  'insufficient_portfolio_coverage',
  'no_market_addressable_holdings',
  'market_brief_generation_unavailable',
])

function isReasonCode(value: unknown): value is MarketBriefReasonCode {
  return typeof value === 'string' && REASON_CODES.has(value as MarketBriefReasonCode)
}

const ERROR_COPY: Record<MarketBriefReasonCode, Omit<MarketBriefErrorState, 'reasonCode'>> = {
  provider_configuration_missing: {
    title: 'Provider setup needed',
    message: 'The approved market-data provider is not ready on the server.',
    recovery: 'Ask the local operator to configure the provider, then retry.',
    retryable: false,
  },
  provider_transport_failure: {
    title: 'Market data is unreachable',
    message: 'The provider could not be reached, so no market data was saved.',
    recovery: 'Check the provider connection and retry.',
    retryable: true,
  },
  provider_authentication_failed: {
    title: 'Provider authentication failed',
    message: 'The server-side provider credentials were rejected.',
    recovery: 'Ask the local operator to verify the provider configuration.',
    retryable: false,
  },
  provider_rate_limited: {
    title: 'Provider rate limit reached',
    message: 'The provider asked Atlas to slow down. No market data was saved.',
    recovery: 'Wait briefly, then retry.',
    retryable: true,
  },
  unsupported_symbol: {
    title: 'Some holdings are not addressable',
    message: 'One or more eligible holdings are not supported by the approved provider.',
    recovery: 'Review the coverage details and correct the holding symbols before retrying.',
    retryable: false,
  },
  live_quote_stale: {
    title: 'Live quotes are stale',
    message: 'Current-session quotes did not meet Atlas’s bounded freshness policy.',
    recovery: 'Retry during market hours or review a prior-close brief outside the session.',
    retryable: true,
  },
  prior_close_accepted: {
    title: 'Prior close accepted',
    message: 'This brief uses the latest bounded prior close rather than live pricing.',
    recovery: 'Review the as-of timestamp and source freshness below.',
    retryable: false,
  },
  prior_close_too_old: {
    title: 'Prior close is too old',
    message: 'The available prior close is outside Atlas’s bounded trading-session window.',
    recovery: 'Refresh provider data before generating another brief.',
    retryable: true,
  },
  invalid_quote: {
    title: 'Quote evidence is invalid',
    message: 'The provider returned incomplete or invalid quote evidence.',
    recovery: 'Ask the local operator to verify the provider response, then retry.',
    retryable: false,
  },
  ambiguous_currency: {
    title: 'Currency needs attention',
    message: 'Atlas could not establish one trustworthy portfolio currency.',
    recovery: 'Resolve the currency ambiguity before generating a brief.',
    retryable: false,
  },
  insufficient_portfolio_coverage: {
    title: 'Portfolio coverage is limited',
    message: 'The brief includes only holdings the provider can price; the rest are disclosed with reasons.',
    recovery: 'Review the disclosed omitted holdings and their reasons in the brief.',
    retryable: false,
  },
  no_market_addressable_holdings: {
    title: 'No priced holdings available',
    message: 'Atlas could not find a trustworthy market-addressable holding.',
    recovery: 'Add or correct an eligible holding, then retry.',
    retryable: false,
  },
  market_brief_generation_unavailable: {
    title: 'Brief generation is unavailable',
    message: 'Atlas could not safely generate a market brief.',
    recovery: 'Resolve the readiness issue and retry; no market data was saved.',
    retryable: true,
  },
}

export function classifyMarketBriefError(error: unknown): MarketBriefErrorState {
  const candidate = error as {
    response?: { status?: number; data?: { reason_code?: unknown; omitted_symbols?: unknown } }
  }
  const status = candidate?.response?.status
  const serverReason = candidate?.response?.data?.reason_code
  let reasonCode: MarketBriefReasonCode
  if (isReasonCode(serverReason)) {
    reasonCode = serverReason
  } else if (status === 401 || status === 403) {
    reasonCode = 'provider_authentication_failed'
  } else if (status === 404) {
    reasonCode = 'market_brief_generation_unavailable'
  } else if (!candidate?.response) {
    reasonCode = 'provider_transport_failure'
  } else {
    reasonCode = 'market_brief_generation_unavailable'
  }
  const rawSymbols = candidate?.response?.data?.omitted_symbols
  const omittedSymbols = Array.isArray(rawSymbols)
    ? rawSymbols
        .filter((item): item is string => typeof item === 'string' && item.length > 0)
        .slice(0, 50)
    : undefined
  return omittedSymbols && omittedSymbols.length > 0
    ? { reasonCode, ...ERROR_COPY[reasonCode], omittedSymbols }
    : { reasonCode, ...ERROR_COPY[reasonCode] }
}

export async function listMarketBriefs(): Promise<BriefIndex[]> {
  return (await api.get<{ briefs: BriefIndex[] }>('/api/v1/market-briefs')).data.briefs
}

export async function getMarketBrief(id: string): Promise<MarketBrief> {
  return (await api.get<{ brief: MarketBrief }>(`/api/v1/market-briefs/${encodeURIComponent(id)}`)).data.brief
}

/** Sends only the bounded report-window control; financial facts remain server-owned. */
export async function generateMarketBrief(): Promise<{ brief_id: string; replayed: boolean; brief: MarketBrief }> {
  return (await api.post<{ brief_id: string; replayed: boolean; brief: MarketBrief }>('/api/v1/market-briefs/generate', { report_window: 'latest' })).data
}

/** Server-owned, bounded, zero-dollar market pulse. Client sends no holdings. */
export async function fetchMarketPulse(): Promise<MarketPulseSnapshot> {
  return (await api.get<MarketPulseSnapshot>('/api/v1/market-briefs/pulse')).data
}
