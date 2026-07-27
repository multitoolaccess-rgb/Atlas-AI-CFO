'use client'

// NOTE: Retained for future use. The dashboard page (ui/app/page.tsx)
// now uses AIWealthOverview as the hero zone (Phase 2 redesign). This
// component is kept because its KPI-card pattern may be reused on
// other pages (e.g. income/expenses summary strips).

import { ArrowDownRight, ArrowUpRight, Minus, TrendingUp, Wallet, PiggyBank, Landmark } from 'lucide-react'
import type { DashboardSummary, DashboardBreakdownResponse, TrendDataPoint } from '@/lib/api'
import { useThemeColors } from '@/lib/themeColors'
import { formatNumber } from '@/lib/format'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface KPIStripProps {
  summary: DashboardSummary | null
  trends: TrendDataPoint[] | null
  breakdown: DashboardBreakdownResponse | null
  loading?: boolean
  className?: string
}

// ---------------------------------------------------------------------------
// Single KPI card
// ---------------------------------------------------------------------------

interface KPICardProps {
  title: string
  value: number
  format?: 'currency' | 'number'
  icon: React.ReactNode
  /** Primary color bar accent */
  accentColor: string
  /** Delta vs last month (null = no data) */
  deltaLabel?: string
  deltaValue?: number | null
  loading?: boolean
}

function KPICard({ title, value, format = 'currency', icon, accentColor, deltaLabel, deltaValue, loading }: KPICardProps) {
  const fmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })

  const isPositive = (deltaValue ?? 0) > 0
  const isNegative = (deltaValue ?? 0) < 0
  const isZero = deltaValue === 0
  const DeltaIcon = isPositive ? ArrowUpRight : isNegative ? ArrowDownRight : Minus
  const deltaColor = isPositive ? 'text-[var(--success-600)]' : isNegative ? 'text-[var(--danger-500)]' : 'text-tertiary'

  if (loading) {
    return (
      <div className="card p-6 animate-pulse" aria-busy="true">
        <div className="skeleton h-4 w-1/2 mb-3" />
        <div className="skeleton h-8 w-3/4 mb-2" />
        <div className="skeleton h-3 w-1/3" />
      </div>
    )
  }

  return (
    <div className="card p-6 relative overflow-hidden transition-all duration-200 group">
      <div className="flex items-start justify-between mb-3">
        <p className="label-sm text-tertiary">{title}</p>
        <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${accentColor}24` }}>
          {icon}
        </div>
      </div>

      <p className="headline-xl text-on-surface mb-1 font-bold tracking-tight">
        {formatNumber(value)}
      </p>

      {deltaLabel && deltaValue != null && (
        <div className={`flex items-center gap-1 text-xs ${deltaColor}`}>
          <DeltaIcon className="w-3.5 h-3.5" />
          <span className="font-semibold">
            {isZero ? '0%' : `${isPositive ? '+' : ''}${Math.round(deltaValue)}%`}
          </span>
          <span className="text-tertiary ml-1">{deltaLabel}</span>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function KPIStrip({ summary, trends, breakdown, loading, className }: KPIStripProps) {
  const tc = useThemeColors()
  const income = summary?.total_income_month ?? 0
  const spend = summary?.total_expenses_month ?? 0
  const netRetained = income - spend

  // Saved/Invested pulled from the /api/dashboard/breakdown Savings bucket —
  // uses the same _SAVINGS_KEYWORDS classification (brokerage, retirement,
  // ira, 401k, deposits, transfers, contributions) as the breakdown panel.
  const savedInvested = breakdown?.buckets?.find(b => b.label === 'Savings')?.amount ?? 0

  // Compute deltas from trends data
  const currentMonth = new Date().toISOString().slice(0, 7)
  const trendMap = new Map((trends ?? []).map(t => [t.month, t]))

  function computeDelta(current: number, field: 'income' | 'spend' | 'retained'): number | null {
    if (!trends || trends.length < 2) return null
    // Find last month's data point
    const months = [...trendMap.keys()].sort()
    const currentIdx = months.indexOf(currentMonth)
    const prevMonth = currentIdx > 0 ? months[currentIdx - 1] : months[months.length - 2]
    const prev = trendMap.get(prevMonth)
    if (!prev || prev[field] === 0) return null
    return ((current - prev[field]) / prev[field]) * 100
  }

  const incomeDelta = computeDelta(income, 'income')
  const spendDelta = computeDelta(spend, 'spend')
  const retainedDelta = computeDelta(netRetained, 'retained')

  return (
    <section className={className}>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <KPICard
          title="Income MTD"
          value={income}
          icon={<TrendingUp className="w-4 h-4" style={{ color: tc.income_accent }} />}
          accentColor={tc.income_accent}
          deltaLabel="vs last month"
          deltaValue={incomeDelta}
          loading={loading}
        />
        <KPICard
          title="Spend MTD"
          value={spend}
          icon={<Wallet className="w-4 h-4" style={{ color: tc.spend_accent }} />}
          accentColor={tc.spend_accent}
          deltaLabel="vs last month"
          deltaValue={spendDelta}
          loading={loading}
        />
<KPICard
          title="Saved / Invested"
          value={savedInvested}
          icon={<PiggyBank className="w-4 h-4" style={{ color: tc.saved_accent }} />}
          accentColor={tc.saved_accent}
          deltaLabel={savedInvested > 0 ? 'from savings categories' : undefined}
          deltaValue={null}
          loading={loading}
        />
        <KPICard
          title="Net Retained"
          value={netRetained}
          icon={<Landmark className="w-4 h-4" style={{ color: tc.retained_accent }} />}
          accentColor={tc.retained_accent}
          deltaLabel="vs last month"
          deltaValue={retainedDelta}
          loading={loading}
        />
      </div>
    </section>
  )
}
