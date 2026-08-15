'use client'

import { useState } from 'react'
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
import { rulesService, type Goal, type RecommendationLogItem } from '@/lib/api'

const tabs = [{ id: 'recommendations', label: 'Recommendations' }, { id: 'journal', label: 'Decision journal' }, { id: 'outcomes', label: 'Outcomes' }] as const

type DecisionView = (typeof tabs)[number]['id']

function DecisionList({ items, loading, error, onAction, busyId }: { items: RecommendationLogItem[]; loading: boolean; error: string | null; onAction: (id: number, action: 'approve' | 'deny' | 'dismiss') => void; busyId: number | null }) {
  if (loading) return <p className="card p-6 text-sm text-secondary" role="status">Loading persisted recommendations…</p>
  if (error) return <section className="card p-6" role="alert"><h2 className="headline-sm text-primary">Recommendations unavailable</h2><p className="mt-2 text-sm text-secondary">Atlas could not load the recommendation record. No recommendation is fabricated in this state.</p></section>
  if (items.length === 0) return <section className="card p-6"><h2 className="headline-sm text-primary">No recommendations to review</h2><p className="mt-2 text-sm text-secondary">New recommendations appear only when the server has current evidence and a reviewable next step.</p></section>
  return <div className="space-y-4" data-testid="decisions-list">{items.map((item) => <article key={item.id} className="card p-5" data-testid={`decision-${item.id}`}><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="label-sm text-secondary">{item.category} · {item.priority} priority</p><h2 className="headline-sm mt-1 text-primary">{item.title}</h2></div><span className="rounded-full bg-surface-container px-3 py-1 text-xs font-semibold text-secondary">{item.status}</span></div><p className="mt-3 text-sm leading-relaxed text-secondary">{item.description}</p>{item.impact && <p className="mt-3 text-sm font-medium text-primary">Potential impact: {item.impact}</p>}<p className="mt-3 text-xs text-tertiary">Recorded {new Date(item.created_at).toLocaleDateString()}</p>{item.status === 'pending' && <div className="mt-4 flex flex-wrap gap-2 border-t border-outline-variant/20 pt-4"><button type="button" onClick={() => onAction(item.id, 'approve')} disabled={busyId === item.id} className="btn-primary inline-flex min-h-11 items-center gap-2 px-3 py-2 text-sm"><Check className="h-4 w-4" aria-hidden="true" />{busyId === item.id ? 'Saving…' : 'Accept for review'}</button><button type="button" onClick={() => onAction(item.id, 'deny')} disabled={busyId === item.id} className="btn-secondary inline-flex min-h-11 items-center gap-2 px-3 py-2 text-sm"><X className="h-4 w-4" aria-hidden="true" />Reject</button><button type="button" onClick={() => onAction(item.id, 'dismiss')} disabled={busyId === item.id} className="btn-secondary inline-flex min-h-11 items-center gap-2 px-3 py-2 text-sm"><Clock3 className="h-4 w-4" aria-hidden="true" />Defer review</button></div>}</article>)}</div>
}

function DecisionsWorkspace() {
  const [busyId, setBusyId] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const { data: recommendations, loading: recommendationsLoading, error: recommendationsError, refetch } = useCachedFetch('decisions-recommendations', () => rulesService.listRecommendations({ limit: 50 }), [], { group: 'decisions' })
  const { data: goals, loading: goalsLoading } = useCachedFetch<Goal[]>('decisions-goals', () => rulesService.listGoals(), [], { group: 'decisions' })
  const searchParams = useSearchParams()
  const requested = searchParams.get('view')
  const view: DecisionView = tabs.some((tab) => tab.id === requested) ? requested as DecisionView : 'recommendations'

  const takeAction = async (id: number, action: 'approve' | 'deny' | 'dismiss') => {
    setBusyId(id)
    setActionError(null)
    try { await rulesService.takeRecommendationAction(id, action); refetch() }
    catch { setActionError('The decision could not be recorded. The recommendation remains unchanged.') }
    finally { setBusyId(null) }
  }

  const content = view === 'recommendations' ? <><DecisionList items={recommendations?.items ?? []} loading={recommendationsLoading} error={recommendationsError} onAction={takeAction} busyId={busyId} />{actionError && <p className="mt-3 text-sm text-danger" role="alert">{actionError}</p>}</> : goalsLoading ? <p className="card p-6 text-sm text-secondary" role="status">Loading decision history…</p> : <><section className="card p-5"><div className="flex items-start gap-3"><ShieldAlert className="h-5 w-5 shrink-0 text-warning-600" aria-hidden="true" /><div><h2 className="headline-sm text-primary">Approval is not execution</h2><p className="mt-2 text-sm leading-relaxed text-secondary">Accepting, rejecting, or deferring a recommendation records your decision. It does not place a trade, move money, or prove an outcome. Immutable history and outcome lifecycle status are shown below.</p></div></div></section><DecisionHistorySection goals={(goals ?? []).map((goal) => ({ id: goal.id, name: goal.name }))} /></>

  return <section data-testid="decisions-page" className="space-y-6"><PageHeader title="Decisions" description="Review recommendations, record decisions, and inspect outcome evidence without implying execution." /><PageTabs tabs={tabs} activeId={view} queryKey="view" /><AnalyticalContextBar showRange={false} pageSlot={<span className="text-xs text-secondary">Decision state is server-owned and append-only where applicable.</span>} coverage={<span>{recommendations?.pending_count ?? 0} pending</span>} freshness={<span>Owner scoped</span>} />{view === 'outcomes' && <AnalyticalPageFrame header={null} primaryVisualization={content} />}{view !== 'outcomes' && content}</section>
}

export default function DecisionsPage() {
  return <PageLayout><AtlasFilterProvider><DecisionsWorkspace /></AtlasFilterProvider></PageLayout>
}
