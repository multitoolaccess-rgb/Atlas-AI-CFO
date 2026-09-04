import api from './api'

export type ScoutSelector =
  | { recommendation_id: string; committee_finding_id?: never; security_id?: never; discovery_candidate_id?: never }
  | { recommendation_id?: never; committee_finding_id: string; security_id?: never; discovery_candidate_id?: never }
  | { recommendation_id?: never; committee_finding_id?: never; security_id: string; discovery_candidate_id?: never }

export type ScoutSource = {
  schema_version: 'InvestmentScoutSource/v1'
  source_id: string
  source_type: 'company_news' | 'earnings' | 'sec_filing' | 'company_profile'
  provider: string
  source_url: string
  title: string
  publisher: string | null
  excerpt: string | null
  publication_at: string | null
  retrieved_at: string
  freshness: 'fresh' | 'stale' | 'unknown'
  source_hash: string
}

export type ScoutEvidence = {
  schema_version: 'InvestmentScoutEvidence/v1'
  evidence_id: string
  evidence_type: 'source_snapshot'
  source_id: string
  source_hash: string
  summary: string
  retrieved_at: string
  data_state: 'observed' | 'unavailable'
}

export type ScoutClaim = {
  schema_version: 'InvestmentScoutClaim/v1'
  claim_id: string
  kind: 'retrieved_fact' | 'derived_observation' | 'model_interpretation' | 'uncertainty'
  text: string
  source_ids: string[]
  evidence_ids: string[]
  data_state: 'observed' | 'derived' | 'uncertain' | 'unavailable'
}

export type ScoutResearchResult = {
  schema_version: 'InvestmentScoutResearchResult/v1'
  run_id: string
  question: string
  security: {
    schema_version: 'InvestmentScoutSecurity/v1'
    security: {
      schema_version: 'SecurityIdentity/v1'
      security_id: string
      state: string
      instrument_type: string
      symbol: string | null
      exchange: string | null
      currency: string | null
      issuer_id: string | null
      identifiers: Array<{ schema_version: 'SecurityIdentifier/v1'; namespace: string; value: string; valid_from: string | null; valid_to: string | null }>
      as_of: string
    }
    symbol: string
  }
  state: 'ready' | 'partial' | 'unavailable'
  requested_at: string
  as_of: string
  as_known_at: string
  sources: ScoutSource[]
  evidence: ScoutEvidence[]
  claims: ScoutClaim[]
  limitations: string[]
  warnings: string[]
  methodology_version: 'ui10-scout-provider-research/v1'
  calculation_version: 'ui10-source-normalization/v1'
  hypothetical: false
  predictive: false
  result_hash: string
}

export type ScoutRunSummary = {
  schema_version: 'InvestmentScoutRunSummary/v1'
  run_id: string
  security_id: string
  symbol: string
  state: 'ready' | 'partial' | 'unavailable'
  as_of: string
  source_count: number
  result_hash: string
}

export async function researchInvestmentSecurity(selector: ScoutSelector, question: string, maxSources = 12): Promise<ScoutResearchResult> {
  const response = await api.post('/api/v1/investments/scout/research', { ...selector, question, max_sources: maxSources })
  return response.data
}

export async function listInvestmentScoutRuns(limit = 20): Promise<ScoutRunSummary[]> {
  const response = await api.get('/api/v1/investments/scout/runs', { params: { limit } })
  return response.data
}

export async function getInvestmentScoutRun(runId: string): Promise<ScoutResearchResult> {
  const response = await api.get(`/api/v1/investments/scout/runs/${encodeURIComponent(runId)}`)
  return response.data
}
