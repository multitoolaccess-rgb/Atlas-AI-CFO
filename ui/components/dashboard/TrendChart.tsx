'use client'

import { useMemo, useState, useCallback } from 'react'
import { TrendingUp } from 'lucide-react'
import AreaTrend, { type AreaSeries } from '@/components/charts/AreaTrend'
import type { TrendDataPoint } from '@/lib/api'
import { useThemeColors } from '@/lib/themeColors'
import ExpandableCard from '@/components/dashboard/ExpandableCard'
import { formatCurrency, formatMonthLabel } from '@/lib/format'

// ---------------------------------------------------------------------------
// Delta badge (extracted to avoid re-creation per render)
// ---------------------------------------------------------------------------

function DeltaBadge({ label, pct, color }: { label: string; pct: number | null; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
      <span className="text-xs text-[var(--text-secondary)]">{label}</span>
      {pct != null ? (
        <span className={`text-xs font-semibold ${pct >= 0 ? 'text-[var(--success-600)]' : 'text-[var(--danger-500)]'}`}>
          {pct >= 0 ? '+' : ''}
          {pct.toFixed(1)}%
        </span>
      ) : (
        <span className="text-xs text-[var(--text-tertiary)]">—</span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface TrendChartProps {
  trends: TrendDataPoint[]
  /** Label for the shared Cash Flow range. */
  rangeLabel?: string
  loading?: boolean
  className?: string
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function TrendChart({ trends, rangeLabel, loading, className }: TrendChartProps) {
  const tc = useThemeColors()
  const [hiddenSeries, setHiddenSeries] = useState<Set<string>>(new Set())

  const SERIES: AreaSeries[] = useMemo(
    () => [
      { key: 'income', name: 'Income', color: tc.income, fillOpacity: 0.25 },
      { key: 'spend', name: 'Spend', color: tc.spend_series, fillOpacity: 0.2 },
      { key: 'retained', name: 'Net Retained', color: tc.net_retained, fillOpacity: 0.15 },
    ],
    [tc],
  )

  const toggleSeries = useCallback((key: string) => {
    setHiddenSeries((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  const visibleSeries = useMemo(
    () => SERIES.filter((s) => !hiddenSeries.has(s.key)),
    [SERIES, hiddenSeries],
  )

  const chartData = useMemo(
    () =>
      trends.map((t) => ({
        month: formatMonthLabel(t.month),
        income: t.income,
        spend: t.spend,
        retained: t.retained,
      })),
    [trends],
  )

  const latestMonth = trends.length > 0 ? trends[trends.length - 1] : null

  // Summary stats for expanded view
  const summary = useMemo(() => {
    if (trends.length === 0) return null
    const totalIncome = trends.reduce((s, t) => s + t.income, 0)
    const totalSpend = trends.reduce((s, t) => s + t.spend, 0)
    const totalRetained = trends.reduce((s, t) => s + t.retained, 0)
    const avgIncome = totalIncome / trends.length
    const avgSpend = totalSpend / trends.length
    const avgRetained = totalRetained / trends.length
    const maxIncomeMonth = trends.reduce((max, t) => (t.income > max.income ? t : max), trends[0])
    const maxSpendMonth = trends.reduce((max, t) => (t.spend > max.spend ? t : max), trends[0])
    const minRetainedMonth = trends.reduce((min, t) => (t.retained < min.retained ? t : min), trends[0])
    return { totalIncome, totalSpend, totalRetained, avgIncome, avgSpend, avgRetained, maxIncomeMonth, maxSpendMonth, minRetainedMonth }
  }, [trends])

  // Prior period delta
  const priorDelta = useMemo(() => {
    if (trends.length < 2) return null
    const cur = trends[trends.length - 1]
    const prev = trends[trends.length - 2]
    return {
      income: prev.income > 0 ? ((cur.income - prev.income) / prev.income) * 100 : null,
      spend: prev.spend > 0 ? ((cur.spend - prev.spend) / prev.spend) * 100 : null,
      retained: prev.retained !== 0 ? ((cur.retained - prev.retained) / Math.abs(prev.retained)) * 100 : null,
    }
  }, [trends])

  const expandedContent = summary ? (
    <div className="space-y-3">
      {/* Summary table — restrained data list, not hero metrics */}
      <div className="overflow-hidden rounded-lg border border-[var(--border-color)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[var(--bg-secondary)]">
              <th className="text-left px-3 py-2 text-xs font-semibold text-[var(--text-tertiary)]">Metric</th>
              <th className="text-right px-3 py-2 text-xs font-semibold text-[var(--text-tertiary)]">Period Total</th>
              <th className="text-right px-3 py-2 text-xs font-semibold text-[var(--text-tertiary)]">Monthly Avg</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border-color)]">
            {[
              { label: 'Income', total: summary.totalIncome, avg: summary.avgIncome, color: tc.income },
              { label: 'Spend', total: summary.totalSpend, avg: summary.avgSpend, color: tc.spend_series },
              { label: 'Retained', total: summary.totalRetained, avg: summary.avgRetained, color: tc.net_retained },
            ].map((row) => (
              <tr key={row.label} className="hover:bg-[var(--bg-secondary)] transition-colors">
                <td className="px-3 py-2 text-[var(--text-primary)]">
                  <span className="inline-block w-2 h-2 rounded-full mr-2" style={{ backgroundColor: row.color }} />
                  {row.label}
                </td>
                <td className="px-3 py-2 text-right font-mono text-[var(--text-primary)]">{formatCurrency(row.total)}</td>
                <td className="px-3 py-2 text-right font-mono text-[var(--text-tertiary)]">{formatCurrency(row.avg)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Prior period delta */}
      {priorDelta && (
        <div className="p-3 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-color)]">
          <p className="text-xs font-semibold text-[var(--text-tertiary)] mb-2">vs Previous Month</p>
          <div className="flex items-center gap-5">
            <DeltaBadge label="Income" pct={priorDelta.income} color={tc.income} />
            <DeltaBadge label="Spend" pct={priorDelta.spend} color={tc.spend_series} />
            <DeltaBadge label="Retained" pct={priorDelta.retained} color={tc.net_retained} />
          </div>
        </div>
      )}

      {/* Notable months */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-xs text-[var(--text-secondary)]">
        <span>
          Peak income:{' '}
          <strong className="font-mono" style={{ color: tc.income }}>
            {new Date(summary.maxIncomeMonth.month + '-01').toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}
          </strong>{' '}
          ({formatCurrency(summary.maxIncomeMonth.income)})
        </span>
        <span>
          Peak spend:{' '}
          <strong className="font-mono" style={{ color: tc.spend_series }}>
            {new Date(summary.maxSpendMonth.month + '-01').toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}
          </strong>{' '}
          ({formatCurrency(summary.maxSpendMonth.spend)})
        </span>
        <span>
          Lowest retained:{' '}
          <strong className="font-mono" style={{ color: tc.net_retained }}>
            {new Date(summary.minRetainedMonth.month + '-01').toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}
          </strong>{' '}
          ({formatCurrency(summary.minRetainedMonth.retained)})
        </span>
      </div>
    </div>
  ) : undefined

  return (
    <ExpandableCard
      title="Trend"
      subtitle={trends.length > 0 ? `${trends.length}-month income vs spending${rangeLabel ? ` · ${rangeLabel}` : ''}` : 'No trend data yet'}
      icon={<TrendingUp className="w-4 h-4 text-[var(--primary-600)]" />}
      headerRight={
        <div className="flex items-center gap-2">
          {/* Legend toggles */}
          {SERIES.map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => toggleSeries(s.key)}
              className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-all duration-150 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--primary-500)] ${
                hiddenSeries.has(s.key) ? 'opacity-40' : 'hover:bg-[var(--slate-100)]'
              }`}
              aria-label={`${hiddenSeries.has(s.key) ? 'Show' : 'Hide'} ${s.name}`}
            >
              <span className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ backgroundColor: s.color }} />
              <span className="text-[var(--text-secondary)] hidden lg:inline">{s.name}</span>
            </button>
          ))}

          {/* Latest month KPIs */}
          {latestMonth && (
            <div className="hidden md:flex items-center gap-3 ml-2 pl-2 border-l border-[var(--border-color)] text-right">
              <div>
                <p className="label-sm text-tertiary">Income</p>
                <p className="text-sm font-semibold" style={{ color: tc.income }}>
                  {formatCurrency(latestMonth.income)}
                </p>
              </div>
              <div>
                <p className="label-sm text-tertiary">Retained</p>
                <p className="text-sm font-semibold" style={{ color: tc.net_retained }}>
                  {formatCurrency(latestMonth.retained)}
                </p>
              </div>
            </div>
          )}
        </div>
      }
      expandedContent={expandedContent}
      className={className}
    >
      <AreaTrend data={chartData} series={visibleSeries} xKey="month" height={320} loading={loading} currency />
    </ExpandableCard>
  )
}
