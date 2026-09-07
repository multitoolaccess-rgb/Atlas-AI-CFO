'use client'

import SimpleDonutChart, { type DonutDatum } from '@/components/charts/SimpleDonutChart'
import { formatCurrency } from '@/lib/format'

interface ExpensePieChartProps {
  data: DonutDatum[]
  total: number
  onSelect?: (datum: DonutDatum) => void
  className?: string
}

export default function ExpensePieChart({
  data,
  total,
  onSelect,
  className = '',
}: ExpensePieChartProps) {
  return (
    <div className={`card p-6 ${className}`}>
      <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--text-primary)] mb-4">
        Expense Categories
      </h3>
      <div className="flex flex-col md:flex-row items-center gap-6">
        <SimpleDonutChart
          data={data}
          size={200}
          thickness={35}
          onSelect={onSelect}
          center={
            <div className="text-center">
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
                Total
              </p>
              <p className="text-lg font-bold tabular-nums text-[var(--danger-500)]">
                {formatCurrency(total)}
              </p>
            </div>
          }
        />
        <div className="flex-1 w-full">
          <ul className="space-y-2">
            {data.map((d) => {
              const pct = total > 0 ? (d.value / total) * 100 : 0
              return (
                <li key={d.id} className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-full flex-shrink-0"
                    style={{ backgroundColor: d.color }}
                  />
                  <span className="text-sm text-[var(--text-secondary)] flex-1 truncate">
                    {d.name}
                  </span>
                  <span className="text-sm font-semibold text-[var(--text-primary)] tabular-nums">
                    {formatCurrency(d.value)}
                  </span>
                  <span className="text-xs text-[var(--text-tertiary)] tabular-nums">
                    {pct.toFixed(0)}%
                  </span>
                </li>
              )
            })}
          </ul>
        </div>
      </div>
    </div>
  )
}
