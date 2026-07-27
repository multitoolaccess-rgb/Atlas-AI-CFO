'use client'

import { AlertTriangle, Target, TrendingUp, Wallet } from 'lucide-react'
import StatCard from '@/components/ui/StatCard'
import ProgressBar from '@/components/ui/ProgressBar'
import ErrorBanner from '@/components/ui/ErrorBanner'
import { projectDashboardTrajectory } from '@/lib/math/projection'
import type { DashboardSummary, Goal } from '@/lib/api'

/**
 * CashFlix default goal anchor (when no explicit goals are configured):
 *   $15M in 20 years — mirrored from the ``profile.target_net_worth``
 *   and ``profile.time_horizon_years`` columns on the BE via
 *   ``summary.default_goal_target`` / ``summary.default_goal_horizon_years``.
 *
 * Phase 8 — multi-goal. The component renders ONE StatCard PER goal in
 * ``summary.user_goals``; when the list is empty (fresh install) we
 * synthesize a single fallback "Default Goal" derived from the user's
 * profile anchor so the page still renders something. The user can edit
 * the anchor on Settings → Financial Goals; the dashboard re-renders the
 * next time ``getDashboardSummary`` fires.
 *
 * If the user has NOT set anything (free initial profile), we fall back
 * to the historical $15M / 20y anchor so the page never looks broken on
 * a brand-new install.
 *
 * Projection assumptions are intentionally conservative and pinned:
 *   - 7% nominal annual return (long-run equity average)
 *   - 0% real inflation in the nominal headline (user toggles in a later phase)
 *   - 5-year midpoint projection
 *
 * PMT is derived from the user's monthly net cash flow (income - expenses)
 * so the projection reacts to the actual data on the dashboard.
 */
const FALLBACK_GOAL_TARGET_USD = 15_000_000
const FALLBACK_GOAL_HORIZON_YEARS = 20
const PROJECTION_HORIZON_YEARS = 5
const ANNUAL_RETURN_RATE = 0.07

/** Shared projection constants used by both FinancialPlans and Goals page. */
export const GOAL_PROJECTION_ANNUAL_RETURN = ANNUAL_RETURN_RATE

/**
 * Pretty-print a target dollar amount as "$15M" / "$15.5M" / "$50K" / "$500".
 * The fallback goal name uses this so the synthesized tile label stays in
 * sync with the user's profile anchor (e.g. user sets $5M → "$5M Default Goal").
 */
function formatTargetCompact(amount: number): string {
  if (amount >= 1_000_000_000) {
    return `$${(amount / 1_000_000_000).toFixed(amount % 1_000_000_000 === 0 ? 0 : 1)}B`
  }
  if (amount >= 1_000_000) {
    const m = amount / 1_000_000
    return `$${m.toFixed(m === Math.floor(m) ? 0 : 1)}M`
  }
  if (amount >= 1_000) {
    return `$${Math.round(amount / 1_000)}K`
  }
  return `$${amount.toLocaleString('en-US')}`
}

interface FinancialPlansProps {
  summary: DashboardSummary | null
  loading?: boolean
  /**
   * Non-null when the upstream dashboard summary call failed but
   * we still want to render the goals list (Phase F2 #2 +
   * goals-page drilldown). Rendered as an inline warning banner
   * ABOVE the Financial Plans section so the user can still see
   * their configured goals below. Distinct from the top-of-page
   * ``Couldn't load goals:`` banner — that one fires only when
   * ``listGoals`` itself fails, not when a downstream forwarder
   * (e.g. Finlynq) misfires.
   */
  error?: string | null
  /**
   * Retry handler for the inline banner. Wired by the parent
   * (``GoalsPage``) to the same ``retryCount`` state the top-of-page
   * banner uses, so clicking either button re-triggers BOTH
   * ``listGoals`` and ``getDashboardSummary`` fetches. Optional —
   * callers that want a read-only / no-retry surface (SSR, test
   * stub, etc.) can omit it; the inline banner will render
   * without a Retry control, matching the Phase F2 #2 initial
   * shape.
   */
  onRetry?: () => void
}

/**
 * Year-only extraction (``slice(0, 4)``) avoids the tz-trap where
 * ``new Date('2045-12-31')`` parses as UTC midnight and renders as
 * 2044-12-31 in negative-offset zones. Belt-and-braces: also clamp to
 * a non-negative horizon.
 */
function resolveGoalHorizonYears(goal: Goal): number {
  if (typeof goal.horizon_years === 'number' && goal.horizon_years > 0) {
    return goal.horizon_years
  }
  if (typeof goal.target_date === 'string' && goal.target_date.length >= 4) {
    const targetYear = Number(goal.target_date.slice(0, 4))
    if (Number.isFinite(targetYear)) {
      return Math.max(1, targetYear - new Date().getFullYear())
    }
  }
  return FALLBACK_GOAL_HORIZON_YEARS
}

/**
 * Stable, name-derived React key for a (possibly synthesized) goal tile.
 * Defends against the synthesized fallback ``id=-1`` colliding with a
 * hypothetical negative-id goal in a future BE migration.
 */
function goalKey(goal: Goal): string {
  return goal.id > 0 ? `goal-${goal.id}` : `fallback-${goal.name}`
}

export default function FinancialPlans({ summary, loading, error, onRetry }: FinancialPlansProps) {
  // If the dashboard-summary forwarder failed, render an inline
  // warning banner at the top of THIS section so the goals list
  // and create/edit/archive affordances on the parent GoalsPage
  // still work — the local /api/goals/ endpoint doesn't depend on
  // Finlynq. This is the Goals-page counterpart to the top-of-page
  // "Couldn't load goals:" banner which fires only when listGoals
  // itself fails.
  if (error) {
    return (
      <section className="mb-8" aria-label="Financial plans">
        <h2 className="headline-lg text-primary mb-4">Financial Plans</h2>
        <ErrorBanner
          title="Couldn't load projections:"
          message={error}
          variant="warning"
          // Retry affordance — same shared ``retryCount`` state
          // the parent wiring sets up; clicking re-triggers BOTH
          // fetches so a recovered inbound dashboard forwarder
          // immediately repopulates the projection tiles.
          onRetry={onRetry}
        />
      </section>
    )
  }

  // Net worth: prefer summary.total_balance; treat undefined as 0.
  const netWorth = summary?.total_balance ?? 0
  // Monthly net contribution: income - expenses (treat missing as 0).
  // We DELIBERATELY do NOT floor negative values at 0 — a user with
  // negative cash flow is drawing down their principal each month, and
  // the projection engine handles negative PMT correctly (the annuity
  // term becomes negative, reducing FV). Flooring to 0 would give a
  // user spending $2k/mo MORE than they earn an optimistic projection
  // that grows from PV alone — a trust defect for a finance copilot.
  const monthlyNet =
    (summary?.total_income_month ?? 0) - (summary?.total_expenses_month ?? 0)
  const monthlyContribution = monthlyNet
  const isDepleting = monthlyNet < 0

  const fiveYear = projectDashboardTrajectory({
    netWorth,
    monthlyContribution,
    annualReturnRate: ANNUAL_RETURN_RATE,
    years: PROJECTION_HORIZON_YEARS,
  })  // Resolve the goal list — only BE-provided goals. Phase 15
  // /api/goals/ auto-seeds a "Default $15M Goal" row on first list
  // when the user has never had any goal (across archive state), so
  // the DashboardSummary returns >=1 goal for any returning user.
  // We do NOT synthesize an in-memory placeholder; if the list is
  // still empty (cold-start, before the seed has fired) the empty-
  // state copy below guides the user to the Goals page.
  const userGoals: Goal[] = summary?.user_goals ?? []
  const goalsToRender: Goal[] = userGoals





  if (loading || !summary) {
    return (
      <section className="mb-8" aria-label="Financial plans" aria-busy="true">
        <h2 className="headline-lg text-primary mb-4">Financial Plans</h2>
        <div className="bento-grid">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="col-span-12 md:col-span-4 card p-6 h-32"
              role="article"
              aria-label="Loading plan…"
            >
              <div className="skeleton h-4 w-1/3 mb-3" />
              <div className="skeleton h-6 w-2/3" />
            </div>
          ))}
        </div>
      </section>
    )
  }

  return (
    <section className="mb-8" aria-label="Financial plans" aria-live="polite">
      <div className="flex-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[var(--primary-50)] flex items-center justify-center border border-[var(--primary-200)]">
            <Target className="w-4 h-4 text-[var(--primary-600)]" aria-hidden="true" />
          </div>
          <h2 className="headline-lg text-primary">Financial Plans</h2>
        </div>
        <p className="body-sm text-on-surface-variant">
          {isDepleting ? (
            <span className="text-negative font-semibold inline-flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4" aria-hidden="true" />
              Net cash flow is negative (${Math.abs(monthlyContribution).toLocaleString('en-US')}/mo
              drawdown). Projection shows depletion of principal.
            </span>
          ) : monthlyContribution > 0 ? (
            `Assuming $${monthlyContribution.toLocaleString('en-US')}/mo contribution at ${(ANNUAL_RETURN_RATE * 100).toFixed(0)}% annual return.`
          ) : (
            `Assuming 0 monthly contribution at ${(ANNUAL_RETURN_RATE * 100).toFixed(0)}% annual return.`
          )}
        </p>
      </div>

      <div className="bento-grid">
        {/* Universal: Current Net Worth (single, non-per-goal). */}
        <StatCard
          title="Current Net Worth"
          value={netWorth}
          icon={<Wallet className="w-5 h-5" aria-hidden="true" />}
          format="currency"
          className="col-span-12 md:col-span-4"
        />
        {/* Universal: 5-Year Projection (single, non-per-goal). */}
        <StatCard
          title={`Projected (${PROJECTION_HORIZON_YEARS} Years)`}
          value={fiveYear}
          change={
            isDepleting
              ? `−$${Math.abs(fiveYear - netWorth).toLocaleString('en-US', { maximumFractionDigits: 0 })} depleted`
              : `+$${(fiveYear - netWorth).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
          }
          changeType={isDepleting ? 'negative' : 'positive'}
          icon={<TrendingUp className="w-5 h-5" aria-hidden="true" />}
          format="currency"
          className="col-span-12 md:col-span-4"
        />
        {/* Per-goal horizon projections. Phase 8 — render one tile per
            goal using each goal's target_amount and ``resolveGoalHorizonYears``
            (horizon_years || target_date.year - current year). Without
            goals we render the synthesized USER.md fallback. */}
        {goalsToRender.map((goal) => {
          const horizonYears = resolveGoalHorizonYears(goal)
          const projection = projectDashboardTrajectory({
            netWorth,
            monthlyContribution,
            annualReturnRate: ANNUAL_RETURN_RATE,
            years: horizonYears,
          })
          const reached = projection >= goal.target_amount
          const label =
            horizonYears > 0 ? `${goal.name} (${horizonYears}y)` : goal.name
          return (
            <StatCard
              key={goalKey(goal)}
              title={label}
              value={goal.target_amount}
              change={
                reached
                  ? 'on track'
                  : `$${Math.max(0, goal.target_amount - projection).toLocaleString('en-US', { maximumFractionDigits: 0 })} short`
              }
              changeType={reached ? 'positive' : 'neutral'}
              icon={<Target className="w-5 h-5" aria-hidden="true" />}
              format="currency"
              className="col-span-12 md:col-span-4"
              data-testid={`goal-tile-${goal.id}`}
            />
          )
        })}
      </div>

      {/* Per-goal progress bars: one row per goal with progress %.
          Falls back to a single "Implied $15M" row when no goals exist. */}
      <div className="space-y-4 mt-4">
        {goalsToRender.map((goal) => {
          const progressPercent = Math.min(
            100,
            (netWorth / Math.max(1, goal.target_amount)) * 100,
          )
          return (
            <div
              key={goalKey(goal)}
              className="card p-6"
              data-testid={`goal-progress-${goal.id}`}
            >
              <div className="flex-between mb-2">
                <span className="label-md text-on-surface-variant">
                  {goal.name} progress
                </span>
                <span className="label-md text-primary">
                  ${netWorth.toLocaleString('en-US', { maximumFractionDigits: 0 })}{' '}
                  / ${goal.target_amount.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                </span>
              </div>
              <ProgressBar
                value={progressPercent}
                variant={
                  progressPercent >= 85
                    ? 'success'
                    : progressPercent >= 60
                      ? 'warning'
                      : 'danger'
                }
                size="md"
                label={`${goal.name}: ${progressPercent.toFixed(2)}% of target`}
              />
            </div>
          )
        })}
      </div>

      {userGoals.length === 0 && (
        <p className="body-sm text-on-surface-variant mt-4">
          No goals yet. Open{' '}
          <a
            href="/goals"
            className="text-primary underline hover:text-primary-600"
          >
            the Goals page
          </a>{' '}
          to add or seed your first goal.
        </p>
      )}
    </section>
  )
}
