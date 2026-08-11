'use client'

import { useEffect, useState } from 'react'
import {
  getDecisionHistory,
  readDecisionHistoryError,
  type DecisionHistoryEntryWire,
  type DecisionAlternative,
} from '@/lib/api_phase4'

interface Goal {
  id: number
  name: string
}

type HistoryState =
  | { kind: 'loading' }
  | { kind: 'ready'; history: DecisionHistoryEntryWire[] }
  | { kind: 'unavailable' }
  | { kind: 'error' }

const actionLabels = { accept: 'Accepted', reject: 'Rejected', defer: 'Deferred' } as const
const alternativeLabels: Record<DecisionAlternative, string> = {
  do_nothing: 'Keep the current plan',
  accept: 'Accept the recommendation',
  reject: 'Reject the recommendation',
  defer: 'Defer the recommendation',
}

function lifecycleLabel(lifecycles: DecisionHistoryEntryWire['outcome_lifecycles']): string {
  // The service sends this list in recorded chronology. Only its final token
  // describes the current lifecycle; an earlier measurement must not mask a
  // later pending/not-yet-measurable correction state.
  const current = lifecycles.at(-1)
  if (current === 'measured') return 'Measured'
  if (current === 'pending') return 'Pending measurement'
  return 'Not yet measurable'
}

function dateLabel(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Recorded decision' : date.toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC',
  })
}

export default function DecisionHistorySection({ goals }: { goals: Goal[] }) {
  const [states, setStates] = useState<Record<number, HistoryState>>({})
  const [retryVersion, setRetryVersion] = useState(0)
  const goalKey = goals.map((goal) => goal.id).join('|')

  useEffect(() => {
    let cancelled = false
    setStates(Object.fromEntries(goals.map((goal) => [goal.id, { kind: 'loading' } as HistoryState])))
    void Promise.all(goals.map(async (goal) => {
      try {
        const envelope = await getDecisionHistory(goal.id)
        if (!cancelled) setStates((previous) => ({ ...previous, [goal.id]: { kind: 'ready', history: envelope.history } }))
      } catch (error) {
        if (cancelled) return
        const state = readDecisionHistoryError(error)
        setStates((previous) => ({ ...previous, [goal.id]: { kind: state === 'unavailable' ? 'unavailable' : 'error' } }))
      }
    }))
    return () => { cancelled = true }
  // Goal IDs and retryVersion are stable scalar dependencies. This deliberately
  // permits React 18 Strict Mode's setup-after-cleanup probe to issue its
  // second fetch: the first setup is cancelled, while the second resolves.
  // Depending on the caller's mapped `goals` array would instead refetch on
  // every parent render.
  }, [goalKey, retryVersion])

  if (goals.length === 0) return null

  return (
    <section className="mt-8 card p-6" aria-labelledby="decision-history-heading" data-testid="decision-history-section">
      <h2 id="decision-history-heading" className="headline-md text-primary">Decision history</h2>
      <p className="mt-1 text-sm text-secondary">Your recorded decisions and their outcome status.</p>
      <p className="mt-2 text-xs text-secondary">Recorded acceptance is approval only, not execution or success. A measured outcome is not proof that a decision caused it.</p>
      <div className="mt-5 space-y-6">
        {goals.map((goal) => <GoalHistory key={goal.id} goal={goal} state={states[goal.id] ?? { kind: 'loading' }} onRetry={() => setRetryVersion((version) => version + 1)} />)}
      </div>
    </section>
  )
}

function GoalHistory({ goal, state, onRetry }: { goal: Goal; state: HistoryState; onRetry: () => void }) {
  return (
    <section aria-labelledby={`decision-history-goal-${goal.id}`}>
      <h3 id={`decision-history-goal-${goal.id}`} className="text-base font-semibold text-primary">Decision history for {goal.name}</h3>
      {state.kind === 'loading' && <p className="mt-2 text-sm text-secondary" role="status">Loading decision history…</p>}
      {state.kind === 'unavailable' && <div className="mt-2 flex items-center gap-3" role="status"><p className="text-sm text-secondary">Decision history is currently unavailable.</p><button type="button" onClick={onRetry} className="text-sm font-medium text-primary underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">Retry decision history</button></div>}
      {state.kind === 'error' && <div className="mt-2 flex items-center gap-3" role="alert"><p className="text-sm text-secondary">Decision history could not be loaded.</p><button type="button" onClick={onRetry} className="text-sm font-medium text-primary underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">Retry decision history</button></div>}
      {state.kind === 'ready' && (state.history.length === 0 ? (
        <p className="mt-2 text-sm text-secondary">No decisions have been recorded for this goal yet.</p>
      ) : (
        <ol className="mt-3 space-y-3 border-l-2 border-outline-variant/40 pl-4" aria-label={`${goal.name} decision history`}>
          {state.history.map((entry, index) => <HistoryItem entry={entry} key={`${entry.recorded_at}-${index}`} />)}
        </ol>
      ))}
    </section>
  )
}

function HistoryItem({ entry }: { entry: DecisionHistoryEntryWire }) {
  return (
    <li className="rounded-lg bg-surface-container p-4 text-sm text-secondary">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <strong className="text-primary">{actionLabels[entry.decision_action]}</strong>
        <span aria-hidden="true">•</span>
        <time dateTime={entry.recorded_at}>{dateLabel(entry.recorded_at)}</time>
        <span className="rounded-full bg-surface px-2 py-0.5 text-xs font-medium text-primary">{lifecycleLabel(entry.outcome_lifecycles)}</span>
      </div>
      {entry.supersedes_history_id && <p className="mt-2 text-xs font-medium text-secondary">Corrects an earlier decision</p>}
      <details className="mt-3">
        <summary className="cursor-pointer font-medium text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">View rationale and alternatives</summary>
        <p className="mt-2 leading-relaxed">{entry.rationale}</p>
        <p className="mt-3 font-medium text-primary">Alternatives considered</p>
        <ul className="mt-1 list-disc pl-5">
          {entry.alternatives.map((alternative, index) => <li key={`${alternative}-${index}`}>{alternativeLabels[alternative]}</li>)}
        </ul>
      </details>
    </li>
  )
}
