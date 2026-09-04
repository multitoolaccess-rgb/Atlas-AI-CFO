'use client'

import { useState, useMemo } from 'react'
import { BarChart3, ChevronRight } from 'lucide-react'
import SimpleDonutChart, { type DonutDatum } from '@/components/charts/SimpleDonutChart'
import type { DashboardBreakdownResponse, CashflowRole, TrendDataPoint } from '@/lib/api'
import { ROLE_LABELS } from '@/lib/api'
import { useThemeColors } from '@/lib/themeColors'
import ExpandableCard from '@/components/dashboard/ExpandableCard'
import TiltCard from '@/components/ui/TiltCard'
import { formatCurrency } from '@/lib/format'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface BreakdownPanelProps {
  breakdown: DashboardBreakdownResponse | null
  /** Label for the shared Cash Flow range. */
  rangeLabel?: string
  /** Trend data for prior-period delta computation. */
  trends?: TrendDataPoint[] | null
  loading?: boolean
  className?: string
  /** Called when a user clicks a breakdown segment for drilldown. */
  onSegmentClick?: (label: string) => void
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function BreakdownPanel({ breakdown, rangeLabel, trends, loading, className, onSegmentClick }: BreakdownPanelProps) {
  const tc = useThemeColors()
  const [hoveredSegment, setHoveredSegment] = useState<string | null>(null)

  // Prefer canonical transaction categories so this card speaks the same
  // vocabulary as the Sankey and Spending by Category modules. The legacy
  // role buckets remain as a compatibility fallback for older responses.
  const visibleBuckets = useMemo(
    () => breakdown
      ? (breakdown.categories?.length ? breakdown.categories : breakdown.buckets).filter((b) => b.amount > 0)
      : [],
    [breakdown],
  )
  const total = breakdown?.total_spend ?? 0

  const donutData: DonutDatum[] = useMemo(
    () =>
      visibleBuckets.map((b) => ({
        id: b.label,
        name: b.label,
        value: b.amount,
        color: b.color,
      })),
    [visibleBuckets],
  )

  // Prior-period spend delta from trends
  const spendDelta = useMemo(() => {
    if (!trends || trends.length < 2) return null
    const cur = trends[trends.length - 1]
    const prev = trends[trends.length - 2]
    if (prev.spend <= 0) return null
    return ((cur.spend - prev.spend) / prev.spend) * 100
  }, [trends])

  if (loading) {
    return (
      <ExpandableCard
        title="Breakdown"
        subtitle="Loading…"
        icon={<BarChart3 className="w-4 h-4 text-[var(--primary-600)]" />}
        className={className}
      >
        <div className="skeleton h-[320px] w-full" aria-busy="true" />
      </ExpandableCard>
    )
  }

  const expandedContent = visibleBuckets.length > 0 ? (
    <div className="space-y-3">
      {/* Detailed breakdown table */}
      <div className="space-y-2">
        {visibleBuckets.map((bucket) => {
          const isActive = hoveredSegment === bucket.label
          return (
            <div
              key={bucket.label}
              className={`flex items-center gap-3 p-3 rounded-lg border transition-all duration-150 cursor-pointer ${
                isActive
                  ? 'bg-[var(--bg-tertiary)] border-[var(--primary-200)]'
                  : 'bg-[var(--bg-secondary)] border-[var(--border-color)] hover:border-[var(--primary-200)]'
              }`}
              onClick={() => onSegmentClick?.(bucket.label)}
              onMouseEnter={() => setHoveredSegment(bucket.label)}
              onMouseLeave={() => setHoveredSegment(null)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onSegmentClick?.(bucket.label) }}
            >
              <div className="w-3 h-3 rounded-sm flex-shrink-0" style={{ backgroundColor: bucket.color }} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-on-surface">{bucket.label}</p>
                <p className="text-xs text-tertiary">{bucket.percentage}% of total</p>
              </div>
              <p className="text-sm font-bold text-on-surface tabular-nums whitespace-nowrap">{formatCurrency(bucket.amount)}</p>
              <ChevronRight className="w-4 h-4 text-[var(--text-tertiary)]" />
            </div>
          )
        })}
      </div>

      {/* Total */}
      <div className="flex items-center justify-between p-3 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-color)]">
        <span className="label-sm text-tertiary">Total Spending</span>
        <span className="text-base font-bold text-on-surface tabular-nums">{formatCurrency(total)}</span>
      </div>
    </div>
  ) : undefined

  return (
    <ExpandableCard
      title="Breakdown"
      subtitle={breakdown ? `${formatCurrency(total)} total spending · ${rangeLabel ?? breakdown.period}` : 'No breakdown data yet'}
      icon={<BarChart3 className="w-4 h-4 text-[var(--primary-600)]" />}
      expandedContent={expandedContent}
      className={className}
    >
      {/* Prior-period spend delta */}
      {spendDelta != null && (
        <div className="flex items-center gap-2 mb-3 px-1">
          <span className="text-xs text-[var(--text-tertiary)]">vs Previous Month</span>
          <span className={`text-xs font-semibold ${spendDelta >= 0 ? 'text-[var(--danger-500)]' : 'text-[var(--success-600)]'}`}>
            {spendDelta >= 0 ? '+' : ''}{spendDelta.toFixed(1)}%
          </span>
        </div>
      )}

      {/* Interactive category breakdown */}
      {visibleBuckets.length > 0 ? (
        <TiltCard className="p-2">
          <div className="flex flex-col items-center gap-4">
            <SimpleDonutChart
              data={donutData}
              size={220}
              thickness={44}
              activeId={hoveredSegment}
              onSelect={(d) => onSegmentClick?.(d.name)}
              className="flex-shrink-0"
              center={
                <div className="text-center">
                  <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">Total</p>
                  <p className="text-lg font-bold tabular-nums text-[var(--text-primary)]">{formatCurrency(total)}</p>
                </div>
              }
            />
            <div className="w-full min-w-0">
              <ul className="grid grid-cols-1 gap-1.5 max-h-[220px] overflow-y-auto pr-1">
                {visibleBuckets.map((bucket) => (
                  <li key={bucket.label} className="min-w-0">
                    <button
                      type="button"
                      className={`grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 text-sm rounded-md px-2 py-1.5 hover:bg-[var(--bg-secondary)] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--primary-500)] transition-colors text-left w-full min-w-0 ${
                        hoveredSegment === bucket.label ? 'ring-1 ring-[var(--primary-200)] bg-[var(--bg-secondary)]' : ''
                      }`}
                      onClick={() => onSegmentClick?.(bucket.label)}
                      onMouseEnter={() => setHoveredSegment(bucket.label)}
                      onMouseLeave={() => setHoveredSegment(null)}
                    >
                      <span className="w-3 h-3 rounded-sm flex-shrink-0" style={{ backgroundColor: bucket.color }} />
                      <span className="min-w-0 truncate text-[var(--text-secondary)]">{bucket.label}</span>
                      <span className="text-right whitespace-nowrap">
                        <span className="block font-semibold text-on-surface tabular-nums">{formatCurrency(bucket.amount)}</span>
                        <span className="block text-[10px] text-[var(--text-tertiary)] tabular-nums">{bucket.percentage}%</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </TiltCard>
      ) : (
        <div className="flex min-h-[220px] items-center justify-center rounded-lg border border-dashed border-[var(--border-color)] bg-[var(--bg-secondary)] px-6 text-center">
          <div>
            <p className="text-sm font-semibold text-[var(--text-primary)]">No spending in this range</p>
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">Choose a wider range or add transactions to see category detail.</p>
          </div>
        </div>
      )}

      {/* Role vocabulary footer */}
      <div className="mt-4 pt-3 border-t border-[var(--border-color)]">
        <p className="text-xs font-semibold text-tertiary mb-2">Roles</p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          {(['spend', 'earn', 'save', 'invest', 'debt', 'transfer'] as CashflowRole[]).map((role) => (
            <span key={role} className="inline-flex items-center gap-1 text-xs text-[var(--text-tertiary)]">
              <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: tc[role] }} />
              {ROLE_LABELS[role as CashflowRole]}
            </span>
          ))}
        </div>
      </div>
    </ExpandableCard>
  )
}
