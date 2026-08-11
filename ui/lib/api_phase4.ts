/** Typed, read-only client for the default-off Phase 4 decision-history API. */
import type { AxiosError } from 'axios'
import rulesApi from '@/lib/api'

export type DecisionAction = 'accept' | 'reject' | 'defer'
export type DecisionAlternative = 'do_nothing' | 'accept' | 'reject' | 'defer'
export type OutcomeLifecycle = 'not_yet_measurable' | 'pending' | 'measured'

/** Wire-only identity fields are deliberately never displayed by the UI. */
export interface DecisionHistoryEntryWire {
  history_id: string
  recommendation_id: string
  decision_id: string
  decision_action: DecisionAction
  alternatives: DecisionAlternative[]
  rationale: string
  supersedes_history_id: string | null
  recorded_at: string
  audit: {
    event_action: 'recorded' | 'corrected' | 'evaluated'
    actor_scope: 'owner'
    policy_result: 'recorded'
    occurred_at: string
  } | null
  outcome_lifecycles: OutcomeLifecycle[]
}

export interface DecisionHistoryEnvelope {
  schema_version: 'atlas-decision-history-envelope/v1'
  history: DecisionHistoryEntryWire[]
}

export type DecisionHistoryErrorState = 'unavailable' | 'not_found' | 'error'

export async function getDecisionHistory(goalId: number): Promise<DecisionHistoryEnvelope> {
  const response = await rulesApi.get<DecisionHistoryEnvelope>(
    `/api/v1/goals/${goalId}/decision-history`,
  )
  return response.data
}

/** Do not expose server-provided messages: only stable public state branches. */
export function readDecisionHistoryError(error: unknown): DecisionHistoryErrorState {
  const axiosError = error as AxiosError<{ code?: unknown }>
  const code = axiosError?.isAxiosError ? axiosError.response?.data?.code : undefined
  if (code === 'decision_history_unavailable') return 'unavailable'
  if (code === 'decision_history_not_found') return 'not_found'
  return 'error'
}
