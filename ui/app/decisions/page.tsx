'use client'

import { useMemo, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { Check, Clock3, ShieldAlert, X } from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import PageTabs from '@/components/ui/PageTabs'
import AnalyticalContextBar from '@/components/ui/AnalyticalContextBar'
import AnalyticalPageFrame from '@/components/ui/AnalyticalPageFrame'
import { AtlasFilterProvider } from '@/components/ui/AtlasFilterContext'
import DecisionHistorySection from '@/components/dashboard/DecisionHistorySection'
import { useCachedFetch } from '@/lib/cache'
import { rulesService, type Goal } from '@/lib/api'
import {
  getDerivedRecommendationResource,
  getLatestForecastForGoal,
  mintIdempotencyKey,
  postDecisionJournal,
  readSanitizedError,
  type DecisionETag,
  type DecisionJournalEntryWire,
  type DeterministicRecommendationWire,
} from '@/lib/api_phase2'
import {
  getDecisionHistoryForGoals,
  readDecisionHistoryError,
  recordDecisionHistory,
  type DecisionHistorySnapshot,
} from '@/lib/api_phase4'

const tabs = [{ id: 'recommendations', label: 'Recommendations' }, { id: 'journal', label: 'Decision journal' }, { id: 'outcomes', label: 'Outcomes' }] as const

type DecisionView = (typeof tabs)[number]['id']
type DecisionAction = 'accept' | 'reject' | 'defer'
type DecisionButtonAction = 'approve' | 'deny' | 'dismiss'

interface DecisionRecommendation {
  id: string
  goalId: number
  goalName: string
  recommendation: DeterministicRecommendationWire
  decisionEtag: DecisionETag
}

interface DecisionRecommendationEnvelope {
  items: DecisionRecommendation[]
  unavailableGoals: number
}

function recommendationId(recommendation: DeterministicRecommendationWire): string | null {
  const decideLink = recommendation.links.find((link) => link.rel === 'decide')
  const match = decideLink?.href.match(/\/recommendations\/([^/]+)\/decisions$/)
  return match?.[1] ?? null
}

async function loadDerivedRecommendations(goals: Goal[]): Promise<DecisionRecommendationEnvelope> {
  const results = await Promise.allSettled(goals.map(async (goal) => {
    const latest = await getLatestForecastForGoal(goal.id)
    if (latest.state === 'no_forecast') return null
    const resource = await getDerivedRecommendationResource(latest.forecast.id)
    const id = recommendationId(resource.recommendation)
    if (!id) return null
    return { id, goalId: goal.id, goalName: goal.name, recommendation: resource.recommendation, decisionEtag: resource.decisionEtag }
  }))

  const items: DecisionRecommendation[] = []
  let unavailableGoals = 0
  results.forEach((result) => {
    if (result.status === 'fulfilled' && result.value) items.push(result.value)
    if (result.status === 'rejected') unavailableGoals += 1
  })
  return { items, unavailableGoals }
}

function DecisionList({
  envelope,
  loading,
  error,
  onAction,
  busyId,
  recordedActions,
  historyUnavailableGoalIds,
  pendingHistory,
  onRetryHistory,
}: {
  envelope: DecisionRecommendationEnvelope | null
  loading: boolean
  error: string | null
  onAction: (item: DecisionRecommendation, action: DecisionButtonAction) => void
  busyId: string | null
  recordedActions: Record<string, DecisionAction>
  historyUnavailableGoalIds: number[]
  pendingHistory: Record<string, boolean>
  onRetryHistory: (item: DecisionRecommendation) => void
}) {
  if (loading) return <p className="card p-6 text-sm text-secondary" role="status">Loading server-owned recommendations…</p>
  if (error) return <section className="card p-6" role="alert"><h2 className="headline-sm text-primary">Recommendations unavailable</h2><p className="mt-2 text-sm text-secondary">Atlas could not load the authoritative recommendation record. No recommendation is fabricated in this state.</p></section>
  if (!envelope || (envelope.items.length === 0 && envelope.unavailableGoals > 0)) return <section className="card p-6" role="status"><h2 className="headline-sm text-primary">Recommendations unavailable</h2><p className="mt-2 text-sm text-secondary">The server did not make a current forecast and recommendation available for review. Existing decisions remain in the journal.</p></section>
  if (envelope.items.length === 0) return <section className="card p-6"><h2 className="headline-sm text-primary">No recommendations to review</h2><p className="mt-2 text-sm text-secondary">New recommendations appear only when the server has current evidence and a reviewable next step.</p></section>

  return <div className="space-y-4" data-testid="decisions-list">
    {envelope.unavailableGoals > 0 && <p className="rounded-lg border border-warning-200 bg-warning-50 p-4 text-sm text-warning-900" role="status">{envelope.unavailableGoals} goal{envelope.unavailableGoals === 1 ? '' : 's'} did not have an available recommendation. Atlas is showing only server responses that passed the authoritative contract.</p>}
    {historyUnavailableGoalIds.length > 0 && <p className="rounded-lg border border-warning-200 bg-warning-50 p-4 text-sm text-warning-900" role="status">Decision history is unavailable for {historyUnavailableGoalIds.length === 1 ? 'this goal' : 'some goals'}. Decision actions are disabled until the server-backed history can be loaded.</p>}
    {envelope.items.map((item) => {
      const recorded = recordedActions[item.id]
      const historyUnavailable = historyUnavailableGoalIds.includes(item.goalId)
      const historyPending = pendingHistory[item.id] === true
      return <article key={item.id} className="card p-5" data-testid={`decision-${item.id}`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><p className="label-sm text-secondary">{item.goalName} · {item.recommendation.confidence} confidence</p><h2 className="headline-sm mt-1 text-primary">{item.recommendation.action_verb}</h2></div>
          <span className="rounded-full bg-surface-container px-3 py-1 text-xs font-semibold text-secondary">{recorded ? `Recorded: ${recorded}` : 'Awaiting decision'}</span>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-secondary">{item.recommendation.why_now}</p>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div><dt className="font-semibold text-primary">Evidence as of</dt><dd className="mt-1 text-secondary">{new Date(item.recommendation.evidence_references.data_as_of).toLocaleDateString()}</dd></div>
          <div><dt className="font-semibold text-primary">Expected impact range</dt><dd className="mt-1 font-mono text-secondary">{item.recommendation.expected_impact_range.min_delta_decimal} to {item.recommendation.expected_impact_range.max_delta_decimal}</dd></div>
          <div><dt className="font-semibold text-primary">Risks</dt><dd className="mt-1 text-secondary">{item.recommendation.risks.length ? item.recommendation.risks.join(', ').replaceAll('_', ' ') : 'No risk tokens returned'}</dd></div>
          <div><dt className="font-semibold text-primary">Expires</dt><dd className="mt-1 text-secondary">{new Date(item.recommendation.expiration).toLocaleDateString()}</dd></div>
        </dl>
        <p className="mt-4 text-xs leading-relaxed text-tertiary">Recording a decision appends to the server journal. It does not execute a trade, move money, or prove an outcome.</p>
        {!recorded && !historyUnavailable && !historyPending && <div className="mt-4 flex flex-wrap gap-2 border-t border-outline-variant/20 pt-4"><button type="button" onClick={() => onAction(item, 'approve')} disabled={busyId === item.id} className="btn-primary inline-flex min-h-11 items-center gap-2 px-3 py-2 text-sm"><Check className="h-4 w-4" aria-hidden="true" />{busyId === item.id ? 'Saving…' : 'Accept for review'}</button><button type="button" onClick={() => onAction(item, 'deny')} disabled={busyId === item.id} className="btn-secondary inline-flex min-h-11 items-center gap-2 px-3 py-2 text-sm"><X className="h-4 w-4" aria-hidden="true" />Reject</button><button type="button" onClick={() => onAction(item, 'dismiss')} disabled={busyId === item.id} className="btn-secondary inline-flex min-h-11 items-center gap-2 px-3 py-2 text-sm"><Clock3 className="h-4 w-4" aria-hidden="true" />Defer review</button></div>}
        {historyPending && <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-warning-200 pt-4"><p className="text-sm text-warning-900" role="status">Journal entry recorded; history linkage still needs confirmation.</p><button type="button" onClick={() => onRetryHistory(item)} disabled={busyId === item.id} className="btn-secondary min-h-11 px-3 py-2 text-sm">Retry history linkage</button></div>}
      </article>
    })}
  </div>
}

function DecisionsWorkspace() {
  const [busyId, setBusyId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [recordedActions, setRecordedActions] = useState<Record<string, DecisionAction>>({})
  const [historyVersion, setHistoryVersion] = useState(0)
  const [pendingHistory, setPendingHistory] = useState<Record<string, { item: DecisionRecommendation; action: DecisionAction; entry: DecisionJournalEntryWire; idempotencyKey: string }>>({})
  const { data: goals, loading: goalsLoading } = useCachedFetch<Goal[]>('decisions-goals', () => rulesService.listGoals(), [], { group: 'decisions' })
  const goalIds = goals?.map((goal) => goal.id) ?? []
  const { data: recommendations, loading: recommendationsLoading, error: recommendationsError, refetch } = useCachedFetch<DecisionRecommendationEnvelope>('decisions-derived-recommendations', () => loadDerivedRecommendations(goals ?? []), [goalIds], { group: 'decisions', enabled: goals !== null })
  const { data: historySnapshot, loading: historyLoading, refetch: refetchHistory } = useCachedFetch<DecisionHistorySnapshot>('decisions-history', () => getDecisionHistoryForGoals(goalIds), [goalIds], { group: 'decisions', enabled: goals !== null })
  const persistedActions = useMemo(() => {
    const actions: Record<string, DecisionAction> = {}
    Object.values(historySnapshot?.historyByGoal ?? {}).forEach((entries) => entries.forEach((entry) => { actions[entry.recommendation_id] = entry.decision_action }))
    return actions
  }, [historySnapshot])
  const searchParams = useSearchParams()
  const requested = searchParams.get('view')
  const view: DecisionView = tabs.some((tab) => tab.id === requested) ? requested as DecisionView : 'recommendations'

  const persistHistory = async (item: DecisionRecommendation, action: DecisionAction, entry: DecisionJournalEntryWire, idempotencyKey: string) => {
    try {
      await recordDecisionHistory(item.goalId, {
        recommendation_id: item.id,
        decision_journal_entry_id: entry.journal_entry_id,
        alternatives: ['do_nothing', action],
        rationale: item.recommendation.why_now,
      }, idempotencyKey)
      setPendingHistory((previous) => {
        const next = { ...previous }
        delete next[item.id]
        return next
      })
      setRecordedActions((previous) => ({ ...previous, [item.id]: action }))
      setHistoryVersion((version) => version + 1)
      refetchHistory()
      refetch()
    } catch (error) {
      const state = readDecisionHistoryError(error)
      setPendingHistory((previous) => ({ ...previous, [item.id]: { item, action, entry, idempotencyKey } }))
      setActionError(state === 'conflict'
        ? 'The decision history changed before linkage was recorded. Retry history linkage.'
        : state === 'unavailable'
          ? 'The decision was recorded, but server-backed history is currently unavailable. Retry history linkage.'
          : 'The decision was recorded, but its server-backed history could not be confirmed. Retry history linkage.')
    }
  }

  const takeAction = async (item: DecisionRecommendation, buttonAction: DecisionButtonAction) => {
    const action: DecisionAction = buttonAction === 'approve' ? 'accept' : buttonAction === 'deny' ? 'reject' : 'defer'
    setBusyId(item.id)
    setActionError(null)
    try {
      const entry = await postDecisionJournal(item.id, { action, decision_etag: item.decisionEtag }, mintIdempotencyKey())
      await persistHistory(item, action, entry, `history-${entry.journal_entry_id}`)
    } catch (error) {
      const sanitized = readSanitizedError(error)
      setActionError(sanitized.message || 'The decision could not be recorded. The recommendation remains unchanged.')
    } finally { setBusyId(null) }
  }

  const retryHistory = async (item: DecisionRecommendation) => {
    const pending = pendingHistory[item.id]
    if (!pending) return
    setBusyId(item.id)
    setActionError(null)
    try { await persistHistory(item, pending.action, pending.entry, pending.idempotencyKey) }
    finally { setBusyId(null) }
  }

  const effectiveRecordedActions = { ...persistedActions, ...recordedActions }
  const content = view === 'recommendations' ? <><DecisionList envelope={recommendations} loading={goalsLoading || recommendationsLoading || historyLoading} error={recommendationsError} onAction={takeAction} busyId={busyId} recordedActions={effectiveRecordedActions} historyUnavailableGoalIds={historySnapshot?.unavailableGoalIds ?? []} pendingHistory={Object.fromEntries(Object.keys(pendingHistory).map((id) => [id, true]))} onRetryHistory={retryHistory} />{actionError && <p className="mt-3 text-sm text-danger" role="alert">{actionError}</p>}</> : goalsLoading ? <p className="card p-6 text-sm text-secondary" role="status">Loading decision history…</p> : <><section className="card p-5"><div className="flex items-start gap-3"><ShieldAlert className="h-5 w-5 shrink-0 text-warning-600" aria-hidden="true" /><div><h2 className="headline-sm text-primary">Approval is not execution</h2><p className="mt-2 text-sm leading-relaxed text-secondary">Accepting, rejecting, or deferring a recommendation records your decision. It does not place a trade, move money, or prove an outcome. Immutable history and outcome lifecycle status are shown below.</p></div></div></section><DecisionHistorySection key={historyVersion} goals={(goals ?? []).map((goal) => ({ id: goal.id, name: goal.name }))} snapshot={historySnapshot ?? undefined} /></>

  return <section data-testid="decisions-page" className="space-y-6"><PageHeader title="Decisions" description="Review server-owned recommendations, record append-only decisions, and inspect outcome evidence without implying execution." /><PageTabs tabs={tabs} activeId={view} queryKey="view" /><AnalyticalContextBar showRange={false} pageSlot={<span className="text-xs text-secondary">Decision state is server-owned and append-only where applicable.</span>} coverage={<span>{recommendations?.items.length ?? 0} current</span>} freshness={<span>Owner scoped</span>} />{view === 'outcomes' && <AnalyticalPageFrame header={null} primaryVisualization={content} />}{view !== 'outcomes' && content}</section>
}

export default function DecisionsPage() {
  return <PageLayout><AtlasFilterProvider><DecisionsWorkspace /></AtlasFilterProvider></PageLayout>
}
