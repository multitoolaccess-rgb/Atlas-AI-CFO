'use client'

import React from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { formatCompact, formatNumber } from '@/lib/format'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface StackedSegment {
  key: string
  name: string
  color: string
}

interface StackedBarProps {
  data: Record<string, unknown>[]
  segments: StackedSegment[]
  xKey: string
  height?: number
  loading?: boolean
  currency?: boolean
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
  const total = payload.reduce((sum, p) => sum + (p.value || 0), 0)

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
            {formatNumber(entry.value)}
          </span>
        </div>
      ))}
      <div className="border-t border-[var(--border-subtle)] mt-2 pt-2 flex items-center justify-between">
        <span className="text-xs font-semibold text-[var(--text-primary)]">Total</span>
        <span className="text-xs font-bold text-[var(--text-primary)]">{formatNumber(total)}</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Y-axis formatter
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const StackedBar = React.memo(function StackedBar({
  data,
  segments,
  xKey,
  height = 320,
  loading,
  currency,
  className,
}: StackedBarProps) {
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
        <p className="body-sm">No breakdown data yet.</p>
      </div>
    )
  }

  return (
    <div
      className={className}
      style={{ height }}
      role="img"
      aria-label="Stacked bar chart"
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
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
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'var(--slate-100)' }} />
          {segments.map((seg) => (
            <Bar
              key={seg.key}
              dataKey={seg.key}
              name={seg.name}
              stackId="a"
              radius={seg.key === segments[segments.length - 1]?.key ? [4, 4, 0, 0] : [0, 0, 0, 0]}
            >
              {data.map((_, i) => (
                <Cell key={i} fill={seg.color} />
              ))}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
})

export default StackedBar
