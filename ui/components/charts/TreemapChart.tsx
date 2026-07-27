'use client'

import { useState, useMemo, useCallback } from 'react'
import { motion } from 'framer-motion'
import { formatNumber } from '@/lib/format'

export interface TreemapDatum {
  id: string
  name: string
  value: number
  color: string
  [key: string]: unknown
}

interface TreemapChartProps {
  data: TreemapDatum[]
  onSelect?: (datum: TreemapDatum) => void
  height?: number
  className?: string
}

const BAR_GAP = 8
const BAR_MIN_HEIGHT = 32
const LABEL_WIDTH = 140

export default function TreemapChart({ data, onSelect, height = 320, className = '' }: TreemapChartProps) {
  const [hovered, setHovered] = useState<string | null>(null)

  const handleClick = useCallback(
    (datum: TreemapDatum) => {
      onSelect?.(datum)
    },
    [onSelect],
  )

  if (!data.length) {
    return (
      <div className={`flex items-center justify-center text-[var(--text-tertiary)] ${className}`} style={{ height }}>
        <p className="text-sm">No data yet.</p>
      </div>
    )
  }

  const total = useMemo(() => data.reduce((s, d) => s + d.value, 0) || 1, [data])
  const sorted = useMemo(() => [...data].sort((a, b) => b.value - a.value), [data])

  // Compute bar heights proportionally within the available height
  const availableHeight = height - (sorted.length - 1) * BAR_GAP
  const barHeights = sorted.map((d) =>
    Math.max(BAR_MIN_HEIGHT, (d.value / total) * availableHeight)
  )

  return (
    <div className={className} style={{ height, overflowY: 'auto' }}>
      <div className="flex flex-col" style={{ gap: BAR_GAP, minHeight: height }}>
        {sorted.map((d, i) => {
          const isHovered = hovered === d.id
          const barHeight = barHeights[i]
          const pct = ((d.value / total) * 100).toFixed(1)

          return (
            <div
              key={d.id}
              className="flex items-center gap-3 group cursor-pointer"
              style={{ height: barHeight }}
              onClick={() => handleClick(d)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  handleClick(d)
                }
              }}
              onMouseEnter={() => setHovered(d.id)}
              onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(d.id)}
              onBlur={() => setHovered(null)}
              tabIndex={0}
              role="button"
              aria-label={`${d.name}: ${formatNumber(d.value)} (${pct}%)`}
            >
              {/* Category label */}
              <div
                className="shrink-0 text-right text-xs font-medium text-[var(--text-secondary)] truncate"
                style={{ width: LABEL_WIDTH }}
              >
                <div className="truncate">{d.name}</div>
                <div className="text-[10px] text-[var(--text-tertiary)] tabular-nums">
                  {formatNumber(d.value)} · {pct}%
                </div>
              </div>

              {/* Bar */}
              <motion.div
                className="h-full rounded-r-md min-w-[4px]"
                style={{
                  width: `${(d.value / total) * 100}%`,
                  backgroundColor: d.color,
                }}
                initial={{ width: '0%' }}
                animate={{ width: `${(d.value / total) * 100}%` }}
                transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                whileHover={{ opacity: 0.85 }}
              />

              {/* Hover detail pill */}
              {isHovered && (
                <div className="shrink-0 px-2 py-1 rounded-md bg-[var(--bg-secondary)] border border-[var(--border-color)] text-xs font-semibold tabular-nums text-[var(--text-primary)] animate-fadeIn">
                  {formatNumber(d.value)}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
