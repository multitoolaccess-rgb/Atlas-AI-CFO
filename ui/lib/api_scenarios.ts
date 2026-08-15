import type { AxiosError } from 'axios'
import api from '@/lib/api'

/** Decimal values remain strings from the API through the rendering boundary. */
export type ScenarioDecimal = string & { readonly __scenarioDecimal: unique symbol }

export type ScenarioLifecycle = 'active' | 'archived'
export type ScenarioBand = 'conservative' | 'base' | 'optimistic'

export interface ScenarioFreshness {
  data_as_of: string
  data_age_days: number
  max_data_age_days: number
}

export interface ScenarioBandComparison {
  baseline_ending_net_worth: ScenarioDecimal
  scenario_ending_net_worth: ScenarioDecimal
  difference_from_baseline: ScenarioDecimal
  baseline_target_reached: boolean | null
  scenario_target_reached: boolean | null
  baseline_target_gap: ScenarioDecimal | null
  scenario_target_gap: ScenarioDecimal | null
  target_amount: ScenarioDecimal | null
}

export interface ScenarioDeterministicBands {
  conservative: ScenarioBandComparison
  base: ScenarioBandComparison
  optimistic: ScenarioBandComparison
}

export interface ScenarioTimingImpact {
  contribution_start_date: string | null
  contribution_stop_date: string | null
  one_time_outflow_date: string | null
  one_time_outflow_boundary_index: number | null
}

export interface ScenarioAssumptions {
  annual_return_rates: Record<ScenarioBand, ScenarioDecimal>
  annual_inflation_rate: ScenarioDecimal
  contribution_timing: string
  period: 'monthly' | string
  rounding_rule: string
  probability: false
}

export interface ScenarioComparison {
  schema_version: 'atlas-scenario-comparison/v1'
  baseline_forecast_id: string
  baseline_version_number: number
  baseline_input_state_hash: string
  currency: string
  ending_net_worth: ScenarioDecimal
  difference_from_baseline: ScenarioDecimal
  target_amount: ScenarioDecimal | null
  target_gap: ScenarioDecimal | null
  target_reached: boolean | null
  contribution_difference: ScenarioDecimal
  one_time_liquidity_consumed: ScenarioDecimal
  deterministic_bands: ScenarioDeterministicBands
  timing_impact: ScenarioTimingImpact
  assumptions: ScenarioAssumptions
  source_freshness: ScenarioFreshness
  warnings: string[]
  limitations: string[]
}

export interface ScenarioBandResult {
  ending_balance: ScenarioDecimal
  total_contributions: ScenarioDecimal
  contribution_difference: ScenarioDecimal
  one_time_liquidity_consumed: ScenarioDecimal
  target_gap: ScenarioDecimal | null
  reaches_target: boolean | null
}

export interface ScenarioResultSnapshot {
  schema_version: 'atlas-scenario-lab/v1'
  model_version: string
  calculation_version: string
  currency: string
  scenario_input_hash: string
  canonical_inputs: ScenarioInput
  deterministic_bands: Record<ScenarioBand, ScenarioBandResult>
  source_freshness: ScenarioFreshness
  assumptions: ScenarioAssumptions
}

export interface ScenarioListItem {
  scenario_id: string
  goal_id: number
  version_number: number
  baseline_forecast_id: string
  baseline_version_number: number
  currency: string
  lifecycle_state: ScenarioLifecycle
  created_at: string | null
  ending_net_worth: ScenarioDecimal
  difference_from_baseline: ScenarioDecimal
  target_reached: boolean | null
}

export interface ScenarioListEnvelope {
  schema_version: 'atlas-scenario-list/v1'
  items: ScenarioListItem[]
  next_cursor: string | null
}

export interface ScenarioEnvelope {
  schema_version: 'atlas-scenario-envelope/v1'
  scenario_id: string
  version_id: string
  version_number: number
  goal_id: number
  baseline_forecast_id: string
  baseline_version_number: number
  baseline_input_state_hash: string
  scenario_input_hash: string
  model_version: string
  calculation_version: string
  currency: string
  lifecycle_state: ScenarioLifecycle
  created_at: string | null
  input: {
    schema_version: 'atlas-scenario-lab/v1'
    baseline_forecast_id: string
    baseline_version_number: number
    baseline_input_state_hash: string
    scenario: ScenarioInput
  }
  result: ScenarioResultSnapshot
  comparison: ScenarioComparison
  recommendation_reference: string | null
  etag: string
}

export interface ScenarioComparisonEnvelope {
  schema_version: 'atlas-scenario-comparison-envelope/v1'
  scenario_id: string
  version_number: number
  comparison: ScenarioComparison
}

export interface ScenarioComparisonSet {
  schema_version: 'atlas-scenario-comparison-set/v1'
  baseline_forecast_id: string
  baseline_version_number: number
  scenarios: Array<{
    scenario_id: string
    version_number: number
    comparison: ScenarioComparison
  }>
}

export interface ScenarioArchiveResponse {
  schema_version: 'atlas-scenario-archive/v1'
  scenario_id: string
  lifecycle_state: 'archived'
  archived_at: string | null
}

export type ScenarioInput = {
  scenario_id?: string
  monthly_contribution_delta?: string
  contribution_start_date?: string
  contribution_stop_date?: string
  one_time_outflow?: { date: string; amount: string }
}

export type ScenarioErrorCode =
  | 'scenario_generation_unavailable'
  | 'scenario_baseline_unavailable'
  | 'scenario_baseline_conflict'
  | 'scenario_not_found'
  | 'scenario_validation_error'
  | 'scenario_compare_validation_error'
  | 'scenario_comparison_incompatible'
  | 'idempotency_conflict'
  | 'scenario_conflict'
  | 'unknown'

export interface ScenarioErrorState {
  code: ScenarioErrorCode
  message: string
  recovery: string
}

const SAFE_ERROR_MESSAGE = 'Scenario Lab could not complete that request. No client-side result was calculated.'
const KNOWN_CODES: readonly ScenarioErrorCode[] = [
  'scenario_generation_unavailable',
  'scenario_baseline_unavailable',
  'scenario_baseline_conflict',
  'scenario_not_found',
  'scenario_validation_error',
  'scenario_compare_validation_error',
  'scenario_comparison_incompatible',
  'idempotency_conflict',
  'scenario_conflict',
]

function recoveryFor(code: ScenarioErrorCode): string {
  switch (code) {
    case 'scenario_generation_unavailable': return 'Scenario Lab is disabled or temporarily unavailable. Try again when the server is ready.'
    case 'scenario_baseline_unavailable': return 'Generate or refresh an approved baseline forecast before creating a scenario.'
    case 'scenario_baseline_conflict': return 'Refresh the goal and try again against the current baseline.'
    case 'scenario_comparison_incompatible': return 'Choose scenarios from the same goal, baseline, currency, and model versions.'
    case 'scenario_not_found': return 'Refresh the archive; the saved scenario may no longer be available to this owner.'
    case 'scenario_validation_error':
    case 'scenario_compare_validation_error': return 'Review the supported fields and dates, then try again.'
    case 'idempotency_conflict': return 'The previous request key was used for different input. Change the input and submit again.'
    case 'scenario_conflict': return 'Refresh the saved history and retry the same intent.'
    default: return 'Retry when the service is available. Atlas will not estimate a result locally.'
  }
}

export function readScenarioError(error: unknown): ScenarioErrorState {
  const axiosError = error as AxiosError<{ code?: unknown }>
  const rawCode = axiosError?.isAxiosError ? axiosError.response?.data?.code : undefined
  const code: ScenarioErrorCode = typeof rawCode === 'string' && KNOWN_CODES.includes(rawCode as ScenarioErrorCode)
    ? rawCode as ScenarioErrorCode
    : 'unknown'
  return { code, message: SAFE_ERROR_MESSAGE, recovery: recoveryFor(code) }
}

export async function listScenarios(goalId: number, includeArchived = true): Promise<ScenarioListEnvelope> {
  const response = await api.get<ScenarioListEnvelope>(`/api/v1/goals/${goalId}/scenarios`, { params: { include_archived: includeArchived } })
  return response.data
}

export async function generateScenario(goalId: number, input: ScenarioInput, idempotencyKey: string): Promise<ScenarioEnvelope> {
  const response = await api.post<ScenarioEnvelope>(`/api/v1/goals/${goalId}/scenarios`, input, { headers: { 'Idempotency-Key': idempotencyKey } })
  return response.data
}

export async function readScenario(scenarioId: string): Promise<ScenarioEnvelope> {
  const response = await api.get<ScenarioEnvelope>(`/api/v1/scenarios/${encodeURIComponent(scenarioId)}`)
  return response.data
}

export async function archiveScenario(scenarioId: string, idempotencyKey: string): Promise<ScenarioArchiveResponse> {
  const response = await api.post<ScenarioArchiveResponse>(`/api/v1/scenarios/${encodeURIComponent(scenarioId)}/archive`, null, { headers: { 'Idempotency-Key': idempotencyKey } })
  return response.data
}

export async function compareScenarios(scenarioIds: string[]): Promise<ScenarioComparisonSet> {
  const response = await api.post<ScenarioComparisonSet>('/api/v1/scenarios/compare', { scenario_ids: scenarioIds.slice(0, 3) })
  return response.data
}