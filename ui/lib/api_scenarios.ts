import type { AxiosError } from 'axios'
import api from '@/lib/api'

export interface ScenarioListItem {
  scenario_id: string
  goal_id: number
  version_number: number
  baseline_forecast_id: string
  baseline_version_number: number
  currency: string
  lifecycle_state: 'active' | 'archived'
  created_at: string | null
  ending_net_worth: string
  difference_from_baseline: string
  target_reached: boolean
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
  lifecycle_state: 'active' | 'archived'
  created_at: string | null
  input: Record<string, unknown>
  result: Record<string, unknown>
  comparison: Record<string, unknown>
  recommendation_reference: string | null
  etag: string
}

export interface ScenarioComparisonEnvelope {
  schema_version: 'atlas-scenario-comparison-envelope/v1'
  scenario_id: string
  version_number: number
  comparison: Record<string, unknown>
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
}

export function readScenarioError(error: unknown): ScenarioErrorState {
  const axiosError = error as AxiosError<{ code?: unknown; message?: unknown }>
  const code = axiosError?.isAxiosError ? axiosError.response?.data?.code : undefined
  const known: ScenarioErrorCode[] = [
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
  return {
    code: typeof code === 'string' && known.includes(code as ScenarioErrorCode) ? code as ScenarioErrorCode : 'unknown',
    message: 'Scenario Lab is unavailable or the requested scenario could not be loaded. No client-side result was calculated.',
  }
}

export type ScenarioInput = {
  scenario_id?: string
  monthly_contribution_delta?: string
  contribution_start_date?: string
  contribution_stop_date?: string
  one_time_outflow?: { date: string; amount: string }
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

export async function archiveScenario(scenarioId: string, idempotencyKey: string): Promise<{ scenario_id: string; lifecycle_state: 'archived'; archived_at: string | null }> {
  const response = await api.post(`/api/v1/scenarios/${encodeURIComponent(scenarioId)}/archive`, null, { headers: { 'Idempotency-Key': idempotencyKey } })
  return response.data
}

export async function compareScenarios(scenarioIds: string[]): Promise<{ schema_version: 'atlas-scenario-comparison-set/v1'; baseline_forecast_id: string; baseline_version_number: number; scenarios: Array<{ scenario_id: string; version_number: number; comparison: Record<string, unknown> }> }> {
  const response = await api.post('/api/v1/scenarios/compare', { scenario_ids: scenarioIds.slice(0, 3) })
  return response.data
}
