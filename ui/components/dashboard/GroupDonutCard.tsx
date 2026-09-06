'use client'

import { useMemo, useState } from 'react'
import { PieChart } from 'lucide-react'
import SimpleDonutChart, { type DonutDatum } from '@/components/charts/SimpleDonutChart'
import ExpandableCard from '@/components/dashboard/ExpandableCard'
import TiltCard from '@/components/ui/TiltCard'
import { formatCurrency } from '@/lib/format'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface GroupDonutCardProps {
  title: string
  /** Short label for the donut center and expanded total row. */
  totalLabel: string
  data: DonutDatum[]
  total: number
  /** Called when a segment/row is clicked for drilldown. */
  onSelect?: (datum: DonutDatum) => void
  className?: string
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function GroupDonutCard({ title, totalLabel, data, total, onSelect, className = '' }: GroupDonutCardProps) {
  const [hovered, setHovered] = useState<string | null>(null)

  const chartData = useMemo(() => data.filter((d) => d.value > 0), [data])

  const legendRow = (d: DonutDatum) => {
    const pct = total > 0 ? (d.value / total) * 100 : 0
    const isActive = hovered === d.id
    return (
      <li key={d.id} className="min-w-0">
        <button
          type="button"
          className={`grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 text-sm rounded-md px-2 py-1.5 hover:bg-[var(--bg-secondary)] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--primary-500)] transition-colors text-left w-full min-w-0 ${
            isActive ? 'ring-1 ring-[var(--primary-200)] bg-[var(--bg-secondary)]' : ''
          }`}
          onClick={() => onSelect?.(d)}
          onMouseEnter={() => setHovered(d.id)}
          onMouseLeave={() => setHovered(null)}
        >
          <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: d.color }} />
          <span className="min-w-0 truncate text-[var(--text-secondary)]">{d.name}</span>
          <span className="text-right whitespace-nowrap">
            <span className="block font-semibold text-[var(--text-primary)] tabular-nums">{formatCurrency(d.value)}</span>
            <span className="block text-[10px] text-[var(--text-tertiary)] tabular-nums">{pct.toFixed(0)}%</span>
          </span>
        </button>
      </li>
    )
  }

  const expandedContent = chartData.length > 0 ? (
    <div className="space-y-3">
      <div className="space-y-2">
        {chartData.map((d) => {
          const pct = total > 0 ? (d.value / total) * 100 : 0
          const isActive = hovered === d.id
          return (
            <div
              key={d.id}
              role="button"
              tabIndex={0}
              aria-label={`${d.name}: ${formatCurrency(d.value)} (${pct.toFixed(1)}%)`}
              className={`flex items-center gap-3 p-3 rounded-lg border transition-all duration-150 cursor-pointer ${
                isActive
                  ? 'bg-[var(--bg-tertiary)] border-[var(--primary-200)]'
                  : 'bg-[var(--bg-secondary)] border-[var(--border-color)] hover:border-[var(--primary-200)]'
              }`}
              onClick={() => onSelect?.(d)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onSelect?.(d)
                }
              }}
              onMouseEnter={() => setHovered(d.id)}
              onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(d.id)}
              onBlur={() => setHovered(null)}
            >
              <div className="w-3 h-3 rounded-sm flex-shrink-0" style={{ backgroundColor: d.color }} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-[var(--text-primary)] truncate">{d.name}</p>
                <p className="text-xs text-[var(--text-tertiary)]">{pct.toFixed(1)}% of {totalLabel.toLowerCase()}</p>
              </div>
              <p className="text-sm font-bold text-[var(--text-primary)] tabular-nums whitespace-nowrap">{formatCurrency(d.value)}</p>
            </div>
          )
        })}
      </div>

      <div className="flex items-center justify-between p-3 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-color)]">
        <span className="label-sm text-tertiary">{totalLabel}</span>
        <span className="text-base font-bold text-[var(--text-primary)] tabular-nums">{formatCurrency(total)}</span>
      </div>
    </div>
  ) : undefined

  return (
    <ExpandableCard
      title={title}
      subtitle={chartData.length > 0 ? `${chartData.length} groups · ${formatCurrency(total)}` : 'No data in this range'}
      icon={<PieChart className="w-4 h-4 text-[var(--primary-600)]" />}
      expandedContent={expandedContent}
      className={className}
    >
      {chartData.length > 0 ? (
        <TiltCard className="p-2">
          <div className="flex flex-col items-center gap-4">
            <SimpleDonutChart
              data={chartData}
              size={220}
              thickness={44}
              activeId={hovered}
              onSelect={onSelect}
              className="flex-shrink-0"
              center={
                <div className="text-center">
                  <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">{totalLabel}</p>
                  <p className="text-lg font-bold tabular-nums text-[var(--text-primary)]">{formatCurrency(total)}</p>
                </div>
              }
            />
            <div className="w-full min-w-0">
              <ul className="grid grid-cols-1 gap-1.5 max-h-[220px] overflow-y-auto pr-1">
                {chartData.map(legendRow)}
              </ul>
            </div>
          </div>
        </TiltCard>
      ) : (
        <div className="flex min-h-[220px] items-center justify-center rounded-lg border border-dashed border-[var(--border-color)] bg-[var(--bg-secondary)] px-6 text-center">
          <div>
            <p className="text-sm font-semibold text-[var(--text-primary)]">No {totalLabel.toLowerCase()} in this range</p>
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">Choose a wider range or add transactions to see group detail.</p>
          </div>
        </div>
      )}
    </ExpandableCard>
  )
}