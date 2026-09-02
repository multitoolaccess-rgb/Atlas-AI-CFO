import axios from 'axios'

export type DiscoveryUniverse = 'portfolio' | 'sp500'
export type DiscoveryStatus = 'candidate' | 'watch' | 'unavailable'
export type DiscoveryDataState = 'unknown' | 'missing' | 'stale' | 'estimated' | 'observed'

export interface DiscoveryCandidate {
  candidate_id: string
  universe: DiscoveryUniverse
  security: { security_id: string; symbol?: string | null; instrument_type: string; state: string }
  status: DiscoveryStatus
  reason: string
  source: string
  as_of: string
  freshness: DiscoveryDataState
  methodology_version: string
  metrics: Record<string, string | null>
  metric_states: Record<string, DiscoveryDataState>
  recommendation_id: string | null
}

export interface DiscoveryListResponse {
  schema_version: string
  universe: DiscoveryUniverse
  as_of: string
  methodology_version: string
  candidates: DiscoveryCandidate[]
  omitted_count: number
}

export interface DiscoveryComparisonResponse {
  schema_version: string
  candidate_ids: string[]
  metrics: Array<{ name: string; values: Record<string, string | null>; states: Record<string, DiscoveryDataState>; as_of: string; methodology_version: string }>
  comparable: boolean
  limitations: string[]
}

const client = axios.create({ baseURL: process.env.NEXT_PUBLIC_RULES_SERVICE_URL ?? 'http://localhost:8000', withCredentials: true })

export const investmentDiscovery = {
  async list(universe: DiscoveryUniverse, query?: string, limit = 50): Promise<DiscoveryListResponse> {
    return (await client.get<DiscoveryListResponse>('/api/v1/investments/discovery', { params: { universe, query, limit } })).data
  },
  async detail(universe: DiscoveryUniverse, id: string): Promise<DiscoveryCandidate> {
    return (await client.get<DiscoveryCandidate>(`/api/v1/investments/discovery/${encodeURIComponent(id)}`, { params: { universe } })).data
  },
  async compare(universe: DiscoveryUniverse, candidate_ids: string[], metric_names: string[]): Promise<DiscoveryComparisonResponse> {
    return (await client.post<DiscoveryComparisonResponse>('/api/v1/investments/discovery/compare', { candidate_ids, metric_names }, { params: { universe } })).data
  },
}
