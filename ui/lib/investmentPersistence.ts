import axios from 'axios'

export type InvestmentDecisionType = 'accept' | 'reject' | 'defer' | 'modify' | 'no_action'
export type InvestmentLifecycle = 'active' | 'superseded' | 'expired' | 'withdrawn'

export interface InvestmentDecisionRequest {
  decision_type: InvestmentDecisionType
  rationale?: string | null
}

export interface InvestmentDecision {
  decision_id: string
  recommendation_id: string
  decision_type: InvestmentDecisionType
  decision_timestamp: string
  rationale: string | null
  recommendation_hash: string
  created_at: string | null
}

export interface InvestmentEvidenceItem {
  evidence_id: string
  category: string
  subject_security_id?: string | null
  owner_id?: number | null
  reference: Record<string, unknown>
  excerpt?: string | null
  numeric_value?: string | null
}

export interface InvestmentEvidencePacket {
  schema_version: string
  packet_id: string
  packet_hash: string
  owner_id: number
  subject_security_id: string
  analysis_as_of: string
  items: InvestmentEvidenceItem[]
}

export interface InvestmentRecommendation {
  [key: string]: unknown
  recommendation_id: string
  owner_id: number
  security_id: string
  recommendation_type: 'BUY' | 'ADD' | 'HOLD' | 'REDUCE' | 'SELL' | 'WATCH'
  status: InvestmentLifecycle
  recommendation_hash: string
}

export interface InvestmentRecommendationResponse { schema_version: string; recommendation: InvestmentRecommendation }
export interface InvestmentRecommendationListResponse { schema_version: string; items: InvestmentRecommendation[] }
export interface InvestmentDecisionListResponse { schema_version: string; items: InvestmentDecision[] }

const baseURL = process.env.NEXT_PUBLIC_RULES_SERVICE_URL ?? 'http://localhost:8000'
const client = axios.create({ baseURL, withCredentials: true, headers: { 'Content-Type': 'application/json' } })

function storedToken(): string | null {
  return typeof window === 'undefined' ? null : window.localStorage.getItem('fc_session_token')
}

client.interceptors.request.use((config) => {
  const token = storedToken()
  if (token) config.headers.set('Authorization', `Bearer ${token}`)
  return config
})

export const investmentPersistence = {
  async listRecommendations(params?: { security_id?: string; lifecycle?: InvestmentLifecycle; limit?: number }): Promise<InvestmentRecommendationListResponse> {
    const response = await client.get<InvestmentRecommendationListResponse>('/api/v1/investments/recommendations', { params })
    return response.data
  },
  async getRecommendation(id: string): Promise<InvestmentRecommendationResponse> {
    const response = await client.get<InvestmentRecommendationResponse>(`/api/v1/investments/recommendations/${encodeURIComponent(id)}`)
    return response.data
  },
  async getEvidence(id: string): Promise<InvestmentEvidencePacket> {
    const response = await client.get<InvestmentEvidencePacket>(`/api/v1/investments/recommendations/${encodeURIComponent(id)}/evidence`)
    return response.data
  },
  async listDecisions(id: string): Promise<InvestmentDecisionListResponse> {
    const response = await client.get<InvestmentDecisionListResponse>(`/api/v1/investments/recommendations/${encodeURIComponent(id)}/decisions`)
    return response.data
  },
  async recordDecision(id: string, request: InvestmentDecisionRequest, recommendationHash: string, idempotencyKey: string): Promise<{ schema_version: string; decision: InvestmentDecision; replayed: boolean }> {
    const response = await client.post(`/api/v1/investments/recommendations/${encodeURIComponent(id)}/decisions`, request, { headers: { 'If-Match': recommendationHash, 'Idempotency-Key': idempotencyKey } })
    return response.data
  },
}
