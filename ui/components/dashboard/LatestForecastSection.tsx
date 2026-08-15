'use client'

/**
 * Phase 2 Slice 2 — Per-Goal Latest Forecast + Recommendation Section.
 *
 * Container that owns the per-goal async state machine:
 *   forecast → recommendation → decide → recorded
 *
 * Per §3 of PHASE2_VERTICAL_SLICE_PLAN.md:
 *   1. ``getLatestForecastForGoal(goal_id)`` (Phase 1 read endpoints)
 *   2. ``getDerivedRecommendation(forecast_id)`` (Slice 1 derivation)
 *   3. ``postDecisionJournal(recommendation_id, body, idempotency_key)``
 *      (Slice 1 append-only journal)
 *
 * Sanitized 503/404/409/422 envelopes surface via inline section
 * banners with ``code`` semantics — NEVER echo raw response bodies.
 * Money stays as canonical Decimal STRING until deliberate display
 * formatting. NO ``Number()`` coercion on the API path.
 *
 * Per-goal isolation: each goal's fetch chain is independent so a
 * 404 on one goal's forecast does not block the others (Phase F2 #2
 * regression discipline).
 *
 * Cross-reload behavior: per Phase 2 plan §2 AC10, the journal
 * state is intentionally NOT bound across reload. On reload, all
 * cards revert to action buttons; re-clicks are idempotent retries
 * that collapse to the SAME journal row via the (Idempotency-Key,
 * payload-hash) contract — the canonical state in the DB is always
 * preserved; the UI is ephemeral by design.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getLatestForecastForGoal,
  getDerivedRecommendationResource,
  postDecisionJournal,
  readSanitizedError,
  mintIdempotencyKey,
  type DecisionAction,
  type DecisionETag,
  type DecisionJournalEntryWire,
  type DeterministicRecommendationWire,
  type LatestForecastState,
} from '@/lib/api_phase2'
import LatestForecastCard from '@/components/dashboard/LatestForecastCard'
import RecommendationExplainedCard from '@/components/dashboard/RecommendationExplainedCard'
import DecisionRecordedToast from '@/components/dashboard/DecisionRecordedToast'

export interface Goal {
  id: number
  name: string
  /** Canonical Decimal string from the existing goals endpoint. */
  target_amount: string
}

interface PendingDecision {
  action: DecisionAction
  recommendationId: string
  decisionEtag: DecisionETag
  idempotencyKey: string
}

interface PerGoalSliceState {
  forecast: 'loading' | LatestForecastState
  recommendation:
    | 'idle'
    | 'loading'
    | DeterministicRecommendationWire
  recorded: DecisionJournalEntryWire | null
  decisionEtag: DecisionETag | null
  busy: boolean
  pendingDecision: PendingDecision | null
  decisionError: string | null
}

const EMPTY: PerGoalSliceState = {
  forecast: 'loading',
  recommendation: 'idle',
  recorded: null,
  decisionEtag: null,
  busy: false,
  pendingDecision: null,
  decisionError: null,
}

export default function LatestForecastSection({ goals }: { goals: Goal[] }) {
  const [perGoal, setPerGoal] = useState<Record<number, PerGoalSliceState>>({})
  const [toast, setToast] = useState<DecisionJournalEntryWire | null>(null)
  const [sectionError, setSectionError] = useState<string | null>(null)
  const pendingDecisionsRef = useRef<Record<number, PendingDecision | null>>({})
  const decisionBusyRef = useRef<Record<number, boolean>>({})

  // Goals-array identity change (e.g., user added/removed a goal)
  // drives a fresh per-goal fetch.
  const goalKey = goals.map((g) => `${g.id}:${g.target_amount}`).join('|')
  const goalKeyRef = useRef('')
  useEffect(() => {
    if (goalKeyRef.current === goalKey) return
    goalKeyRef.current = goalKey
    let cancelled = false

    async function fetchGoal(goal: Goal): Promise<void> {
      // A changed forecast/recommendation starts a new logical decision.
      pendingDecisionsRef.current[goal.id] = null
      decisionBusyRef.current[goal.id] = false
      // 1) Forecast.
      let fc: LatestForecastState
      try {
        fc = await getLatestForecastForGoal(goal.id)
        if (cancelled) return
      } catch (err) {
        if (cancelled) return
        const env = readSanitizedError(err)
        setPerGoal((prev) => ({
          ...prev,
          [goal.id]: {
            ...EMPTY,
            forecast: { state: 'no_forecast', goal_id: goal.id },
          },
        }))
        if (env.code === 'forecast_read_api_unavailable') {
          setSectionError('Forecast reads are currently disabled.')
          return
        }
        if (env.code === 'forecast_not_found') {
          // Per-goal absent — silent.
          return
        }
        if (env.code !== 'unknown') {
          setSectionError(env.message || 'Forecast data is unavailable.')
        }
        return
      }

      setPerGoal((prev) => ({
        ...prev,
        [goal.id]: {
          ...EMPTY,
          forecast: fc,
          recommendation: fc.state === 'ready' ? 'loading' : 'idle',
          pendingDecision: null,
          decisionError: null,
        },
      }))
      if (fc.state !== 'ready') return

      // 2) Recommendation.
      try {
        const resource = await getDerivedRecommendationResource(fc.forecast.id)
        if (cancelled) return
        setPerGoal((prev) => ({
          ...prev,
          [goal.id]: {
            ...(prev[goal.id] ?? EMPTY),
            recommendation: resource.recommendation,
            decisionEtag: resource.decisionEtag,
            pendingDecision: null,
            decisionError: null,
          },
        }))
      } catch (err) {
        if (cancelled) return
        const env = readSanitizedError(err)
        if (env.code === 'recommendation_not_found') {
          // Silent: forecast card alone is enough.
          return
        }
        if (env.code === 'forecast_read_api_unavailable') {
          setSectionError('Forecast reads are currently disabled.')
          return
        }
        if (env.code !== 'unknown') {
          setSectionError(env.message || 'Forecast data is unavailable.')
        }
      }
    }

    void Promise.all(goals.map(fetchGoal))
    return () => {
      cancelled = true
    }
  }, [goalKey, goals])

  const handleDecide = useCallback(
    async (
      action: DecisionAction,
      rec: DeterministicRecommendationWire,
      decisionEtag: DecisionETag,
    ) => {
      const goalId = rec.linked_goal_id
      if (decisionBusyRef.current[goalId]) return

      const existing = pendingDecisionsRef.current[goalId]
      const pendingDecision =
        existing &&
        existing.action === action &&
        existing.recommendationId === rec.forecast_id &&
        existing.decisionEtag === decisionEtag
          ? existing
          : {
              action,
              recommendationId: rec.forecast_id,
              decisionEtag,
              idempotencyKey: mintIdempotencyKey(),
            }
      pendingDecisionsRef.current[goalId] = pendingDecision
      decisionBusyRef.current[goalId] = true
      setPerGoal((prev) => ({
        ...prev,
        [goalId]: {
          ...(prev[goalId] ?? EMPTY),
          busy: true,
          pendingDecision,
          decisionError: null,
        },
      }))
      try {
        const entry = await postDecisionJournal(
          rec.forecast_id,
          { action, decision_etag: decisionEtag },
          pendingDecision.idempotencyKey,
        )
        pendingDecisionsRef.current[goalId] = null
        decisionBusyRef.current[goalId] = false
        setPerGoal((prev) => ({
          ...prev,
          [goalId]: {
            ...(prev[goalId] ?? EMPTY),
            busy: false,
            pendingDecision: null,
            decisionError: null,
            recorded: entry,
          },
        }))
        setToast(entry)
      } catch (err) {
        decisionBusyRef.current[goalId] = false
        const env = readSanitizedError(err)
        const decisionError =
          env.code === 'decision_version_conflict'
            ? 'This recommendation has changed. Refresh before trying again.'
            : env.code === 'recommendation_not_found'
              ? 'That recommendation is no longer available.'
              : env.code === 'forecast_validation_error'
                ? env.message || 'That decision was rejected.'
                : env.code !== 'unknown'
                  ? env.message || 'Could not record your decision.'
                  : 'The response was not confirmed. Retry with the same request.'
        const retryable = env.code === 'unknown'
        if (!retryable) {
          pendingDecisionsRef.current[goalId] = null
        }
        if (env.code === 'decision_version_conflict') {
          setSectionError(decisionError)
        }
        setPerGoal((prev) => ({
          ...prev,
          [goalId]: {
            ...(prev[goalId] ?? EMPTY),
            busy: false,
            pendingDecision: retryable ? pendingDecision : null,
            decisionError,
          },
        }))
      }
    },
    [],
  )

  if (goals.length === 0) return null

  return (
    <section
      className="mt-6 mb-6"
      aria-label="Latest forecast and recommendation"
      data-testid="latest-forecast-section"
    >
      {sectionError && (
        <div
          role="alert"
          data-testid="latest-forecast-section-error"
          className="mb-4 flex items-start gap-2 p-3 bg-warning-50 text-warning-700 border border-warning-200 rounded-lg"
        >
          <p className="text-sm flex-1">{sectionError}</p>
          <button
            type="button"
            onClick={() => setSectionError(null)}
            className="text-on-surface-variant hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500 transition-colors"
            aria-label="Dismiss section error"
          >
            ×
          </button>
        </div>
      )}
      {goals.map((goal) => {
        const state = perGoal[goal.id] ?? EMPTY
        // Typed narrow: when ``state.forecast`` is the ready variant
        // we hand the narrowed object into JSX instead of relying on
        // a separate boolean (TS does not propagate narrowing across
        // a different variable). ``fcState`` is either the ready
        // variant or ``null`` so accessing ``fcState.forecast`` /
        // ``fcState.version`` is safe.
        const fcState =
          state.forecast !== 'loading' && state.forecast.state === 'ready'
            ? state.forecast
            : null
        const rec =
          typeof state.recommendation === 'object'
            ? state.recommendation
            : null
        return (
          <div
            key={goal.id}
            className="mb-6"
            data-testid={`goal-slice-${goal.id}`}
          >
            {fcState && (
              <LatestForecastCard
                goalName={goal.name}
                goalTargetAmount={goal.target_amount}
                forecast={fcState.forecast}
                version={fcState.version}
              />
            )}
            {rec && (
              <RecommendationExplainedCard
                recommendation={rec}
                sourceVersionNumber={
                  fcState ? fcState.version.version_number : 0
                }
                sourceCalculatedAt={
                  fcState
                    ? fcState.version.calculated_at
                    : rec.evidence_references.data_as_of
                }
                sourceDataAgeDays={
                  fcState ? fcState.version.drivers.data_age_days : 0
                }
                onDecide={(action, recommendation) => {
                  if (state.decisionEtag) void handleDecide(action, recommendation, state.decisionEtag)
                }}
                onRetry={
                  state.pendingDecision && state.decisionEtag
                    ? () => void handleDecide(state.pendingDecision!.action, rec, state.decisionEtag!)
                    : undefined
                }
                decisionError={state.decisionError}
                recordedEntry={state.recorded}
                busy={state.busy}
              />
            )}
          </div>
        )
      })}
      <DecisionRecordedToast
        entry={toast}
        onDismiss={() => setToast(null)}
      />
    </section>
  )
}
