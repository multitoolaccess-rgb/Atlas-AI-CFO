'use client'

import { useMemo } from 'react'
import GaugeRing from '@/components/charts/GaugeRing'
import type { DashboardSummary, DashboardBreakdownResponse, TrendDataPoint } from '@/lib/api'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface WealthScoreRingProps {
  summary: DashboardSummary | null
  breakdown?: DashboardBreakdownResponse | null
  trends?: TrendDataPoint[] | null
  loading?: boolean
  /** Ring size in px (default 160 for hero prominence). */
  size?: number
  className?: string
}

// ---------------------------------------------------------------------------
// Wealth score computation
// ---------------------------------------------------------------------------

/**
 * Compute a 0–850 AI Wealth Score from the same dashboard metrics that
 * drive the FinancialHealthGauges panel. The scale mirrors a FICO score
 * (300–850 is the live range; we render 0–850 so the ring fills
 * proportionally).
 *
 * Five weighted components:
 *   1. Savings rate      — 30% — (income − expenses) / income
 *   2. Debt load         — 25% — inverse of debt / income
 *   3. Investment rate   — 20% — savings-bucket / income
 *   4. Cash buffer       — 15% — net worth / annual expenses
 *   5. Activity breadth  — 10% — accounts + transactions density
 *
 * Each component is normalised to 0–100, then weighted and scaled to
 * the 300–850 band (base 300 + score/100 × 550).
 */
function computeWealthScore(
  summary: DashboardSummary | null,
  breakdown: DashboardBreakdownResponse | null | undefined,
  trends: TrendDataPoint[] | null | undefined,
): { score: number; trend: number | null } {
  if (!summary) return { score: 0, trend: null }

  const income = summary.total_income_month ?? 0
  const expenses = summary.total_expenses_month ?? 0
  const netWorth = summary.total_balance ?? 0
  const monthlyNet = income - expenses

  // 1. Savings rate (0–100)
  const savingsRate = income > 0
    ? Math.max(0, Math.min(100, (monthlyNet / income) * 100))
    : 0

  // 2. Debt load (0–100, inverted — lower debt = higher score)
  const debtAmount = breakdown?.buckets?.find((b) => b.label === 'Debt')?.amount ?? 0
  const debtRatio = income > 0 ? Math.min(100, (debtAmount / income) * 100) : 0
  const debtScore = Math.max(0, 100 - debtRatio * 2)

  // 3. Investment rate (0–100)
  const savingsAmount = breakdown?.buckets?.find((b) => b.label === 'Savings')?.amount ?? 0
  const investmentRate = income > 0
    ? Math.max(0, Math.min(100, (savingsAmount / income) * 100))
    : 0

  // 4. Cash buffer (0–100) — months of runway capped at 12
  const cashBuffer = expenses > 0
    ? Math.min(100, (netWorth / (expenses * 12)) * 100)
    : netWorth > 0 ? 100 : 0

  // 5. Activity breadth (0–100) — rewards having multiple accounts + txn history
  const accountsScore = Math.min(50, (summary.accounts_count ?? 0) * 10)
  const txnScore = Math.min(50, Math.log10(Math.max(1, summary.transactions_count ?? 0)) * 20)
  const activityScore = accountsScore + txnScore

  // Weighted composite (0–100)
  const composite =
    savingsRate * 0.30 +
    debtScore * 0.25 +
    investmentRate * 0.20 +
    cashBuffer * 0.15 +
    activityScore * 0.10

  // Scale to 300–850 band
  const score = Math.round(300 + (composite / 100) * 550)

  // Compute trend (delta vs prior month) ONLY from the savings-rate
  // component — the one signal we can reliably recompute from trends
  // alone (breakdown history isn't available). We compare the current
  // savings-rate sub-score to the prior month's savings-rate sub-score
  // so the delta is apples-to-apples, not a mixed-formula comparison.
  let trend: number | null = null
  if (trends && trends.length >= 2) {
    const prev = trends[trends.length - 2]
    const prevNet = prev.income - prev.spend
    const prevSavingsRate = prev.income > 0
      ? Math.max(0, Math.min(100, (prevNet / prev.income) * 100))
      : 0
    // Delta in savings-rate sub-score (0-100 → 0-550 scaled)
    const currentSubScore = Math.round(savingsRate * 0.30 * 5.5)
    const prevSubScore = Math.round(prevSavingsRate * 0.30 * 5.5)
    trend = currentSubScore - prevSubScore
  }

  return { score, trend }
}

/** Map a 300–850 score to a status label + color. */
function scoreStatus(score: number): { label: string; color: string } {
  if (score >= 750) return { label: 'Excellent', color: 'var(--success-500)' }
  if (score >= 670) return { label: 'Good', color: 'var(--info-500)' }
  if (score >= 580) return { label: 'Fair', color: 'var(--warning-500)' }
  return { label: 'Building', color: 'var(--danger-500)' }
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function WealthScoreRing({
  summary,
  breakdown,
  trends,
  loading,
  size = 160,
  className,
}: WealthScoreRingProps) {
  const { score, trend } = useMemo(
    () => computeWealthScore(summary, breakdown, trends),
    [summary, breakdown, trends],
  )

  if (loading) {
    return (
      <div
        className={`flex flex-col items-center gap-2 ${className ?? ''}`}
        aria-busy="true"
        data-testid="wealth-score-loading"
      >
        <div className="skeleton rounded-full" style={{ width: size, height: size }} />
        <div className="skeleton h-3 w-20" />
      </div>
    )
  }

  const status = scoreStatus(score)
  // GaugeRing expects 0–100; convert 300–850 → 0–100 for the ring fill
  const ringPercent = ((score - 300) / 550) * 100

  return (
    <div
      className={`flex flex-col items-center gap-1 ${className ?? ''}`}
      data-testid="wealth-score-ring"
    >
      <GaugeRing
        value={ringPercent}
        label="AI Wealth Score"
        subLabel={status.label}
        color={status.color}
        size={size}
        strokeWidth={12}
        format="number"
        rawValue={score}
        animate
      />
      {trend !== null && (
        <span
          className={`text-xs font-semibold tabular-nums ${
            trend > 0
              ? 'text-[var(--success-600)]'
              : trend < 0
                ? 'text-[var(--danger-500)]'
                : 'text-[var(--text-tertiary)]'
          }`}
          data-testid="wealth-score-trend"
        >
          {trend > 0 ? '↑' : trend < 0 ? '↓' : '→'} {Math.abs(trend)} pts vs last month
        </span>
      )}
    </div>
  )
}

export { computeWealthScore, scoreStatus }
