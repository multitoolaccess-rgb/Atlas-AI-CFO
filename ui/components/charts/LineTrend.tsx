'use client'

import React from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { formatCompact } from '@/lib/format'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface LineSeries {
  key: string
  name: string
  color: string
  /** Stroke dash array, e.g. "5 5" for dashed lines */
  strokeDasharray?: string
}

interface LineTrendProps {
  data: Record<string, unknown>[]
  series: LineSeries[]
  xKey: string
  height?: number
  loading?: boolean
  /** Format Y-axis ticks as currency */
  currency?: boolean
  /** Custom Y-axis label */
  yAxisLabel?: string
  className?: string
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
  const fmt = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  })

  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-color)] p-4 rounded-lg text-sm min-w-[160px]">
      <p className="text-xs text-[var(--text-tertiary)] mb-2 font-semibold">
        {label}
      </p>
      {payload.map((entry, i) => (
        <div key={i} className="flex items-center justify-between gap-4 py-1">
          <div className="flex items-center gap-2">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: entry.color }}
            />
            <span className="text-[var(--text-primary)] text-xs">{entry.name}</span>
          </div>
          <span className="font-semibold text-[var(--text-primary)] text-xs">
            {fmt.format(entry.value)}
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

const LineTrend = React.memo(function LineTrend({
  data,
  series,
  xKey,
  height = 320,
  loading,
  currency,
  yAxisLabel,
  className,
}: LineTrendProps) {
  if (loading) {
    return (
      <div
        className={`flex items-center justify-center card ${className}`}
        style={{ height }}
        aria-busy="true"
      >
        <div className="skeleton w-full h-full rounded-lg" />
      </div>
    )
  }

  if (!data.length) {
    return (
      <div
        className={`flex items-center justify-center card text-[var(--text-tertiary)] ${className}`}
        style={{ height }}
      >
        <p className="body-sm">No trend data yet.</p>
      </div>
    )
  }

  return (
    <div
      className={className}
      style={{ height }}
      role="img"
      aria-label="Trend line chart"
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={data}
          margin={{ top: 8, right: 16, bottom: 8, left: 8 }}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="var(--slate-200)"
            vertical={false}
          />
          <XAxis
            dataKey={xKey}
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }}
            dy={8}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }}
            tickFormatter={currency ? formatCompact : undefined}
            width={60}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ stroke: 'var(--slate-300)', strokeDasharray: '4 4' }} />
          <Legend
            verticalAlign="top"
            height={36}
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}
          />
          {series.map((s) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.name}
              stroke={s.color}
              strokeWidth={2.5}
              strokeDasharray={s.strokeDasharray}
              dot={{ r: 3, strokeWidth: 2, fill: '#fff', stroke: s.color }}
              activeDot={{ r: 5, strokeWidth: 2, fill: '#fff', stroke: s.color }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
})

export default LineTrend
