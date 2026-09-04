'use client'

import { useMemo } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { formatCurrency, formatNumber, formatMonthLabel } from '@/lib/format'

export interface VerticalBarDatum {
  id: string
  label: string
  value: number
  color?: string
}

interface VerticalBarChartProps {
  data: VerticalBarDatum[]
  maxValue?: number
  height?: number
  barWidth?: number
  onSelect?: (datum: VerticalBarDatum) => void
  className?: string
  /** Format values as currency in tooltips and accessible labels. */
  currency?: boolean
  /** Defaults to positive theme color. */
  defaultColor?: string
}

export default function VerticalBarChart({
  data,
  maxValue,
  height = 240,
  barWidth = 36,
  onSelect,
  className = '',
  currency = false,
  defaultColor = 'var(--primary-500)',
}: VerticalBarChartProps) {
  const reduced = useReducedMotion()

  const { max, chartData } = useMemo(() => {
    const computedMax = maxValue ?? ((Math.max(...data.map((d) => d.value), 0) || 1))
    return {
      max: computedMax,
      chartData: data.map((d) => ({ ...d, heightPct: computedMax > 0 ? d.value / computedMax : 0 })),
    }
  }, [data, maxValue])

  const displayLabel = (raw: string) => formatMonthLabel(raw)

  return (
    <div className={`w-full ${className}`}>
      <div
        className="relative flex items-end justify-between gap-2"
        style={{ height }}
      >
        {/* Background grid lines */}
        <div className="absolute inset-0 flex flex-col justify-between pointer-events-none">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="border-t border-[var(--border-color)] opacity-30" style={{ height: 0 }} />
          ))}
        </div>

        {chartData.map((d) => {
          const isActive = d.value > 0
          return (
            <div
              key={d.id}
              className="relative flex h-full flex-1 flex-col items-center justify-end group"
              style={{ minWidth: barWidth }}
            >
              {/* Tooltip value on hover */}
              <div
                className="mb-2 opacity-0 group-hover:opacity-100 transition-opacity text-xs font-semibold text-[var(--text-primary)] tabular-nums pointer-events-none absolute -top-6"
                aria-hidden="true"
              >
                {currency ? formatCurrency(d.value) : formatNumber(d.value)}
              </div>

              <motion.button
                type="button"
                onClick={() => onSelect?.(d)}
                disabled={!isActive}
                className="w-full rounded-t-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--primary-500)] shadow-sm"
                style={{
                  width: barWidth,
                  height: '100%',
                  backgroundColor: d.color || defaultColor,
                  transformOrigin: 'bottom',
                }}
                initial={reduced ? { scaleY: d.heightPct } : { scaleY: 0 }}
                animate={{ scaleY: d.heightPct }}
                transition={reduced ? { duration: 0 } : { duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                whileHover={reduced || !isActive ? undefined : { opacity: 0.85 }}
                aria-label={`${d.label}: ${currency ? formatCurrency(d.value) : formatNumber(d.value)}`}
              />

              <span className="mt-2 text-xs font-medium text-[var(--text-tertiary)] text-center">
                {displayLabel(d.label)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
