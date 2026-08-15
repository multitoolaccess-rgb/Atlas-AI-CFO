'use client'

import { useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { Archive, GitCompareArrows, Loader2, ShieldCheck, SlidersHorizontal } from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import PageTabs from '@/components/ui/PageTabs'
import AnalyticalContextBar from '@/components/ui/AnalyticalContextBar'
import { AtlasFilterProvider } from '@/components/ui/AtlasFilterContext'
import EmptyState from '@/components/ui/EmptyState'
import { Button, Input, Select } from '@/components/ui'
import { useCachedFetch } from '@/lib/cache'
import { rulesService, type Goal } from '@/lib/api'
import { archiveScenario, compareScenarios, generateScenario, listScenarios, readScenarioError, type ScenarioEnvelope, type ScenarioInput, type ScenarioListItem } from '@/lib/api_scenarios'

const tabs = [{ id: 'scenarios', label: 'Scenarios' }, { id: 'comparisons', label: 'Comparisons' }, { id: 'archive', label: 'Archive' }] as const

type ScenarioView = (typeof tabs)[number]['id']

function ScenarioList({ items, selected, onSelect }: { items: ScenarioListItem[]; selected: string | null; onSelect: (id: string) => void }) {
  if (items.length === 0) return <p className="rounded-lg border border-dashed border-outline-variant p-4 text-sm text-secondary">No saved scenarios for this goal yet. Generate one from an explicitly bounded change below.</p>
  return <ul className="space-y-2" aria-label="Saved scenarios">{items.map((item) => <li key={item.scenario_id}><button type="button" onClick={() => onSelect(item.scenario_id)} className={`w-full rounded-lg border p-4 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${selected === item.scenario_id ? 'border-primary-500 bg-primary-50' : 'border-outline-variant hover:border-primary-300'}`}><div className="flex items-center justify-between gap-3"><span className="font-mono text-xs text-secondary">{item.scenario_id.slice(0, 8)} · v{item.version_number}</span><span className={`text-xs font-semibold ${item.lifecycle_state === 'archived' ? 'text-secondary' : 'text-primary'}`}>{item.lifecycle_state}</span></div><p className="mt-2 text-sm font-medium text-primary">Server comparison: {item.difference_from_baseline}</p><p className="mt-1 text-xs text-secondary">{item.target_reached ? 'Target reached in server result' : 'Target not reached in server result'} · {item.currency}</p></button></li>)}</ul>
}

function ScenarioResult({ result }: { result: ScenarioEnvelope }) {
  return <section className="card p-5" aria-live="polite"><div className="flex items-start gap-3"><ShieldCheck className="h-5 w-5 shrink-0 text-primary-600" aria-hidden="true" /><div><h2 className="headline-sm text-primary">Authoritative server result</h2><p className="mt-1 text-sm text-secondary">Version {result.version_number} · baseline version {result.baseline_version_number} · {result.currency}. Values below are returned by the server; the browser performed no financial calculation.</p></div></div><dl className="mt-4 grid gap-3 sm:grid-cols-3">{Object.entries(result.comparison).map(([key, value]) => <div key={key} className="rounded-lg bg-surface-container p-3"><dt className="text-xs text-secondary">{key.replaceAll('_', ' ')}</dt><dd className="mt-1 break-words font-mono text-sm font-semibold text-primary">{String(value)}</dd></div>)}</dl><details className="mt-4"><summary className="cursor-pointer text-sm font-medium text-primary">View assumptions and provenance identifiers</summary><p className="mt-2 text-xs leading-relaxed text-secondary">Model {result.model_version}; calculation {result.calculation_version}; baseline hash {result.baseline_input_state_hash}. These identifiers support reproducibility and do not represent a client-supplied authority.</p></details></section>
}

function ScenarioLabWorkspace() {
  const searchParams = useSearchParams()
  const requested = searchParams.get('view')
  const view: ScenarioView = tabs.some((tab) => tab.id === requested) ? requested as ScenarioView : 'scenarios'
  const { data: goals, loading: goalsLoading } = useCachedFetch<Goal[]>('scenario-goals', () => rulesService.listGoals(), [], { group: 'scenario-lab' })
  const [selectedGoalId, setSelectedGoalId] = useState<number | null>(null)
  const activeGoalId = selectedGoalId ?? goals?.[0]?.id ?? null
  const scenarios = useCachedFetch(activeGoalId ? `scenario-list-${activeGoalId}` : 'scenario-list-disabled', () => listScenarios(activeGoalId ?? 0, true), [activeGoalId], { group: 'scenario-lab', enabled: activeGoalId !== null })
  const [delta, setDelta] = useState('')
  const [startDate, setStartDate] = useState('')
  const [stopDate, setStopDate] = useState('')
  const [outflowDate, setOutflowDate] = useState('')
  const [outflowAmount, setOutflowAmount] = useState('')
  const [mutationError, setMutationError] = useState<string | null>(null)
  const [mutating, setMutating] = useState(false)
  const [result, setResult] = useState<ScenarioEnvelope | null>(null)
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null)
  const [comparison, setComparison] = useState<Record<string, unknown> | null>(null)

  const generate = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!activeGoalId) return
    const input: ScenarioInput = {}
    if (delta.trim()) input.monthly_contribution_delta = delta.trim()
    if (startDate) input.contribution_start_date = startDate
    if (stopDate) input.contribution_stop_date = stopDate
    if (outflowDate || outflowAmount) input.one_time_outflow = { date: outflowDate, amount: outflowAmount }
    setMutating(true); setMutationError(null)
    try { setResult(await generateScenario(activeGoalId, input, `scenario-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`)); scenarios.refetch() }
    catch (error) { setMutationError(readScenarioError(error).message) }
    finally { setMutating(false) }
  }

  const archive = async () => {
    if (!selectedScenario) return
    setMutating(true); setMutationError(null)
    try { await archiveScenario(selectedScenario, `archive-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`); scenarios.refetch() }
    catch (error) { setMutationError(readScenarioError(error).message) }
    finally { setMutating(false) }
  }

  const compare = async () => {
    const ids = (scenarios.data?.items ?? []).filter((item) => item.lifecycle_state === 'active').slice(0, 3).map((item) => item.scenario_id)
    if (ids.length === 0) return
    setMutating(true); setMutationError(null)
    try { const response = await compareScenarios(ids); setComparison(Object.fromEntries(response.scenarios.map((item) => [item.scenario_id, item.comparison]))) }
    catch (error) { setMutationError(readScenarioError(error).message) }
    finally { setMutating(false) }
  }

  const selectedGoal = goals?.find((goal) => goal.id === activeGoalId)
  const content = goalsLoading ? <p className="card p-6 text-sm text-secondary" role="status">Loading goals for Scenario Lab…</p> : !selectedGoal ? <EmptyState testId="scenario-no-goal" icon={<SlidersHorizontal className="h-6 w-6" />} title="Choose a goal before modeling" description="Scenario Lab is goal-scoped and does not create a free-standing financial projection." action={<a href="/goals" className="btn-primary inline-flex px-4 py-2 text-sm">Open Goals</a>} /> : <div className="space-y-6"><div className="flex flex-wrap items-end gap-3"><Select label="Goal" value={String(activeGoalId)} onChange={(event) => setSelectedGoalId(Number(event.target.value))} options={(goals ?? []).map((goal) => ({ value: String(goal.id), label: goal.name }))} /></div>{scenarios.error && <section className="card p-5" role="alert"><h2 className="headline-sm text-primary">Scenario history unavailable</h2><p className="mt-2 text-sm text-secondary">The server did not make Scenario Lab available. No local scenario result is shown.</p></section>}{view === 'scenarios' && <><section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]"><form onSubmit={generate} className="card p-5 space-y-4"><div><h2 className="headline-sm text-primary">Create a bounded scenario</h2><p className="mt-1 text-sm text-secondary">Only monthly contribution delta, dated start/stop, and one dated outflow are supported by the server contract.</p></div><Input label="Monthly contribution change" value={delta} onChange={(event) => setDelta(event.target.value)} placeholder="Decimal string, e.g. 250.00" inputMode="decimal" /><div className="grid gap-4 sm:grid-cols-2"><Input label="Contribution start date" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /><Input label="Contribution stop date" type="date" value={stopDate} onChange={(event) => setStopDate(event.target.value)} /></div><div className="grid gap-4 sm:grid-cols-2"><Input label="One-time outflow date" type="date" value={outflowDate} onChange={(event) => setOutflowDate(event.target.value)} /><Input label="One-time outflow amount" value={outflowAmount} onChange={(event) => setOutflowAmount(event.target.value)} placeholder="Decimal string" inputMode="decimal" /></div><p className="text-xs text-secondary">No probability, tax, optimization, execution, or client-side projection is available here.</p><Button type="submit" variant="primary" disabled={mutating || (!delta && !startDate && !stopDate && !outflowDate && !outflowAmount)} icon={mutating ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : undefined}>{mutating ? 'Requesting server result…' : 'Generate scenario'}</Button></form></section>{mutationError && <p className="text-sm text-danger" role="alert">{mutationError}</p>}{result && <ScenarioResult result={result} />}</>}{view === 'comparisons' && <section className="space-y-4"><div className="card p-5"><div className="flex items-center gap-2"><GitCompareArrows className="h-5 w-5 text-primary-600" aria-hidden="true" /><h2 className="headline-sm text-primary">Bounded comparison</h2></div><p className="mt-2 text-sm text-secondary">Compare up to three compatible saved scenarios against the same immutable baseline. Results come from the server.</p><Button type="button" variant="primary" className="mt-4" onClick={compare} disabled={mutating}>Compare saved scenarios</Button></div>{comparison && <pre className="card overflow-x-auto p-5 text-xs text-secondary" aria-label="Scenario comparison result">{JSON.stringify(comparison, null, 2)}</pre>}</section>}{view === 'archive' && <section className="card p-5"><div className="flex items-center gap-2"><Archive className="h-5 w-5 text-primary-600" aria-hidden="true" /><h2 className="headline-sm text-primary">Scenario archive</h2></div><p className="mt-1 text-sm text-secondary">Immutable server versions remain available for review. Select a saved scenario to archive its active identity without deleting its history.</p><div className="mt-4"><ScenarioList items={scenarios.data?.items ?? []} selected={selectedScenario} onSelect={setSelectedScenario} /></div>{selectedScenario && <Button type="button" variant="tertiary" className="mt-3" onClick={archive} disabled={mutating}>Archive selected scenario</Button>}</section>}</div>
  return <section data-testid="scenario-lab-page" className="space-y-6"><PageHeader title="Scenario Lab" description={`Compare explicit, goal-scoped changes against an immutable baseline for ${selectedGoal?.name ?? 'your goal'}.`} /><PageTabs tabs={tabs} activeId={view} queryKey="view" /><AnalyticalContextBar showRange={false} pageSlot={<span className="text-xs text-secondary">Server-selected Decimal-safe authority</span>} coverage={<span>Goal scoped</span>} freshness={<span>Baseline required</span>} />{content}</section>
}

export default function ScenarioLabPage() {
  return <PageLayout><AtlasFilterProvider><ScenarioLabWorkspace /></AtlasFilterProvider></PageLayout>
}
