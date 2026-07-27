'use client'

import React from 'react'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { formatCompact, formatNumber } from '@/lib/format'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AreaSeries {
  key: string
  name: string
  color: string
  /** Optional opacity override for the gradient fill (0-1). Default 0.3 */
  fillOpacity?: number
}

interface AreaTrendProps {
  data: Record<string, unknown>[]
  series: AreaSeries[]
  xKey: string
  height?: number
  loading?: boolean
  /** Format Y-axis ticks as currency */
  currency?: boolean
  className?: string
  /** Show grid lines */
  showGrid?: boolean
}

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: { name: string; value: number; color: string }[]
  label?: string
}) {
  if (!active || !payload?.length) return null

  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-color)] p-4 rounded-lg text-sm min-w-[180px]">
      <p className="text-xs text-[var(--text-tertiary)] mb-2.5 font-semibold">
        {label}
      </p>
      {payload.map((entry, i) => (
        <div key={i} className="flex items-center justify-between gap-5 py-1.5">
          <div className="flex items-center gap-2">
            <div
              className="w-2.5 h-2.5 rounded-[2px]"
              style={{ backgroundColor: entry.color }}
            />
            <span className="text-[var(--text-primary)] text-xs font-medium">
              {entry.name}
            </span>
          </div>
          <span className="font-mono font-semibold text-[var(--text-primary)] text-xs tabular-nums">
            {formatNumber(entry.value)}
          </span>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Y-axis formatter
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const AreaTrend = React.memo(function AreaTrend({
  data,
  series,
  xKey,
  height = 320,
  loading,
  currency,
  className,
  showGrid = true,
}: AreaTrendProps) {
  if (loading) {
    return (
      <div
        className={`flex items-center justify-center card ${className}`}
        style={{ height }}
        aria-busy="true"
      >
        <div className="w-full h-full skeleton" />
      </div>
    )
  }

  if (!data.length) {
    return (
      <div
        className={`flex items-center justify-center card text-[var(--text-tertiary)] ${className}`}
        style={{ height }}
      >
        <p className="text-sm">No trend data yet.</p>
      </div>
    )
  }

  return (
    <div
      className={className}
      style={{ height }}
      role="img"
      aria-label="Area trend chart"
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <defs>
            {series.map((s) => (
              <linearGradient
                key={`gradient-${s.key}`}
                id={`area-gradient-${s.key}`}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop offset="5%" stopColor={s.color} stopOpacity={s.fillOpacity ?? 0.3} />
                <stop offset="95%" stopColor={s.color} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          {showGrid && (
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="var(--slate-200)"
              vertical={false}
            />
          )}
          <XAxis
            dataKey={xKey}
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 11, fill: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}
            dy={8}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 11, fill: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}
            tickFormatter={currency ? formatCompact : undefined}
            width={60}
          />
          <Tooltip
            content={<CustomTooltip />}
            cursor={{ stroke: 'var(--slate-300)', strokeDasharray: '4 4' }}
          />
          <Legend
            verticalAlign="top"
            height={36}
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontFamily: 'var(--font-primary)' }}
          />
          {series.map((s) => (
            <Area
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.name}
              stroke={s.color}
              strokeWidth={2}
              fill={`url(#area-gradient-${s.key})`}
              dot={false}
              activeDot={{
                r: 4,
                strokeWidth: 2,
                fill: 'var(--bg-primary)',
                stroke: s.color,
              }}
              animationDuration={900}
              animationEasing="ease-out"
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
})

export default AreaTrend
