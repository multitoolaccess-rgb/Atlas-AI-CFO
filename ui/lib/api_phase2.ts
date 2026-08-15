/**
 * Phase 2 Slice 2 — UI API surface for the user-visible vertical slice.
 *
 * Per `docs/10-roadmap/PHASE2_VERTICAL_SLICE_PLAN.md` §3 (API-to-UI data
 * flow) and §4/§5 (recommendation + decision-journal contracts).
 *
 *  Three bounded typed methods wrap the merged Phase 1 + Phase 2 routes:
 *    1. ``getLatestForecastForGoal(goalId)``
 *       GET /api/v1/forecasts?goal_id={id}&limit=4
 *       GET /api/v1/forecasts/{forecast_id}/versions/{latest_version_number}
 *    2. ``getDerivedRecommendation(forecastId)``
 *       GET /api/v1/forecasts/{forecast_id}/recommendation
 *    3. ``postDecisionJournal(recommendationId, body, idempotencyKey)``
 *       POST /api/v1/recommendations/{recommendation_id}/decisions
 *
 *  Contract:
 *    - Money is canonical Decimal STRING end-to-end. Compile-time
 *      `string` typing + runtime ``JSON.parse(stringify(x))`` assertion
 *      ensures wire-format preservation. NO `Number()`/`parseFloat` on
 *      the API path.
 *    - Sanitized envelope codes propagate via AxiosError.response.data.code:
 *        * 503 ``forecast_read_api_unavailable`` (read gate off)
 *        * 404 ``forecast_not_found`` / ``recommendation_not_found``
 *        * 409 ``decision_version_conflict``
 *        * 422 ``forecast_validation_error``
 *    - No client-side override of server flags; the BE is the single
 *      source of truth.
 *    - `mintIdempotencyKey()` returns a bounded ASCII visible key
 *      (1..255 chars) suitable for the journal POST header.
 *
 *  The page wires ``code`` to UI state via ``readSanitizedError``.
 */
import type { AxiosError } from 'axios'
import api from '@/lib/api'

// Local alias matching the existing `api.ts` default export.
const rulesApi = api

// ============================================================
// Schema-version literals (canonical source for client-side drift
// detection — planning nit 2 of PHASE2_VERTICAL_SLICE_PLAN.md).
// ============================================================

export type SchemaVersionRecommendation = 'atlas-derived-recommendation/v1'
export type SchemaVersionDecision = 'atlas-decision-journal-entry/v1'

// ============================================================
// Bounded enum literals (mirror recommendation_schemas.py)
// ============================================================

export type RecommendationKind =
  | 'increase_contribution'
  | 'rebalance_allocation'
  | 'extend_horizon'
  | 'hold'

export type RecommendationConfidence = 'high' | 'medium' | 'low'

export type RecommendationRiskToken =
  | 'liquidity_reduction'
  | 'reversibility_required'
  | 'concentration'
  | 'downside_amplification'
  | 'stale_input'

export type DecisionAction = 'accept' | 'reject' | 'defer'

export type ForecastCurrency = 'USD'  // Phase 1 USD-only; new currencies require explicit authority

export type ScenarioName = 'conservative' | 'base' | 'optimistic'

export type LinkRel = 'self' | 'forecast' | 'decide' | 'goal' | 'recorded'

// ============================================================
// HATEOAS link entry (server-relative href under /api/v1/)
// ============================================================

export interface LinkEntryWire {
  rel: LinkRel
  href: string
}

// ============================================================
// Provenance fragment (NO money values, bounded identity only)
// ============================================================

export interface EvidenceReferenceWire {
  forecast_id: string  // lowercase canonical UUID (36 chars)
  model_version: string
  calculation_version: string
  input_state_hash: string  // lowercase SHA-256 hex (64 chars)
  data_as_of: string  // UTC RFC 3339 Z
}

// ============================================================
// Deterministic recommendation envelope (response, frozen)
// ============================================================

export interface DeterministicRecommendationWire {
  schema_version: SchemaVersionRecommendation
  recommendation_kind: RecommendationKind
  action_verb: string  // ≤ 64 chars; one bounded verb phrase
  why_now: string  // ≤ 280 chars
  linked_goal_id: number
  forecast_id: string
  forecast_etag: string
  evidence_references: EvidenceReferenceWire
  expected_impact_range: {
    min_delta_decimal: string  // canonical Decimal string
    max_delta_decimal: string  // canonical Decimal string
  }
  risks: RecommendationRiskToken[]
  confidence: RecommendationConfidence
  assumptions_reference: string  // 64-char SHA-256 hex
  expiration: string  // UTC RFC 3339 Z
  issuer: 'atlas-deterministic-rules/v1'
  links: LinkEntryWire[]
}

// ============================================================
// Decision journal submit body (strict; extra='forbid' on BE)
// ============================================================

export interface DecisionJournalSubmitBody {
  action: DecisionAction
  decision_etag: string  // bare uuid-d<n>
}

// ============================================================
// Decision journal entry envelope (response, frozen)
// ============================================================

export interface DecisionJournalEntryWire {
  schema_version: SchemaVersionDecision
  journal_entry_id: string  // lowercase canonical UUID
  recommendation_id: string
  action_taken: DecisionAction
  decided_at: string  // UTC RFC 3339 Z
  decision_etag: string  // bare uuid-d<n>
  links: LinkEntryWire[]
}

// ============================================================
// Forecast + forecast-version wire shapes (Phase 1 read endpoints)
// ============================================================

export interface ForecastWire {
  id: string  // lowercase canonical UUID
  goal_id: number
  user_id: number
  currency: ForecastCurrency
  kind: 'goal_projection'
  latest_version_number: number
  latest_version_id: string
  etag: string
  created_at: string
  updated_at: string | null
  links: LinkEntryWire[]
}

export interface ForecastScenarioWire {
  name: ScenarioName
  annual_return_rate: string  // canonical Decimal string
  ending_balance: string  // canonical Decimal string
}

export interface ForecastVersionWire {
  id: string
  forecast_id: string
  version_number: number
  ending_balance: string  // canonical Decimal string
  target_decision: {
    rounded_ending_balance: string
    rounded_target_amount: string
    target_status: boolean
    decision_etag: string
  }
  drivers: {
    data_age_days: number
    max_data_age_days: number
  }
  scenarios: ForecastScenarioWire[]
  assumption_snapshot: Record<string, string>
  provenance_snapshot: Record<string, string>
  data_as_of: string  // UTC RFC 3339 Z
  calculated_at: string  // UTC RFC 3339 Z
  model_version: string
  calculation_version: string
  input_state_hash: string  // 64-char SHA-256 hex
}

// ============================================================
// Result type for getLatestForecastForGoal
// ============================================================

export interface LatestForecastForGoalReady {
  state: 'ready'
  goal_id: number
  forecast: ForecastWire
  version: ForecastVersionWire
}

export interface LatestForecastForGoalMissing {
  state: 'no_forecast'
  goal_id: number
}

export type LatestForecastState =
  | LatestForecastForGoalReady
  | LatestForecastForGoalMissing

// ============================================================
// Sanitized envelope (codes are bounded; UI maps to state-tree)
// ============================================================

export type SanitizedErrorCode =
  | 'forecast_read_api_unavailable'
  | 'forecast_not_found'
  | 'recommendation_not_found'
  | 'decision_version_conflict'
  | 'forecast_validation_error'
  | 'unknown'

export interface SanitizedEnvelope {
  code: SanitizedErrorCode
  message: string
}

// ============================================================
// mintIdempotencyKey — bounded ASCII visible (1..255)
// ============================================================

export function mintIdempotencyKey(): string {
  if (
    typeof crypto !== 'undefined' &&
    typeof crypto.randomUUID === 'function'
  ) {
    return crypto.randomUUID()  // 36-char visible UUID v4
  }
  // Defensive fallback for non-browser / Node-without-randomUUID
  // environments (very old jsdom; not the production runtime).
  return `idem-${Date.now()}-${Math.floor(Math.random() * 1e9)}`
}

// ============================================================
// readSanitizedError — bounded envelope extraction (no leaks)
// ============================================================

export function readSanitizedError(err: unknown): SanitizedEnvelope {
  const ax = err as AxiosError<{ code?: unknown }>
  if (
    ax?.isAxiosError &&
    ax.response?.data &&
    typeof ax.response.data === 'object' &&
    typeof (ax.response.data as { code?: unknown }).code === 'string'
  ) {
    const code = (ax.response.data as { code: string }).code
    const messages: Partial<Record<Exclude<SanitizedErrorCode, 'unknown'>, string>> = {
      forecast_read_api_unavailable: 'Forecast reads are currently disabled.',
      forecast_not_found: 'Forecast data is unavailable for this goal.',
      recommendation_not_found: 'The current recommendation is unavailable.',
      decision_version_conflict: 'The recommendation changed before the decision was recorded. Review it again.',
      forecast_validation_error: 'The server could not validate the current forecast evidence.',
    }
    if (code in messages) {
      return { code: code as SanitizedErrorCode, message: messages[code as Exclude<SanitizedErrorCode, 'unknown'>] ?? '' }
    }
  }
  return { code: 'unknown', message: '' }
}

// ============================================================
// Plan §3 — read path (Phase 1 forecast surfacing)
// ============================================================

/**
 * Phase 2 Slice 2 — fetch the latest persisted forecast for a goal.
 *
 * Step 1: ``GET /api/v1/forecasts?goal_id={goal_id}&limit=4`` — Phase 1
 *         bounded list filter.
 * Step 2: ``GET /api/v1/forecasts/{forecast_id}/versions/{latest_version_number}``
 *         — Phase 1 immutable version envelope.
 *
 * If no persisted forecast exists for the goal, returns
 * ``{state: 'no_forecast'}`` so the page can render an empty-state
 * affordance without an error toast.
 *
 * Server-side gate (``atlas_forecast_read_api_enabled``) propagates
 * via sanitized 503 envelope; ``readSanitizedError(.code)`` is the
 * UI state branch.
 */
export async function getLatestForecastForGoal(
  goalId: number,
): Promise<LatestForecastState> {
  const listResp = await rulesApi.get<{ forecasts: ForecastWire[] }>(
    '/api/v1/forecasts',
    { params: { goal_id: goalId, limit: 4 } },
  )
  const forecasts = listResp.data?.forecasts ?? []
  if (forecasts.length === 0) {
    return { state: 'no_forecast', goal_id: goalId }
  }
  // Phase 1 sorts server-side by `created_at` desc; pick the first.
  const forecast = forecasts[0]
  const versionResp = await rulesApi.get<ForecastVersionWire>(
    `/api/v1/forecasts/${forecast.id}/versions/${forecast.latest_version_number}`,
  )
  return {
    state: 'ready',
    goal_id: goalId,
    forecast,
    version: versionResp.data,
  }
}

// ============================================================
// Plan §3 — derivation read path
// ============================================================

/**
 * Phase 2 Slice 2 — fetch the deterministic derived recommendation
 * for the given forecast id.
 *
 * ``GET /api/v1/forecasts/{forecast_id}/recommendation`` returns the
 * frozen ``DeterministicRecommendationEnvelope``. The bare ETag the
 * caller sees in ``forecast_etag`` MUST be echoed back to the journal
 * POST as ``decision_etag`` to preserve the deterministic-replay
 * invariant.
 *
 * Sanitized errors: 503 / 404 / 422.
 */
export async function getDerivedRecommendation(
  forecastId: string,
): Promise<DeterministicRecommendationWire> {
  const resp = await rulesApi.get<DeterministicRecommendationWire>(
    `/api/v1/forecasts/${forecastId}/recommendation`,
  )
  return resp.data
}

// ============================================================
// Plan §3 — append-only journal write
// ============================================================

/**
 * Phase 2 Slice 2 — append one decision-journal row.
 *
 * ``POST /api/v1/recommendations/{recommendation_id}/decisions``
 *   Headers: ``Idempotency-Key`` (REQUIRED, 1..255 ASCII visible)
 *   Body: ``{action, decision_etag}`` (strict; extra fields rejected)
 *
 * Server returns the freshly-written ``DecisionJournalEntryEnvelope``.
 * NO money payload on this envelope — only identity + timestamp +
 * action verb (plan §5).
 *
 * Idempotent replay: same (Idempotency-Key, payload) collapses onto
 * the SAME row. The page treats replays as success.
 *
 * Sanitized errors: 503 / 404 / 409 (decision_version_conflict) /
 * 422 (forecast_validation_error).
 */
export async function postDecisionJournal(
  recommendationId: string,
  body: DecisionJournalSubmitBody,
  idempotencyKey: string,
): Promise<DecisionJournalEntryWire> {
  const resp = await rulesApi.post<DecisionJournalEntryWire>(
    `/api/v1/recommendations/${recommendationId}/decisions`,
    body,
    {
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
    },
  )
  return resp.data
}

const phase2Api = {
  getLatestForecastForGoal,
  getDerivedRecommendation,
  postDecisionJournal,
  readSanitizedError,
  mintIdempotencyKey,
}

export default phase2Api
