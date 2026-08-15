'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Archive, GitCompareArrows, SlidersHorizontal } from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import PageTabs from '@/components/ui/PageTabs'
import AnalyticalContextBar from '@/components/ui/AnalyticalContextBar'
import { AtlasFilterProvider } from '@/components/ui/AtlasFilterContext'
import EmptyState from '@/components/ui/EmptyState'
import { Select } from '@/components/ui'
import { useCachedFetch, cacheInvalidate } from '@/lib/cache'
import { rulesService, type Goal } from '@/lib/api'
import { archiveScenario, compareScenarios, generateScenario, listScenarios, readScenario, readScenarioError, type ScenarioComparisonSet, type ScenarioEnvelope, type ScenarioInput } from '@/lib/api_scenarios'
import ScenarioReadiness, { type ScenarioAvailability } from '@/components/scenario-lab/ScenarioReadiness'
import ScenarioBuilder from '@/components/scenario-lab/ScenarioBuilder'
import ScenarioResult from '@/components/scenario-lab/ScenarioResult'
import ScenarioComparisonWorkspace from '@/components/scenario-lab/ScenarioComparisonWorkspace'
import ScenarioHistory from '@/components/scenario-lab/ScenarioHistory'

const tabs = [{ id: 'scenarios', label: 'Scenarios' }, { id: 'comparisons', label: 'Comparisons' }, { id: 'archive', label: 'Archive' }] as const
type ScenarioView = (typeof tabs)[number]['id']

function newIntentKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  throw new Error('A secure browser idempotency key is required for this mutation.')
}

function withQuery(search: string, updates: Record<string, string | null>): string {
  const params = new URLSearchParams(search)
  Object.entries(updates).forEach(([key, value]) => value === null ? params.delete(key) : params.set(key, value))
  const serialized = params.toString()
  return serialized ? `?${serialized}` : ''
}

function ScenarioError({ state }: { state: ReturnType<typeof readScenarioError> | null }) {
  if (!state) return null
  return <section className="rounded-lg border border-warning-200 bg-warning-50 p-4 text-sm text-warning-900" role="alert"><p className="font-semibold">{state.message}</p><p className="mt-1">{state.recovery}</p></section>
}

function ScenarioLabWorkspace() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const search = searchParams.toString()
  const requestedView = searchParams.get('view')
  const view: ScenarioView = tabs.some((tab) => tab.id === requestedView) ? requestedView as ScenarioView : 'scenarios'
  const goalQuery = searchParams.get('goal')
  const scenarioQuery = searchParams.get('scenario')
  const comparisonQuery = searchParams.get('compare')
  const [selectedGoalId, setSelectedGoalId] = useState<number | null>(goalQuery && /^\d+$/.test(goalQuery) ? Number(goalQuery) : null)
  const [generatedResult, setGeneratedResult] = useState<ScenarioEnvelope | null>(null)
  const [mutationState, setMutationState] = useState<ReturnType<typeof readScenarioError> | null>(null)
  const [mutating, setMutating] = useState(false)
  const [comparison, setComparison] = useState<ScenarioComparisonSet | null>(null)
  const [comparisonError, setComparisonError] = useState<ReturnType<typeof readScenarioError> | null>(null)
  const [comparisonSelection, setComparisonSelection] = useState<string[]>([])
  const generateIntent = useRef<{ fingerprint: string; key: string } | null>(null)
  const archiveIntents = useRef(new Map<string, string>())

  const goals = useCachedFetch<Goal[]>('scenario-goals', () => rulesService.listGoals(), [], { group: 'scenario-lab' })
  const activeGoalId = selectedGoalId ?? goals.data?.[0]?.id ?? null
  const scenarios = useCachedFetch(activeGoalId ? `scenario-list-${activeGoalId}` : 'scenario-list-disabled', () => listScenarios(activeGoalId ?? 0, true), [activeGoalId], { group: 'scenario-lab', enabled: activeGoalId !== null })
  const selectedScenario = scenarioQuery && /^[0-9a-f-]{36}$/.test(scenarioQuery) ? scenarioQuery : null
  const scenarioDetail = useCachedFetch<ScenarioEnvelope>('scenario-detail', () => readScenario(selectedScenario ?? ''), [selectedScenario], { group: 'scenario-lab', enabled: selectedScenario !== null })

  const listErrorState = scenarios.errorCause ? readScenarioError(scenarios.errorCause) : null
  const detailErrorState = scenarioDetail.errorCause ? readScenarioError(scenarioDetail.errorCause) : null
  const selectedGoal = goals.data?.find((goal) => goal.id === activeGoalId)
  const activeItems = scenarios.data?.items ?? []
  const selectedComparisonIds = useMemo(() => {
    if (comparisonSelection.length > 0) return comparisonSelection
    if (!comparisonQuery) return []
    return comparisonQuery.split(',').filter((id, index, all) => /^[0-9a-f-]{36}$/.test(id) && all.indexOf(id) === index).slice(0, 3)
  }, [comparisonQuery, comparisonSelection])
  const result = generatedResult && (!selectedScenario || generatedResult.scenario_id === selectedScenario) ? generatedResult : scenarioDetail.data
  const baseline = result ? { forecastId: result.baseline_forecast_id, version: result.baseline_version_number, currency: result.currency, freshness: `${result.comparison.source_freshness.data_age_days} / ${result.comparison.source_freshness.max_data_age_days} days` } : null

  useEffect(() => {
    if (goalQuery && /^\d+$/.test(goalQuery)) setSelectedGoalId(Number(goalQuery))
  }, [goalQuery])

  useEffect(() => {
    if (!comparisonQuery) setComparisonSelection([])
  }, [comparisonQuery])

  useEffect(() => {
    if (selectedGoalId === null && goals.data?.[0]?.id) {
      setSelectedGoalId(goals.data[0].id)
      router.replace(withQuery(search, { goal: String(goals.data[0].id) }), { scroll: false })
    }
  }, [goals.data, router, search, selectedGoalId])

  const updateGoal = (value: string) => {
    const id = Number(value)
    setSelectedGoalId(id)
    setGeneratedResult(null)
    setMutationState(null)
    router.replace(withQuery(search, { goal: value, scenario: null, compare: null }), { scroll: false })
  }

  const toggleComparison = (id: string) => {
    const next = selectedComparisonIds.includes(id) ? selectedComparisonIds.filter((value) => value !== id) : [...selectedComparisonIds, id].slice(0, 3)
    setComparisonSelection(next)
    router.replace(withQuery(search, { compare: next.length ? next.join(',') : null }), { scroll: false })
    setComparison(null)
    setComparisonError(null)
  }

  const generate = async (input: ScenarioInput) => {
    if (!activeGoalId) return
    const fingerprint = JSON.stringify(input)
    if (!generateIntent.current || generateIntent.current.fingerprint !== fingerprint) generateIntent.current = { fingerprint, key: newIntentKey() }
    setMutating(true); setMutationState(null)
    try {
      const response = await generateScenario(activeGoalId, input, generateIntent.current.key)
      generateIntent.current = null
      setGeneratedResult(response)
      router.replace(withQuery(search, { goal: String(activeGoalId), scenario: response.scenario_id }), { scroll: false })
      cacheInvalidate('scenario-lab:')
      scenarios.refetch()
    } catch (error) {
      setMutationState(readScenarioError(error))
    } finally { setMutating(false) }
  }

  const archive = async (scenarioId: string) => {
    if (!archiveIntents.current.has(scenarioId)) archiveIntents.current.set(scenarioId, newIntentKey())
    setMutating(true); setMutationState(null)
    try {
      await archiveScenario(scenarioId, archiveIntents.current.get(scenarioId)!)
      archiveIntents.current.delete(scenarioId)
      cacheInvalidate('scenario-lab:')
      scenarios.refetch()
      scenarioDetail.refetch()
    } catch (error) { setMutationState(readScenarioError(error)) }
    finally { setMutating(false) }
  }

  const compare = async () => {
    setMutating(true); setComparisonError(null)
    try { setComparison(await compareScenarios(selectedComparisonIds)) }
    catch (error) { setComparisonError(readScenarioError(error)) }
    finally { setMutating(false) }
  }

  const availability: ScenarioAvailability = goals.loading || (activeGoalId !== null && scenarios.loading && !scenarios.data) ? 'loading' : !selectedGoal ? 'no-goal' : listErrorState?.code === 'scenario_generation_unavailable' ? 'disabled' : listErrorState ? 'unavailable' : 'ready'
  const content = goals.loading ? <p className="card p-6 text-sm text-secondary" role="status">Loading goals for Scenario Lab…</p> : !selectedGoal ? <EmptyState testId="scenario-no-goal" icon={<SlidersHorizontal className="h-6 w-6" />} title="Choose a goal before modeling" description="Scenario Lab is goal-scoped and does not create a free-standing financial projection." action={<a href="/goals" className="btn-primary inline-flex px-4 py-2 text-sm">Open Goals</a>} /> : <div className="space-y-6">
    <div className="max-w-sm"><Select label="Goal" value={String(activeGoalId)} onChange={(event) => updateGoal(event.target.value)} options={(goals.data ?? []).map((goal) => ({ value: String(goal.id), label: goal.name }))} /></div>
    {listErrorState && <ScenarioError state={listErrorState} />}
    {detailErrorState && <ScenarioError state={detailErrorState} />}
    {view === 'scenarios' && <div className="space-y-6"><ScenarioBuilder disabled={availability === 'disabled' || availability === 'unavailable'} mutating={mutating} serverError={mutationState?.message} onGenerate={generate} />{mutationState && <ScenarioError state={mutationState} />}{result && <ScenarioResult result={result} />}{!result && !mutationState && <p className="rounded-lg border border-dashed border-outline-variant p-4 text-sm text-secondary">Generate a scenario to see the authoritative result. Reloading a selected scenario reads its persisted server version.</p>}</div>}
    {view === 'comparisons' && <ScenarioComparisonWorkspace items={activeItems} selectedIds={selectedComparisonIds} comparison={comparison} error={comparisonError ? `${comparisonError.message} ${comparisonError.recovery}` : null} onToggle={toggleComparison} onCompare={compare} loading={mutating} />}
    {view === 'archive' && <ScenarioHistory items={scenarios.data?.items ?? []} selectedId={selectedScenario} loading={scenarios.loading} onSelect={(id) => router.replace(withQuery(search, { scenario: id }), { scroll: false })} onArchive={archive} mutating={mutating} />}
  </div>

  return <section data-testid="scenario-lab-page" className="space-y-6"><PageHeader title="Scenario Lab" description="A focused decision workspace for explicit, goal-scoped changes against an immutable baseline." /><PageTabs tabs={tabs} activeId={view} queryKey="view" /><AnalyticalContextBar showRange={false} pageSlot={<span className="text-xs text-secondary">Rules Service · Decimal-safe authority</span>} coverage={<span>Goal scoped</span>} freshness={<span>Baseline required</span>} /><ScenarioReadiness goalName={selectedGoal?.name} availability={availability} baseline={baseline} />{content}</section>
}

export default function ScenarioLabPage() {
  return <PageLayout><AtlasFilterProvider><ScenarioLabWorkspace /></AtlasFilterProvider></PageLayout>
}
