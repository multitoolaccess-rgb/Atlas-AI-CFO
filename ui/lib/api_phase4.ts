/** Typed client for the default-off Phase 4 decision-history API. */
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

export type DecisionHistoryErrorState = 'unavailable' | 'not_found' | 'conflict' | 'error'

export interface DecisionHistoryWriteBody {
  recommendation_id: string
  decision_journal_entry_id: string
  alternatives: readonly DecisionAlternative[]
  rationale: string
}

export interface DecisionHistoryWriteResponse {
  schema_version: 'atlas-decision-history-envelope/v1'
  history_id: string
  decision_action: DecisionAction
  recorded_at: string
  replayed: boolean
}

export interface DecisionHistorySnapshot {
  historyByGoal: Record<number, DecisionHistoryEntryWire[]>
  unavailableGoalIds: number[]
}

export async function getDecisionHistory(goalId: number): Promise<DecisionHistoryEnvelope> {
  const response = await rulesApi.get<DecisionHistoryEnvelope>(
    `/api/v1/goals/${goalId}/decision-history`,
  )
  return response.data
}

export async function getDecisionHistoryForGoals(goalIds: number[]): Promise<DecisionHistorySnapshot> {
  const results = await Promise.allSettled(goalIds.map(async (goalId) => [goalId, await getDecisionHistory(goalId)] as const))
  const historyByGoal: Record<number, DecisionHistoryEntryWire[]> = {}
  const unavailableGoalIds: number[] = []
  results.forEach((result, index) => {
    const goalId = goalIds[index]
    if (result.status === 'fulfilled') historyByGoal[goalId] = result.value[1].history
    else {
      historyByGoal[goalId] = []
      unavailableGoalIds.push(goalId)
    }
  })
  return { historyByGoal, unavailableGoalIds }
}

export async function recordDecisionHistory(
  goalId: number,
  body: DecisionHistoryWriteBody,
  idempotencyKey: string,
): Promise<DecisionHistoryWriteResponse> {
  const response = await rulesApi.post<DecisionHistoryWriteResponse>(
    `/api/v1/goals/${goalId}/decision-history`,
    body,
    { headers: { 'Idempotency-Key': idempotencyKey } },
  )
  return response.data
}

/** Do not expose server-provided messages: only stable public state branches. */
export function readDecisionHistoryError(error: unknown): DecisionHistoryErrorState {
  const axiosError = error as AxiosError<{ code?: unknown }>
  const code = axiosError?.isAxiosError ? axiosError.response?.data?.code : undefined
  if (code === 'decision_history_unavailable') return 'unavailable'
  if (code === 'decision_history_not_found') return 'not_found'
  if (code === 'decision_history_conflict') return 'conflict'
  return 'error'
}
