'use client'

import React, { useState, useCallback } from 'react'
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Sector,
} from 'recharts'
import ChartWrapper from './ChartWrapper'
import { formatNumber } from '@/lib/format'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DonutSliceConfig {
  label: string
  value: number
  color: string
  subLabel?: string
}

export interface ChartDonutProps {
  /** Slice data */
  slices: DonutSliceConfig[]
  /** Center label (e.g., "Total") */
  centerLabel: string
  /** Center value to display */
  centerValue: number
  /** Chart height in px */
  height?: number
  /** Loading skeleton */
  loading?: boolean
  /** Format center value as currency */
  currency?: boolean
  /** Additional CSS classes */
  className?: string
}

// ---------------------------------------------------------------------------
// Currency formatter
// ---------------------------------------------------------------------------



// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: { payload: DonutSliceConfig & { pctLabel: string; originalIndex: number } }[]
}) {
  if (!active || !payload?.length) return null
  const slice = payload[0].payload

  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-color)] p-3 rounded-lg text-xs min-w-[160px]">
      <div className="flex items-center gap-2 mb-2">
        <div className="w-3 h-3 rounded-md ring-1 ring-black/5" style={{ backgroundColor: slice.color }} />
        <span className="font-semibold text-[var(--text-primary)]">{slice.label}</span>
      </div>
      {slice.subLabel && (
        <p className="text-[10px] text-[var(--text-tertiary)] mb-1.5">{slice.subLabel}</p>
      )}
      <div className="space-y-1 pt-1.5 border-t border-[var(--border-subtle)]">
        <div className="flex items-center justify-between gap-4">
          <span className="text-[11px] text-[var(--text-tertiary)]">Value</span>
          <span className="font-mono font-bold text-[var(--text-primary)]">{formatNumber(slice.value)}</span>
        </div>
        <div className="flex items-center justify-between gap-4">
          <span className="text-[11px] text-[var(--text-tertiary)]">Share</span>
          <span className="font-mono font-semibold text-[var(--text-primary)]">{slice.pctLabel}</span>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const ChartDonut = React.memo(function ChartDonut({
  slices,
  centerLabel,
  centerValue,
  height = 400,
  loading = false,
  currency = false,
  className,
}: ChartDonutProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null)

  const onMouseEnter = useCallback((data: unknown) => {
    const d = data as Record<string, unknown> | null
    if (d?.originalIndex != null) setActiveIndex(d.originalIndex as number)
  }, [])

  const onMouseLeave = useCallback(() => setActiveIndex(null), [])

  const total = slices.reduce((s, x) => s + x.value, 0) || 1

  const chartData = slices.map((slice, i) => ({
    ...slice,
    pctLabel: `${((slice.value / total) * 100).toFixed(1)}%`,
    originalIndex: i,
  }))

  const chartHeight = height - 64

  const renderShape = useCallback(
    (props: any) => {
      const isActive = activeIndex !== null && props.originalIndex === activeIndex
      const innerR = isActive ? (props.innerRadius ?? 0) - 5 : (props.innerRadius ?? 0)
      const outerR = isActive ? (props.outerRadius ?? 0) + 10 : (props.outerRadius ?? 0)

      return (
        <Sector
          cx={props.cx}
          cy={props.cy}
          innerRadius={innerR}
          outerRadius={outerR}
          startAngle={props.startAngle}
          endAngle={props.endAngle}
          fill={props.fill}
          stroke={props.stroke}
          strokeWidth={props.strokeWidth}
          style={{
            filter: isActive ? 'drop-shadow(0 6px 16px rgba(0,0,0,0.18)) brightness(1.08)' : undefined,
            transition: 'all 250ms cubic-bezier(0.4, 0, 0.2, 1)',
          }}
        />
      )
    },
    [activeIndex],
  )

  return (
    <ChartWrapper
      height={height}
      loading={loading}
      empty={!slices.length}
      emptyMessage="No allocation data yet."
      ariaLabel="Donut chart"
      interactiveChildren={slices.length > 0}
      className={className}
    >
      <div className="relative" style={{ height: chartHeight }}>
        {/* Subtle glow ring */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none" aria-hidden="true">
          <div
            className="rounded-full opacity-[0.04]"
            style={{
              width: 228,
              height: 228,
              background: 'radial-gradient(circle, var(--primary-400) 0%, transparent 70%)',
            }}
          />
        </div>

        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={78}
              outerRadius={116}
              paddingAngle={3}
              cornerRadius={4}
              dataKey="value"
              nameKey="label"
              shape={renderShape}
              onMouseEnter={onMouseEnter}
              onMouseLeave={onMouseLeave}
              animationBegin={0}
              animationDuration={900}
              animationEasing="ease-out"
              stroke="none"
            >
              {chartData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={entry.color}
                  style={{
                    cursor: 'pointer',
                    transition: 'opacity 200ms ease',
                    opacity: activeIndex !== null && activeIndex !== entry.originalIndex ? 0.4 : 1,
                  }}
                />
              ))}
            </Pie>
            <Tooltip content={<ChartTooltip />} />
          </PieChart>
        </ResponsiveContainer>

        {/* Center label */}
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none" aria-hidden="true">
          <span className="text-[11px] font-semibold mb-0.5" style={{ color: 'var(--text-tertiary)' }}>
            {centerLabel}
          </span>
          <span className="text-[26px] font-bold tracking-tight leading-none" style={{ color: 'var(--text-primary)' }}>
            {formatNumber(centerValue)}
          </span>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-1.5 justify-center mt-3 px-2">
        {slices.map((slice, i) => (
          <button
            key={`legend-${i}`}
            type="button"
            onMouseEnter={() => setActiveIndex(i)}
            onMouseLeave={() => setActiveIndex(null)}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] transition-all duration-200 hover:scale-[1.03]"
            style={{
              backgroundColor: `${slice.color}14`,
              border: `1px solid ${slice.color}30`,
              color: 'var(--text-secondary)',
              boxShadow: `0 1px 2px ${slice.color}10`,
            }}
          >
            <span className="w-2 h-2 rounded-[3px] flex-shrink-0 ring-1 ring-black/5" style={{ backgroundColor: slice.color }} />
            <span className="font-medium">{slice.label}</span>
            <span className="font-mono opacity-60 text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
              {`${((slice.value / total) * 100).toFixed(1)}%`}
            </span>
          </button>
        ))}
      </div>
    </ChartWrapper>
  )
})

export default ChartDonut
