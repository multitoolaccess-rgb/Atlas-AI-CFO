import api from './api'

export type InvestmentAssistantSelector = {
  recommendation_id?: string | null
  committee_finding_id?: string | null
  discovery_candidate_id?: string | null
  security_id?: string | null
}

export type InvestmentAssistantResponse = {
  schema_version: 'InvestmentAssistantResponse/v1'
  response_id: string
  context_id: string
  status: 'ok' | 'offline' | 'refused' | 'error'
  sections: Array<{ kind: 'fact' | 'calculation' | 'interpretation' | 'assumption' | 'limitation' | 'refusal'; text: string; citations: Array<{ citation_id: string; source_hash: string; source_type: string; as_of?: string | null }> }>
  limitations: string[]
}

export type InvestmentAssistantContext = {
  schema_version: 'InvestmentAssistantContext/v1'
  context_id: string
  owner_id: number
  state: 'ready' | 'partial' | 'unavailable'
  resolved_at: string
  context_as_of: string | null
  source_hashes: string[]
  recommendation: Record<string, unknown> | null
  committee: Record<string, unknown> | null
  evidence: Array<Record<string, unknown>>
  limitations: string[]
}

export async function askInvestmentScout(
  selector: InvestmentAssistantSelector,
  question: string,
  maxEvidence = 12,
): Promise<InvestmentAssistantResponse> {
  const response = await api.post('/api/v1/investments/assistant/query', {
    selector,
    question,
    max_evidence: maxEvidence,
  })
  return response.data
}

export async function resolveInvestmentAssistantContext(
  selector: InvestmentAssistantSelector,
  maxEvidence = 12,
): Promise<InvestmentAssistantContext> {
  const response = await api.post('/api/v1/investments/assistant/context', {
    selector,
    max_evidence: maxEvidence,
  })
  return response.data
}
