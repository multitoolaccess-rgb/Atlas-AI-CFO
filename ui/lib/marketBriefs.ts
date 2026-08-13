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

export type CoverageOmission = {
  symbol: string
  reason_code: MarketBriefReasonCode
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
    title: 'Coverage is below the safe threshold',
    message: 'Too little of the eligible portfolio has trustworthy market coverage.',
    recovery: 'Resolve omitted holdings before generating a complete portfolio brief.',
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
