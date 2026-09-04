'use client'

import { useMemo } from 'react'
import SimpleDonutChart, { type DonutDatum } from './SimpleDonutChart'
import { formatCurrency } from '@/lib/format'

interface BreakdownDonutProps {
  data: DonutDatum[]
  total: number
  title?: string
  onSelect?: (datum: DonutDatum) => void
  className?: string
}

export default function BreakdownDonut({ data, total, title, onSelect, className = '' }: BreakdownDonutProps) {

  const chartData = useMemo(() => data.filter((d) => d.value > 0), [data])

  return (
    <div className={`card p-6 ${className}`}>
      {title && (
        <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--text-primary)] mb-4">
          {title}
        </h3>
      )}
      <div className="flex flex-col md:flex-row items-center gap-6">
        <SimpleDonutChart
          data={chartData}
          size={240}
          thickness={40}
          onSelect={onSelect}
          center={
            <div className="text-center">
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">Total</p>
              <p className="text-lg font-bold tabular-nums text-[var(--text-primary)]">{formatCurrency(total)}</p>
            </div>
          }
        />
        <div className="flex-1 w-full">
          <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {chartData.map((d) => {
              const pct = total > 0 ? (d.value / total) * 100 : 0
              return (
                <li key={d.id} className="min-w-0">
                  <button
                    type="button"
                    className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 text-sm rounded-md px-2 py-1.5 hover:bg-[var(--bg-secondary)] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--primary-500)] transition-colors text-left w-full min-w-0"
                    onClick={() => onSelect?.(d)}
                  >
                    <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: d.color }} />
                    <span className="min-w-0 truncate text-[var(--text-secondary)]">{d.name}</span>
                    <span className="text-right whitespace-nowrap">
                      <span className="block font-semibold text-on-surface tabular-nums">{formatCurrency(d.value)}</span>
                      <span className="block text-[10px] text-[var(--text-tertiary)] tabular-nums">{pct.toFixed(0)}%</span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      </div>
    </div>
  )
}
