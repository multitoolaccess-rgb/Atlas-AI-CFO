'use client'

import { useMemo } from 'react'
import { TrendingUp } from 'lucide-react'
import AreaTrend, { type AreaSeries } from '@/components/charts/AreaTrend'
import ExpandableCard from '@/components/dashboard/ExpandableCard'
import { formatCurrency, formatMonthLabel } from '@/lib/format'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface MonthlyTrendCardProps {
  title: string
  /** Series name shown in the chart legend, e.g. "Income". */
  seriesName: string
  points: { month: string; amount: number }[]
  /** Theme-aware hex accent for the series. */
  color: string
  /** Called when a month row is clicked for drilldown. */
  onSelect?: (month: string) => void
  className?: string
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function MonthlyTrendCard({ title, seriesName, points, color, onSelect, className = '' }: MonthlyTrendCardProps) {
  const series: AreaSeries = useMemo(
    () => ({ key: 'value', name: seriesName, color, fillOpacity: 0.25 }),
    [seriesName, color],
  )

  const chartData = useMemo(
    () => points.map((p) => ({ month: formatMonthLabel(p.month), value: p.amount })),
    [points],
  )

  const total = useMemo(() => points.reduce((s, p) => s + p.amount, 0), [points])
  const latest = points.length ? points[points.length - 1] : null

  const expandedContent = points.length > 0 ? (
    <div className="overflow-hidden rounded-lg border border-[var(--border-color)]">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-[var(--bg-secondary)]">
            <th className="text-left px-3 py-2 text-xs font-semibold text-[var(--text-tertiary)]">Month</th>
            <th className="text-right px-3 py-2 text-xs font-semibold text-[var(--text-tertiary)]">Amount</th>
            <th className="text-right px-3 py-2 text-xs font-semibold text-[var(--text-tertiary)]">Share</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--border-color)]">
          {points.map((p) => {
            const share = total > 0 ? (p.amount / total) * 100 : 0
            return (
              <tr
                key={p.month}
                onClick={() => onSelect?.(p.month)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onSelect?.(p.month)
                  }
                }}
                className="hover:bg-[var(--bg-secondary)] transition-colors cursor-pointer"
                tabIndex={0}
              >
                <td className="px-3 py-2 text-[var(--text-primary)]">{formatMonthLabel(p.month)}</td>
                <td className="px-3 py-2 text-right font-mono text-[var(--text-primary)] tabular-nums">{formatCurrency(p.amount)}</td>
                <td className="px-3 py-2 text-right font-mono text-[var(--text-tertiary)] tabular-nums">{share.toFixed(1)}%</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  ) : undefined

  return (
    <ExpandableCard
      title={title}
      subtitle={
        latest
          ? `${points.length} months · ${formatMonthLabel(latest.month)} ${formatCurrency(latest.amount)}`
          : 'No trend data yet'
      }
      icon={<TrendingUp className="w-4 h-4 text-[var(--primary-600)]" />}
      headerRight={
        latest ? (
          <div className="hidden md:flex items-center gap-2 pl-2 border-l border-[var(--border-color)] text-right">
            <div>
              <p className="label-sm text-tertiary">Latest · {formatMonthLabel(latest.month)}</p>
              <p className="text-sm font-semibold tabular-nums" style={{ color }}>{formatCurrency(latest.amount)}</p>
            </div>
          </div>
        ) : undefined
      }
      expandedContent={expandedContent}
      className={className}
    >
      <AreaTrend data={chartData} series={[series]} xKey="month" height={300} currency />
    </ExpandableCard>
  )
}