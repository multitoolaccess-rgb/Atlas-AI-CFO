'use client'

import { useEffect, useMemo, useState, useCallback } from 'react'
import {
  Plus,
  Target,
  Pencil,
  Trash2,
  Loader2,
  Calendar,
  TrendingUp,
  Clock,
  CheckCircle2,
  AlertCircle,
  Calculator,
  ArrowRight,
  RotateCcw,
} from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'
import { AtlasFilterProvider } from '@/components/ui/AtlasFilterContext'
import FloatingTimeRangeBar from '@/components/ui/FloatingTimeRangeBar'
import ErrorBanner from '@/components/ui/ErrorBanner'
import AnimatedPageSection from '@/components/ui/AnimatedPageSection'
import { Button, Input, Modal } from '@/components/ui'
import AnimatedRadialProgress from '@/components/charts/AnimatedRadialProgress'
import TiltCard from '@/components/ui/TiltCard'
import FinancialPlans, { GOAL_PROJECTION_ANNUAL_RETURN } from '@/components/dashboard/FinancialPlans'
import LatestForecastSection from '@/components/dashboard/LatestForecastSection'
import DecisionHistorySection from '@/components/dashboard/DecisionHistorySection'
import { projectDashboardTrajectory } from '@/lib/math/projection'
import { rulesService, type Goal, type DashboardSummary } from '@/lib/api'
import { classifyErrorMessage } from '@/lib/errors'
import { formatNumber } from '@/lib/format'

type FetchResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: unknown }

export default function GoalsPage() {
  const [goals, setGoals] = useState<Goal[]>([])
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [loading, setLoading] = useState(true)
  // ``error`` is the LOCAL goals-list failure (top-of-page banner).
  // ``summaryError`` is the FORWARDED dashboard failure (inline in
  // FinancialPlans so the configured goals list still renders).
  // Phase F2 #2 hard-fix: the two calls run independently so a
  // Finlynq 502/401 on dashboard does not abort the goals list.
  const [error, setError] = useState<string | null>(null)
  const [summaryError, setSummaryError] = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)

  // Create form state (managed locally — no Modal so a click on the
  // primary CTA directly reveals the form inline; matches the
  // /accounts experience where the user expects a single-page flow).
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [createName, setCreateName] = useState('')
  const [createTarget, setCreateTarget] = useState('')
  const [createHorizon, setCreateHorizon] = useState('')
  const [createTargetDate, setCreateTargetDate] = useState('')
  const [createPriority, setCreatePriority] = useState('0')
  const [createNotes, setCreateNotes] = useState('')
  const [createSubmitting, setCreateSubmitting] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  // Edit modal state (mirror Add form, pre-populated).
  const [editing, setEditing] = useState<Goal | null>(null)
  const [editName, setEditName] = useState('')
  const [editTarget, setEditTarget] = useState('')
  const [editHorizon, setEditHorizon] = useState('')
  const [editTargetDate, setEditTargetDate] = useState('')
  const [editPriority, setEditPriority] = useState('0')
  const [editNotes, setEditNotes] = useState('')
  const [editSubmitting, setEditSubmitting] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)

  // Delete confirmation modal state (soft-archive).
  const [confirmingDelete, setConfirmingDelete] = useState<Goal | null>(null)
  const [deleteSubmitting, setDeleteSubmitting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      setSummaryError(null)
      // Wrap each promise so a single failure does not abort the
      // other. The previous ``Promise.all([...])`` shape rejected
      // the outer try/catch on the dashboard forwarder's 502,
      // which surfaced as "Couldn't load goals: <upstream raw
      // detail>" — misleading the user into thinking LIST GOALS
      // failed when only the projection call did.
      const safeList = rulesService.listGoals().then(
        (data): FetchResult<Goal[]> => ({ ok: true, data }),
        (err): FetchResult<Goal[]> => ({ ok: false, error: err }),
      )
      const safeSummary = rulesService.getDashboardSummary().then(
        (data): FetchResult<DashboardSummary> => ({ ok: true, data }),
        (err): FetchResult<DashboardSummary> => ({ ok: false, error: err }),
      )
      const [goalsRes, summaryRes] = await Promise.all([
        safeList,
        safeSummary,
      ])
      if (cancelled) return
      if (goalsRes.ok) {
        setGoals(goalsRes.data)
        setError(null)
      } else {
        setError(classifyErrorMessage(goalsRes.error))
      }
      if (summaryRes.ok) {
        setSummary(summaryRes.data)
        setSummaryError(null)
      } else {
        setSummaryError(classifyErrorMessage(summaryRes.error))
      }
      setLoading(false)
    }
    load()
    return () => {
      cancelled = true
    }
  }, [retryCount])

  const resetCreateForm = () => {
    setCreateName('')
    setCreateTarget('')
    setCreateHorizon('')
    setCreateTargetDate('')
    setCreatePriority('0')
    setCreateNotes('')
    setCreateError(null)
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreateSubmitting(true)
    setCreateError(null)
    try {
      const target = Number(createTarget)
      const horizon = createHorizon === '' ? null : Number(createHorizon)
      const priority = Number(createPriority) || 0
      if (!createName.trim()) {
        setCreateError('Goal name is required.')
        setCreateSubmitting(false)
        return
      }
      if (!Number.isFinite(target) || target <= 0) {
        setCreateError('Target amount must be a positive number.')
        setCreateSubmitting(false)
        return
      }
      const created = await rulesService.createGoal({
        name: createName.trim(),
        target_amount: target,
        target_date: createTargetDate || null,
        horizon_years: horizon,
        priority,
        notes: createNotes || null,
      })
      setGoals((prev) => [...prev, created])
      // Refresh the dashboard summary so ``FinancialPlans`` (which reads
      // summary.user_goals) reflects the new goal without a hard reload.
      try {
        const s = await rulesService.getDashboardSummary()
        setSummary(s)
      } catch {
        /* non-fatal — GoalsPage list already reflects the new row */
      }
      resetCreateForm()
      setShowCreateForm(false)
    } catch (err: any) {
      setCreateError(classifyErrorMessage(err))
    } finally {
      setCreateSubmitting(false)
    }
  }

  // Edit handlers --------------------------------------------------
  const startEdit = (g: Goal) => {
    setEditing(g)
    setEditName(g.name)
    setEditTarget(String(g.target_amount))
    setEditHorizon(g.horizon_years != null ? String(g.horizon_years) : '')
    setEditTargetDate(g.target_date ?? '')
    setEditPriority(String(g.priority ?? 0))
    setEditNotes(g.notes ?? '')
    setEditError(null)
  }

  const cancelEdit = () => {
    if (editSubmitting) return
    setEditing(null)
    setEditError(null)
  }

  const submitEdit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editing) return
    setEditSubmitting(true)
    setEditError(null)
    try {
      const target = Number(editTarget)
      const horizon = editHorizon === '' ? null : Number(editHorizon)
      const priority = Number(editPriority) || 0
      if (!editName.trim()) {
        setEditError('Goal name is required.')
        setEditSubmitting(false)
        return
      }
      if (!Number.isFinite(target) || target <= 0) {
        setEditError('Target amount must be a positive number.')
        setEditSubmitting(false)
        return
      }
      const updated = await rulesService.updateGoal(editing.id, {
        name: editName.trim(),
        target_amount: target,
        target_date: editTargetDate || null,
        horizon_years: horizon,
        priority,
        notes: editNotes || null,
      })
      setGoals((prev) => prev.map((g) => (g.id === updated.id ? updated : g)))
      // Re-pull the dashboard summary so ``FinancialPlans`` re-renders
      // with the new goal label/amount.
      try {
        const s = await rulesService.getDashboardSummary()
        setSummary(s)
      } catch {
        /* non-fatal */
      }
      setEditing(null)
    } catch (err: any) {
      setEditError(classifyErrorMessage(err))
    } finally {
      setEditSubmitting(false)
    }
  }

  // Delete handlers ------------------------------------------------
  const startDelete = (g: Goal) => {
    setConfirmingDelete(g)
    setDeleteError(null)
  }

  const cancelDelete = () => {
    if (deleteSubmitting) return
    setConfirmingDelete(null)
    setDeleteError(null)
  }

  const submitDelete = async () => {
    if (!confirmingDelete) return
    setDeleteSubmitting(true)
    setDeleteError(null)
    try {
      await rulesService.deleteGoal(confirmingDelete.id)
      // Soft-archive flips is_archived=True; listGoals filters those out.
      setRetryCount((c) => c + 1)
      // Also refresh the dashboard summary so ``FinancialPlans`` no
      // longer renders the archived goal.
      try {
        const s = await rulesService.getDashboardSummary()
        setSummary(s)
      } catch {
        /* non-fatal */
      }
      setConfirmingDelete(null)
    } catch (err: any) {
      setDeleteError(classifyErrorMessage(err))
    } finally {
      setDeleteSubmitting(false)
    }
  }

  const sortedGoals = useMemo(
    () =>
      [...goals].sort(
        (a, b) =>
          (b.priority ?? 0) - (a.priority ?? 0) ||
          (a.created_at ?? '').localeCompare(b.created_at ?? ''),
      ),
    [goals],
  )

  // What-if calculator state — null means "use actual monthlyNet"
  const [whatIfEnabled, setWhatIfEnabled] = useState(false)
  const [whatIfContribution, setWhatIfContribution] = useState(0)

  const handleWhatIfToggle = useCallback(() => {
    if (!whatIfEnabled && summary) {
      // Initialize slider to current monthlyNet
      const actualNet = (summary.total_income_month ?? 0) - (summary.total_expenses_month ?? 0)
      setWhatIfContribution(Math.max(0, Math.round(actualNet / 100) * 100))
    }
    setWhatIfEnabled((prev) => !prev)
  }, [whatIfEnabled, summary])

  const handleWhatIfReset = useCallback(() => {
    setWhatIfEnabled(false)
    setWhatIfContribution(0)
  }, [])

  return (
    <PageLayout>
      <AtlasFilterProvider>
      <AnimatedPageSection>
      <div className="flex items-end justify-between mb-6">
        <div>
          <h1 className="headline-xl text-primary mb-2">Financial Goals</h1>
          <p className="body-md text-secondary">
            Set long-term targets and watch your projection in real time.
            Each goal drives a tile in the Financial Plans section below.
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => setShowCreateForm((s) => !s)}
          icon={<Plus className="w-4 h-4" aria-hidden="true" />}
        >
          {showCreateForm ? 'Cancel' : 'Add Goal'}
        </Button>
      </div>

      {/* Floating bar — URL-synced via ?range=… (page-default YTD).
          Visual-only today: goals are not range-aware yet. */}
      <FloatingTimeRangeBar />

      {error && (
        // variant="warning" (amber) — matches Overview / Portfolio /
        // Activity / Settings / Accounts. The summary-error path
        // (FinancialPlans inline banner) was already amber.
        <ErrorBanner
          title="Couldn't load goals:"
          message={error}
          variant="warning"
          onRetry={() => setRetryCount((c) => c + 1)}
        />
      )}

      {showCreateForm && (
        <form
          onSubmit={handleCreate}
          className="card p-6 mb-6"
          data-testid="create-goal-form"
        >
          <h2 className="headline-md text-primary mb-4">New goal</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Goal name"
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
              required
              placeholder="e.g. Retirement by 55"
            />
            <Input
              label="Target amount"
              type="number"
              step="0.01"
              value={createTarget}
              onChange={(e) => setCreateTarget(e.target.value)}
              required
              placeholder="15000000"
            />
            <Input
              label="Horizon (years)"
              type="number"
              min="0"
              max="120"
              value={createHorizon}
              onChange={(e) => setCreateHorizon(e.target.value)}
              hint="OR set a target date"
            />
            <Input
              label="Target date"
              type="date"
              value={createTargetDate}
              onChange={(e) => setCreateTargetDate(e.target.value)}
              hint="OR set a horizon in years"
            />
            <Input
              label="Priority"
              type="number"
              value={createPriority}
              onChange={(e) => setCreatePriority(e.target.value)}
              hint="Higher = shown first"
            />
            <Input
              label="Notes"
              value={createNotes}
              onChange={(e) => setCreateNotes(e.target.value)}
              placeholder="Optional"
            />
          </div>
          {createError && (
            <p className="text-sm text-danger mt-3" role="alert">
              {createError}
            </p>
          )}
          <div className="mt-4 flex gap-2">
            <Button type="submit" variant="primary" disabled={createSubmitting}>
              {createSubmitting ? 'Creating…' : 'Create goal'}
            </Button>
            <Button
              type="button"
              variant="tertiary"
              onClick={() => {
                resetCreateForm()
                setShowCreateForm(false)
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}

      {/* Goal grid ---------------------------------------------------- */}
      {loading ? (
        <p className="text-sm text-secondary" data-testid="goals-loading">
          Loading goals…
        </p>
      ) : sortedGoals.length === 0 ? (
        <div className="card p-8 text-center" data-testid="goals-empty">
          <Target
            className="w-8 h-8 text-primary mx-auto mb-2"
            aria-hidden="true"
          />
          <p className="text-secondary">
            No goals yet. Click <strong className="text-primary">Add Goal</strong>{' '}
            to set one (e.g. &quot;Retirement&quot; or &quot;Emergency fund&quot;).
            The current $15M target from your onboarding profile will appear
            automatically if no goals exist.
          </p>
        </div>
      ) : (
        <div
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
          data-testid="goals-grid"
        >
          {sortedGoals.map((g) => (
            <TiltCard
              key={g.id}
              className="h-full"
            >
              <div
                className="card p-6 h-full"
                role="article"
                data-testid={`goal-card-${g.id}`}
              >
                <div className="flex items-start justify-between mb-1 gap-2">
                <h3 className="text-sm font-bold uppercase tracking-wider text-primary truncate">
                  {g.name}
                </h3>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <button
                    type="button"
                    onClick={() => startEdit(g)}
                    aria-label={`Edit ${g.name}`}
                    title="Edit"
                    data-testid={`goal-edit-${g.id}`}
                    className="
                      inline-flex items-center justify-center
                      w-8 h-8 rounded-[var(--radius-sm)]
                      text-[var(--text-tertiary)]
                      hover:text-[var(--text-primary)]
                      hover:bg-[var(--bg-tertiary)]
                      focus-visible:outline-2 focus-visible:outline-offset-2
                      focus-visible:outline-[var(--primary-500)]
                      transition-colors duration-[var(--duration-fast)]
                    "
                  >
                    <Pencil className="w-4 h-4" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => startDelete(g)}
                    aria-label={`Archive ${g.name}`}
                    title="Archive"
                    data-testid={`goal-delete-${g.id}`}
                    className="
                      inline-flex items-center justify-center
                      w-8 h-8 rounded-[var(--radius-sm)]
                      text-[var(--text-tertiary)]
                      hover:text-[var(--danger-600)]
                      hover:bg-[var(--danger-50)]
                      focus-visible:outline-2 focus-visible:outline-offset-2
                      focus-visible:outline-[var(--danger-500)]
                      transition-colors duration-[var(--duration-fast)]
                    "
                  >
                    <Trash2 className="w-4 h-4" aria-hidden="true" />
                  </button>
                </div>
              </div>

              <div className="flex items-center gap-2 text-xs text-secondary mt-1">
                {g.target_date ? (
                  <>
                    <Calendar className="w-3.5 h-3.5" aria-hidden="true" />
                    <span>by {g.target_date}</span>
                  </>
                ) : g.horizon_years != null ? (
                  <>
                    <TrendingUp
                      className="w-3.5 h-3.5"
                      aria-hidden="true"
                    />
                    <span>{g.horizon_years}-year horizon</span>
                  </>
                ) : (
                  <span>No deadline set</span>
                )}
                {g.priority > 0 && (
                  <span className="ml-auto text-[10px] font-bold uppercase tracking-wider text-primary bg-[var(--bg-tertiary)] px-2 py-0.5 rounded">
                    Priority {g.priority}
                  </span>
                )}
              </div>

              <p className="numeric-lg text-primary mt-3">
                {formatNumber(g.target_amount)}
              </p>
              {g.notes && (
                <p className="text-xs text-tertiary mt-2 italic line-clamp-2">
                  {g.notes}
                </p>
              )}

              {/* Radial progress — shows current funding % toward goal target */}
              {summary && (
                <div className="mt-3 flex items-center gap-3">
                  {(() => {
                    const netWorth = summary.total_balance ?? 0
                    const progressPct = Math.min(100, (netWorth / Math.max(1, g.target_amount)) * 100)
                    const color = progressPct >= 85 ? 'var(--success-500)' : progressPct >= 50 ? 'var(--warning-500)' : 'var(--danger-500)'
                    return (
                      <AnimatedRadialProgress
                        percentage={progressPct}
                        size={56}
                        strokeWidth={6}
                        color={color}
                        label={<span className="text-[10px] font-bold">{Math.round(progressPct)}%</span>}
                      />
                    )
                  })()}
                  <p className="text-[0.65rem] text-on-surface-variant">
                    {formatNumber(summary.total_balance ?? 0)} of {formatNumber(g.target_amount)} funded
                  </p>
                </div>
              )}
              </div>
            </TiltCard>
          ))}
        </div>
      )}

      {/* Phase 2 Slice 2 — Latest persisted forecast + deterministic
          recommendation + append-only decision journal. Per
          `docs/10-roadmap/PHASE2_VERTICAL_SLICE_PLAN.md` §10 PR 2:
          bounded extension of the existing goals page. Default-off
          (``atlas_forecast_read_api_enabled``) surfaces a stable
          sanitized 503 inline — never renders stale legacy data.
          Existing list / create / edit / archive / what-if logic
          below is NOT modified. */}
      <LatestForecastSection
        goals={sortedGoals.map((g) => ({
          id: g.id,
          name: g.name,
          target_amount: String(g.target_amount),
        }))}
      />

      <DecisionHistorySection
        goals={sortedGoals.map((g) => ({ id: g.id, name: g.name }))}
      />

      {/* Funding Plan — projected completion dates for each goal + what-if calculator */}
      {summary && sortedGoals.length > 0 && (() => {
        const netWorth = summary.total_balance ?? 0
        const monthlyNet = (summary.total_income_month ?? 0) - (summary.total_expenses_month ?? 0)
        const annualReturn = GOAL_PROJECTION_ANNUAL_RETURN

        // What-if mode uses the slider value; otherwise use actual monthlyNet
        const effectiveContribution = whatIfEnabled ? whatIfContribution : monthlyNet

        // Helper: compute years-to-fund for a given monthly contribution
        const computeYears = (contribution: number, target: number): number | null => {
          if (contribution <= 0) return null
          for (let y = 1; y <= 100; y++) {
            const projected = projectDashboardTrajectory({
              netWorth,
              monthlyContribution: contribution,
              annualReturnRate: annualReturn,
              years: y,
            })
            if (projected >= target) return y
          }
          return null
        }

        // Compute projections for both actual and what-if scenarios
        const goalProjections = sortedGoals.map((goal) => {
          const actualYears = computeYears(monthlyNet, goal.target_amount)
          const whatIfYears = whatIfEnabled ? computeYears(whatIfContribution, goal.target_amount) : null
          const projectedYears = whatIfEnabled ? whatIfYears : actualYears

          const progressPct = Math.min(100, (netWorth / Math.max(1, goal.target_amount)) * 100)
          const isReached = progressPct >= 100
          const horizonYears = goal.horizon_years ?? (goal.target_date
            ? Math.max(1, Number(goal.target_date.slice(0, 4)) - new Date().getFullYear())
            : null)
          const isOnTrack = projectedYears !== null && horizonYears !== null && projectedYears <= horizonYears
          const isBehind = projectedYears !== null && horizonYears !== null && projectedYears > horizonYears

          // Delta: negative = faster, positive = slower
          const deltaYears = (whatIfEnabled && actualYears !== null && whatIfYears !== null)
            ? whatIfYears - actualYears
            : null

          return { goal, projectedYears, actualYears, whatIfYears, progressPct, isReached, horizonYears, isOnTrack, isBehind, deltaYears }
        })

        // What-if contribution delta (computed once, not per-goal)
        const whatIfDelta = whatIfEnabled ? whatIfContribution - monthlyNet : 0

        // Slider range: 0 to max(actualNet * 3, whatIfValue, 5000)
        const sliderMax = Math.max(monthlyNet * 3, whatIfContribution, 5000)
        const sliderStep = monthlyNet > 1000 ? 500 : monthlyNet > 200 ? 100 : 50

        return (
          <div className="mt-8 card p-6">
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-[var(--success-50)] flex items-center justify-center border border-[var(--success-200)]">
                  <Clock className="w-4 h-4 text-[var(--success-600)]" aria-hidden="true" />
                </div>
                <div>
                  <h2 className="headline-md text-primary">Funding Plan</h2>
                  <p className="text-xs text-on-surface-variant">
                    Projected timelines at{' '}
                    <span className={whatIfEnabled ? 'font-bold text-primary-600' : ''}>
                      {formatNumber(effectiveContribution)}/mo
                    </span>
                    {whatIfEnabled && (
                      <span className="text-on-surface-variant">
                        {' '}(actual: {formatNumber(monthlyNet)}/mo)
                      </span>
                    )}
                    {', '}{(annualReturn * 100).toFixed(0)}% annual return
                  </p>
                </div>
              </div>

              {/* What-if toggle */}
              <button
                type="button"
                onClick={handleWhatIfToggle}
                data-testid="what-if-toggle"
                className={`
                  inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold
                  transition-all duration-200
                  ${whatIfEnabled
                    ? 'bg-primary-100 text-primary-700 ring-2 ring-primary-300'
                    : 'bg-surface-container text-on-surface-variant hover:bg-surface-container-high'
                  }
                `}
              >
                <Calculator className="w-3.5 h-3.5" aria-hidden="true" />
                What if?
              </button>
            </div>

            {/* What-if slider panel — only visible when enabled */}
            {whatIfEnabled && (
              <div
                className="mb-5 p-4 rounded-lg bg-primary-50/50 border border-primary-200/50"
                data-testid="what-if-panel"
              >
                <div className="flex items-center justify-between mb-3">
                  <label className="text-xs font-bold uppercase tracking-wider text-primary-700">
                    Adjust monthly contribution
                  </label>
                  <button
                    type="button"
                    onClick={handleWhatIfReset}
                    className="inline-flex items-center gap-1 text-[0.65rem] font-medium text-on-surface-variant hover:text-primary-600 transition-colors"
                    data-testid="what-if-reset"
                  >
                    <RotateCcw className="w-3 h-3" />
                    Reset
                  </button>
                </div>

                <div className="flex items-center gap-4">
                  {/* Vertical stepped dial — replaces horizontal slider */}
                  <div className="flex flex-col items-center gap-1">
                    <div
                      className="relative w-8 h-40 rounded-full bg-gradient-to-b from-primary-200 to-primary-100 overflow-hidden shadow-inner focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-400"
                      role="slider"
                      aria-label="Adjust monthly contribution"
                      aria-valuemin={0}
                      aria-valuemax={sliderMax}
                      aria-valuenow={whatIfContribution}
                      aria-valuetext={`${formatNumber(whatIfContribution)} monthly contribution`}
                      tabIndex={0}
                      data-testid="what-if-slider"
                      onKeyDown={(e) => {
                        if (e.key === 'ArrowUp' || e.key === 'ArrowRight') {
                          setWhatIfContribution((v) => Math.min(sliderMax, v + sliderStep))
                        } else if (e.key === 'ArrowDown' || e.key === 'ArrowLeft') {
                          setWhatIfContribution((v) => Math.max(0, v - sliderStep))
                        } else if (e.key === 'PageUp') {
                          e.preventDefault()
                          setWhatIfContribution((v) => Math.min(sliderMax, v + sliderStep * 5))
                        } else if (e.key === 'PageDown') {
                          e.preventDefault()
                          setWhatIfContribution((v) => Math.max(0, v - sliderStep * 5))
                        } else if (e.key === 'Home') {
                          e.preventDefault()
                          setWhatIfContribution(0)
                        } else if (e.key === 'End') {
                          e.preventDefault()
                          setWhatIfContribution(sliderMax)
                        }
                      }}
                      onClick={(e) => {
                        const rect = e.currentTarget.getBoundingClientRect()
                        const pct = 1 - (e.clientY - rect.top) / rect.height
                        const raw = Math.round(Math.max(0, Math.min(sliderMax, pct * sliderMax)) / sliderStep) * sliderStep
                        setWhatIfContribution(Math.max(0, Math.min(sliderMax, raw)))
                      }}
                      onPointerDown={(e) => {
                        const slider = e.currentTarget
                        try {
                          slider.setPointerCapture(e.pointerId)
                        } catch {
                          /* ignore if pointer capture unsupported */
                        }
                        const updateFromPointer = (clientY: number) => {
                          const rect = slider.getBoundingClientRect()
                          const pct = 1 - (clientY - rect.top) / rect.height
                          const raw = Math.round(Math.max(0, Math.min(sliderMax, pct * sliderMax)) / sliderStep) * sliderStep
                          setWhatIfContribution(Math.max(0, Math.min(sliderMax, raw)))
                        }
                        updateFromPointer(e.clientY)
                        const onMove = (ev: PointerEvent) => updateFromPointer(ev.clientY)
                        const onUp = () => {
                          slider.removeEventListener('pointermove', onMove)
                          slider.removeEventListener('pointerup', onUp)
                        }
                        slider.addEventListener('pointermove', onMove)
                        slider.addEventListener('pointerup', onUp)
                      }}
                    >
                      <div
                        className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-primary-500 to-primary-400 transition-all duration-300"
                        style={{ height: `${sliderMax > 0 ? (whatIfContribution / sliderMax) * 100 : 0}%` }}
                      />
                      <div
                        className="absolute left-1/2 -translate-x-1/2 w-5 h-5 rounded-full bg-white shadow-md border-2 border-primary-500 transition-all duration-300"
                        style={{ bottom: `calc(${sliderMax > 0 ? (whatIfContribution / sliderMax) * 100 : 0}% - 10px)` }}
                      />
                    </div>
                    <span className="text-[10px] text-on-surface-variant">{formatNumber(sliderMax)}</span>
                  </div>

                  {/* Number input */}
                  <div className="relative">
                    <input
                      type="number"
                      min={0}
                      max={sliderMax}
                      step={sliderStep}
                      value={whatIfContribution || ''}
                      onChange={(e) => setWhatIfContribution(Math.max(0, Number(e.target.value) || 0))}
                      className="w-28 pl-3 pr-2 py-1.5 text-sm font-bold tabular-nums text-right bg-white border border-primary-300 rounded-lg focus:ring-2 focus:ring-primary-400 focus:border-primary-400 outline-none"
                      data-testid="what-if-input"
                    />
                  </div>
                </div>

                {/* Quick presets */}
                <div className="flex gap-2 mt-3">
                  {[0.5, 1, 1.5, 2].map((mult) => {
                    const val = Math.round(monthlyNet * mult / 100) * 100
                    const isActive = whatIfContribution === val
                    return (
                      <button
                        key={mult}
                        type="button"
                        onClick={() => setWhatIfContribution(val)}
                        data-testid={`what-if-preset-${mult}x`}
                        className={`
                          px-2.5 py-1 rounded-md text-[0.65rem] font-semibold tabular-nums
                          transition-all duration-150
                          ${isActive
                            ? 'bg-primary-500 text-white shadow-sm'
                            : 'bg-white text-on-surface-variant border border-outline-variant/30 hover:border-primary-300'
                          }
                        `}
                      >
                        {mult}× ({formatNumber(val)})
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            <div className="space-y-3">
              {goalProjections.map(({ goal, projectedYears, actualYears, whatIfYears, isReached, isOnTrack, isBehind, horizonYears, deltaYears }) => (
                <div
                  key={`plan-${goal.id}`}
                  className="flex items-center gap-4 p-4 rounded-lg border border-outline-variant/20 hover:border-outline-variant/40 transition-colors"
                >
                  {/* Status icon */}
                  <div className="shrink-0">
                    {isReached ? (
                      <CheckCircle2 className="w-5 h-5 text-success-500" />
                    ) : isOnTrack ? (
                      <TrendingUp className="w-5 h-5 text-primary-500" />
                    ) : isBehind ? (
                      <AlertCircle className="w-5 h-5 text-warning-500" />
                    ) : (
                      <Clock className="w-5 h-5 text-on-surface-variant" />
                    )}
                  </div>

                  {/* Goal info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-on-surface truncate">{goal.name}</p>
                    <p className="text-xs text-on-surface-variant">
                      {formatNumber(goal.target_amount)} target
                      {horizonYears ? ` · ${horizonYears}y horizon` : ''}
                    </p>
                  </div>

                  {/* Projected timeline */}
                  <div className="text-right shrink-0">
                    {isReached ? (
                      <>
                        <p className="text-sm font-bold text-success-600">Funded!</p>
                        <p className="text-[0.65rem] text-on-surface-variant">
                          {formatNumber(netWorth - goal.target_amount)} over target
                        </p>
                      </>
                    ) : projectedYears !== null ? (
                      <>
                        <p className={`text-sm font-bold ${isOnTrack ? 'text-primary-600' : 'text-warning-600'}`}>
                          ~{projectedYears}y to fund
                        </p>
                        <p className="text-[0.65rem] text-on-surface-variant">
                          {isOnTrack ? 'On track' : `${projectedYears - (horizonYears ?? 0)}y past horizon`}
                        </p>
                      </>
                    ) : (
                      <>
                        <p className="text-sm font-bold text-on-surface-variant">N/A</p>
                        <p className="text-[0.65rem] text-on-surface-variant">
                          {effectiveContribution <= 0 ? 'Negative cash flow' : 'Increase contributions'}
                        </p>
                      </>
                    )}
                  </div>

                  {/* What-if delta badge — shows comparison when active */}
                  {whatIfEnabled && deltaYears !== null && !isReached && (
                    <div className="shrink-0" data-testid={`what-if-delta-${goal.id}`}>
                      {deltaYears < 0 ? (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[0.65rem] font-bold bg-success-100 text-success-700">
                          <ArrowRight className="w-3 h-3 rotate-[-45deg]" />
                          {Math.abs(deltaYears)}y faster
                        </span>
                      ) : deltaYears > 0 ? (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[0.65rem] font-bold bg-warning-100 text-warning-700">
                          <ArrowRight className="w-3 h-3 rotate-45" />
                          {deltaYears}y slower
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[0.65rem] font-bold bg-surface-container text-on-surface-variant">
                          Same
                        </span>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* What-if insight banner */}
            {whatIfEnabled && (() => {
              const fasterGoals = goalProjections.filter((p) => p.deltaYears !== null && p.deltaYears < 0 && !p.isReached)
              const slowerGoals = goalProjections.filter((p) => p.deltaYears !== null && p.deltaYears > 0 && !p.isReached)
              const avgDelta = fasterGoals.length > 0
                ? Math.round(fasterGoals.reduce((s, p) => s + (p.deltaYears ?? 0), 0) / fasterGoals.length)
                : 0

              if (whatIfDelta === 0) return null

              return (
                <div className="mt-4 p-3 rounded-lg bg-info-50 border border-info-200" data-testid="what-if-insight">
                  <p className="text-xs text-info-700">
                    {whatIfDelta > 0 ? (
                      <>
                        Adding <strong>{formatNumber(whatIfDelta)}/mo</strong>{' '}
                        {fasterGoals.length > 0 && (
                          <>reaches {fasterGoals.length === 1 ? fasterGoals[0].goal.name : `${fasterGoals.length} goals`}{' '}
                          <strong>{Math.abs(avgDelta)}y sooner</strong>{fasterGoals.length > 1 ? ' on average' : ''}{' '}</>
                        )}
                      </>
                    ) : slowerGoals.length > 0 ? (
                      <>
                        Reducing by <strong>{formatNumber(Math.abs(whatIfDelta))}/mo</strong>{' '}
                        delays {slowerGoals.length === 1 ? slowerGoals[0].goal.name : `${slowerGoals.length} goals`}{' '}
                        by up to{' '}
                        <strong>{Math.max(...slowerGoals.map((p) => p.deltaYears ?? 0))}y</strong>.
                      </>
                    ) : (
                      <>Reducing by <strong>{formatNumber(Math.abs(whatIfDelta))}/mo</strong> has no impact on unfunded goals.</>
                    )}
                  </p>
                </div>
              )
            })()}
          </div>
        )
      })()}

      {/* Projection engine (Phase 9): renders one tile per goal using
          summary.user_goals instead of the old hardcoded $15M constant.
          Pass ``summaryError`` so a downstream 502 on the dashboard
          forwarder renders an inline warning INSIDE this section —
          the configured goals list above is unaffected because the
          local /api/goals/ endpoint doesn't depend on Finlynq. */}
      <FinancialPlans
        summary={summary}
        loading={loading}
        error={summaryError}
        onRetry={() => setRetryCount((c) => c + 1)}
      />

      {/* Edit modal (mirrors the Add form, pre-populated). */}
      <Modal
        open={editing !== null}
        onClose={cancelEdit}
        title={editing ? `Edit ${editing.name}` : 'Edit goal'}
        size="md"
        footer={
          <>
            <Button
              variant="tertiary"
              onClick={cancelEdit}
              disabled={editSubmitting}
            >
              Cancel
            </Button>
            <button
              type="submit"
              form="edit-goal-form"
              disabled={editSubmitting}
              data-testid="edit-goal-submit"
              className="
                inline-flex items-center justify-center gap-2
                px-4 py-2 rounded-lg font-medium
                bg-[var(--primary-500)] text-[var(--text-on-brand)]
                hover:bg-[var(--primary-600)] active:bg-[var(--primary-700)]
                disabled:bg-[var(--slate-400)]
                transition-all duration-150
                focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--primary-500)]
                disabled:cursor-not-allowed
              "
            >
              {editSubmitting && (
                <Loader2
                  className="w-4 h-4 animate-spin"
                  aria-hidden="true"
                />
              )}
              {editSubmitting ? 'Saving…' : 'Save changes'}
            </button>
          </>
        }
      >
        <form
          id="edit-goal-form"
          onSubmit={submitEdit}
          className="space-y-4"
          data-testid="edit-goal-form"
        >
          <Input
            label="Goal name"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            required
            placeholder="e.g. Retirement by 55"
          />
          <Input
            label="Target amount"
            type="number"
            step="0.01"
            value={editTarget}
            onChange={(e) => setEditTarget(e.target.value)}
            required
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Horizon (years)"
              type="number"
              min="0"
              max="120"
              value={editHorizon}
              onChange={(e) => setEditHorizon(e.target.value)}
            />
            <Input
              label="Target date"
              type="date"
              value={editTargetDate}
              onChange={(e) => setEditTargetDate(e.target.value)}
            />
          </div>
          <Input
            label="Priority"
            type="number"
            value={editPriority}
            onChange={(e) => setEditPriority(e.target.value)}
            hint="Higher = shown first"
          />
          <Input
            label="Notes"
            value={editNotes}
            onChange={(e) => setEditNotes(e.target.value)}
            placeholder="Optional"
          />
          {editError && (
            <p
              className="text-sm text-danger mt-3"
              role="alert"
              data-testid="edit-goal-error"
            >
              {editError}
            </p>
          )}
        </form>
      </Modal>

      {/* Archive confirmation modal (soft-delete via DELETE /api/goals/{id}). */}
      <Modal
        open={confirmingDelete !== null}
        onClose={cancelDelete}
        title="Archive goal?"
        size="sm"
        footer={
          <>
            <Button
              variant="tertiary"
              onClick={cancelDelete}
              disabled={deleteSubmitting}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={submitDelete}
              disabled={deleteSubmitting}
              icon={
                deleteSubmitting ? (
                  <Loader2
                    className="w-4 h-4 animate-spin"
                    aria-hidden="true"
                  />
                ) : (
                  <Trash2 className="w-4 h-4" aria-hidden="true" />
                )
              }
            >
              {deleteSubmitting ? 'Archiving…' : 'Archive goal'}
            </Button>
          </>
        }
      >
        {confirmingDelete && (
          <div className="space-y-3">
            <p className="body-md text-secondary">
              This will archive{' '}
              <strong className="text-primary">
                {confirmingDelete.name}
              </strong>
              . The goal will stop appearing on your dashboard and on this
              page, but future renderers that pin it by id can still resolve
              its historical state. You can un-archive it later via the API.
            </p>
            {deleteError && (
              <p
                className="text-sm text-danger mt-3"
                role="alert"
                data-testid="delete-goal-error"
              >
                {deleteError}
              </p>
            )}
          </div>
        )}
      </Modal>
      </AnimatedPageSection>
      </AtlasFilterProvider>
    </PageLayout>
  )
}
