'use client'

import { useMemo, useState } from 'react'
import { Activity, ArrowUpRight, ArrowDownRight } from 'lucide-react'
import GaugeRing from '@/components/charts/GaugeRing'
import type { DashboardSummary, DashboardBreakdownResponse, TrendDataPoint } from '@/lib/api'
import ExpandableCard from '@/components/dashboard/ExpandableCard'
import { formatNumber } from '@/lib/format'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface FinancialHealthGaugesProps {
  summary: DashboardSummary | null
  breakdown: DashboardBreakdownResponse | null
  /** Trend data for prior-period delta computation. */
  trends?: TrendDataPoint[] | null
  loading?: boolean
  className?: string
  /** Called when a user clicks a gauge for drilldown. */
  onGaugeClick?: (metric: string) => void
}

// ---------------------------------------------------------------------------
// Metric definitions with formulas and thresholds
// ---------------------------------------------------------------------------

interface MetricDetail {
  key: string
  label: string
  value: number
  formula: string
  numerator: string
  denominator: string
  status: 'healthy' | 'warning' | 'watch'
  statusLabel: string
  color: string
  subLabel: string
  priorValue?: number | null
}

function getStatusColor(status: MetricDetail['status']): string {
  switch (status) {
    case 'healthy': return 'var(--success-600)'
    case 'warning': return 'var(--warning-500)'
    case 'watch': return 'var(--danger-500)'
  }
}

function getStatusBg(status: MetricDetail['status']): string {
  switch (status) {
    case 'healthy': return 'var(--success-50)'
    case 'warning': return 'var(--warning-50)'
    case 'watch': return 'var(--danger-50)'
  }
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function FinancialHealthGauges({
  summary,
  breakdown,
  trends,
  loading,
  className = '',
  onGaugeClick,
}: FinancialHealthGaugesProps) {
  const [hoveredGauge, setHoveredGauge] = useState<string | null>(null)

  const metrics = useMemo(() => {
    const income = summary?.total_income_month ?? 0
    const expenses = summary?.total_expenses_month ?? 0
    const netWorth = summary?.total_balance ?? 0
    const monthlyNet = income - expenses

    const savingsRate = income > 0 ? Math.max(0, Math.min(100, (monthlyNet / income) * 100)) : 0
    const debtAmount = breakdown?.buckets?.find((b) => b.label === 'Debt')?.amount ?? 0
    const debtRatio = income > 0 ? Math.max(0, Math.min(100, (debtAmount / income) * 100)) : 0
    const savingsAmount = breakdown?.buckets?.find((b) => b.label === 'Savings')?.amount ?? 0
    const investmentRate = income > 0 ? Math.max(0, Math.min(100, (savingsAmount / income) * 100)) : 0
    const cashBuffer = expenses > 0 ? Math.min(100, (netWorth / (expenses * 12)) * 100) : netWorth > 0 ? 100 : 0



    // Compute prior-period savings rate from trends for delta badge.
    // Other metrics (debt, investment, cash buffer) need breakdown/net-worth
    // history which isn't available from the trends endpoint.
    let priorSavingsRate: number | null = null
    if (trends && trends.length >= 2) {
      const prev = trends[trends.length - 2]
      const prevNet = prev.income - prev.spend
      priorSavingsRate = prev.income > 0 ? Math.max(0, Math.min(100, (prevNet / prev.income) * 100)) : null
    }

    const details: MetricDetail[] = [
      {
        key: 'savings',
        label: 'Savings Rate',
        value: savingsRate,
        formula: '(Income − Expenses) / Income × 100',
        numerator: `${formatNumber(monthlyNet)} net`,
        denominator: `${formatNumber(income)} income`,
        status: savingsRate >= 20 ? 'healthy' : savingsRate >= 10 ? 'warning' : 'watch',
        statusLabel: savingsRate >= 20 ? 'Healthy' : savingsRate >= 10 ? 'Fair' : 'Needs attention',
        color: 'auto',
        subLabel: 'of income',
        priorValue: priorSavingsRate,
      },
      {
        key: 'debt',
        label: 'Debt Load',
        value: Math.max(0, 100 - debtRatio),
        formula: 'Debt Payments / Income × 100',
        numerator: `${formatNumber(debtAmount)} debt`,
        denominator: `${formatNumber(income)} income`,
        status: debtRatio <= 15 ? 'healthy' : debtRatio <= 30 ? 'warning' : 'watch',
        statusLabel: debtRatio <= 15 ? 'Healthy' : debtRatio <= 30 ? 'Elevated' : 'Critical',
        color: debtRatio > 30 ? 'var(--danger-500)' : debtRatio > 15 ? 'var(--warning-500)' : 'var(--success-500)',
        subLabel: `${Math.round(debtRatio)}% of income`,
      },
      {
        key: 'investment',
        label: 'Investment Rate',
        value: investmentRate,
        formula: 'Savings/Investment / Income × 100',
        numerator: `${formatNumber(savingsAmount)} saved`,
        denominator: `${formatNumber(income)} income`,
        status: investmentRate >= 15 ? 'healthy' : investmentRate >= 5 ? 'warning' : 'watch',
        statusLabel: investmentRate >= 15 ? 'Healthy' : investmentRate >= 5 ? 'Fair' : 'Needs attention',
        color: 'var(--info-500)',
        subLabel: 'of income',
      },
      {
        key: 'cashBuffer',
        label: 'Cash Buffer',
        value: cashBuffer,
        formula: 'Net Worth / (Monthly Expenses × 12) × 100',
        numerator: `${formatNumber(netWorth)} net worth`,
        denominator: `${formatNumber(expenses * 12)} annual`,
        status: cashBuffer >= 66 ? 'healthy' : cashBuffer >= 33 ? 'warning' : 'watch',
        statusLabel: cashBuffer >= 66 ? '12mo+ runway' : cashBuffer >= 33 ? '6mo runway' : 'Building',
        color: 'auto',
        subLabel: cashBuffer >= 80 ? '12mo runway' : cashBuffer >= 50 ? '6mo runway' : 'building',
      },
    ]

    return { savingsRate, debtRatio, investmentRate, cashBuffer, details }
  }, [summary, breakdown, trends])

  const expandedContent = (
    <div className="space-y-3">
      {metrics.details.map((m) => {
        const isHovered = hoveredGauge === m.key
        return (
          <div
            key={m.key}
            className={`p-3 rounded-lg border transition-all duration-150 cursor-pointer ${
              isHovered
                ? 'bg-[var(--bg-tertiary)] border-[var(--primary-200)]'
                : 'bg-[var(--bg-secondary)] border-[var(--border-color)] hover:border-[var(--primary-200)]'
            }`}
            onClick={() => onGaugeClick?.(m.key)}
            onMouseEnter={() => setHoveredGauge(m.key)}
            onMouseLeave={() => setHoveredGauge(null)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onGaugeClick?.(m.key) }}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold text-on-surface">{m.label}</span>
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold"
                style={{ backgroundColor: getStatusBg(m.status), color: getStatusColor(m.status) }}
              >
                {m.statusLabel}
              </span>
            </div>
            <p className="text-xs text-[var(--text-tertiary)] mb-1.5 font-mono">{m.formula}</p>
            <div className="flex items-center gap-4 text-xs text-[var(--text-secondary)]">
              <span className="inline-flex items-center gap-0.5"><ArrowUpRight className="w-3 h-3" />{m.numerator}</span>
              <span className="inline-flex items-center gap-0.5"><ArrowDownRight className="w-3 h-3" />{m.denominator}</span>
              <span className="ml-auto font-bold text-on-surface">{Math.round(m.value)}%</span>
              {m.priorValue != null && (
                <span className={`text-xs font-semibold ${m.value >= m.priorValue ? 'text-[var(--success-600)]' : 'text-[var(--danger-500)]'}`}>
                  {m.value >= m.priorValue ? '+' : ''}{(m.value - m.priorValue).toFixed(1)}pp vs prior
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )

  if (loading) {
    return (
      <ExpandableCard
        title="Financial Health"
        subtitle="Loading…"
        icon={<Activity className="w-4 h-4 text-[var(--primary-600)]" />}
        className={className}
      >
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-6" aria-busy="true">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="flex flex-col items-center gap-2">
              <div className="skeleton w-[100px] h-[100px] rounded-full" />
              <div className="skeleton h-3 w-16" />
            </div>
          ))}
        </div>
      </ExpandableCard>
    )
  }

  return (
    <ExpandableCard
      title="Financial Health"
      subtitle="Key ratios based on this month's activity"
      icon={<Activity className="w-4 h-4 text-[var(--primary-600)]" />}
      expandedContent={expandedContent}
      className={className}
    >
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
        {[
          { value: metrics.savingsRate, label: 'Savings Rate', subLabel: 'of income', color: 'auto', key: 'savings' },
          { value: Math.max(0, 100 - metrics.debtRatio), label: 'Debt Load', subLabel: `${Math.round(metrics.debtRatio)}% of income`, color: metrics.debtRatio > 30 ? 'var(--danger-500)' : metrics.debtRatio > 15 ? 'var(--warning-500)' : 'var(--success-500)', key: 'debt' },
          { value: metrics.investmentRate, label: 'Investment Rate', subLabel: 'of income', color: 'var(--info-500)', key: 'investment' },
          { value: metrics.cashBuffer, label: 'Cash Buffer', subLabel: metrics.cashBuffer >= 80 ? '12mo runway' : metrics.cashBuffer >= 50 ? '6mo runway' : 'building', color: 'auto', key: 'cashBuffer' },
        ].map((gauge) => (
          <button
            key={gauge.key}
            type="button"
            onClick={() => onGaugeClick?.(gauge.key)}
            onMouseEnter={() => setHoveredGauge(gauge.key)}
            onMouseLeave={() => setHoveredGauge(null)}
            className={`flex flex-col items-center gap-1 p-2 rounded-xl transition-all duration-150 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--primary-500)] ${
              hoveredGauge === gauge.key ? 'bg-[var(--bg-secondary)]' : 'hover:bg-[var(--bg-secondary)]'
            }`}
            aria-label={`${gauge.label}: ${Math.round(gauge.value)}%`}
          >
            <GaugeRing
              value={gauge.value}
              label={gauge.label}
              subLabel={gauge.subLabel}
              color={gauge.color}
              size={110}
              strokeWidth={10}
            />
          </button>
        ))}
      </div>
    </ExpandableCard>
  )
}
