import api from './api'

export type RiskDataState = 'available' | 'unknown' | 'missing' | 'stale' | 'unsupported' | 'incompatible' | 'unavailable'
export type BaselineCapability = 'current_only' | 'historical_capable' | 'unavailable'
export type BaselineCompleteness = 'complete' | 'partial' | 'unknown'

export interface RiskMetric {
  name: string
  value: string | null
  unit: string
  currency: string | null
  state: RiskDataState
  limitation: string | null
}

export interface RiskPosition {
  position_id: number
  security: {
    security_id: string
    instrument_type: string
    symbol: string | null
    currency: string | null
    state: string
  }
  quantity: string | null
  market_value: string | null
  currency: string | null
  market_value_state: RiskDataState
  cost_basis: string | null
  cost_basis_state: RiskDataState
  as_of: string
  source_id: string
  source_hash: string
}

export interface PortfolioBaseline {
  schema_version: 'InvestmentPortfolioBaseline/v1'
  baseline_id: string
  as_of: string
  as_known_at: string | null
  capability: BaselineCapability
  positions: RiskPosition[]
  total_value: string | null
  currency: string | null
  metrics: RiskMetric[]
  completeness: BaselineCompleteness
  omissions: string[]
  freshness: RiskDataState
  methodology_version: string
  calculation_version: string
  source_ids: string[]
  source_hashes: string[]
  baseline_hash: string
}

export interface RiskScenario {
  schema_version: 'InvestmentRiskScenario/v1'
  scenario_id: string
  baseline_id: string
  baseline_hash: string
  inputs: {
    schema_version: 'InvestmentRiskScenarioRequest/v1'
    baseline_id: string | null
    position_id: number
    market_value_delta: string
  }
  metrics: RiskMetric[]
  source_ids: string[]
  source_hashes: string[]
  as_of: string
  as_known_at: string | null
  evaluated_at: string
  methodology_version: string
  calculation_version: string
  hypothetical: true
  predictive: false
  result_hash: string
  limitations: string[]
  warnings: string[]
}

export async function getInvestmentPortfolioBaseline(): Promise<PortfolioBaseline> {
  return (await api.get<PortfolioBaseline>('/api/v1/investments/portfolio-risk/baseline')).data
}

export async function previewInvestmentRiskScenario(input: {
  baseline_id: string
  position_id: number
  market_value_delta: string
}): Promise<RiskScenario> {
  return (await api.post<RiskScenario>('/api/v1/investments/portfolio-risk/scenarios/preview', input)).data
}
