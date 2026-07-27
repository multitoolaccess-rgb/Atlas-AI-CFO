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

export interface BarDatum {
  name: string
  value: number
  color: string
  /** Optional sub-label for tooltip */
  subLabel?: string
}

interface SimpleBarProps {
  data: BarDatum[]
  /** Height of the chart area */
  height?: number
  loading?: boolean
  /** Format values as currency */
  currency?: boolean
  /** Use horizontal layout */
  horizontal?: boolean
  className?: string
  /** Show grid lines */
  showGrid?: boolean
  /** Show values on bars */
  showLabels?: boolean
  /** Called when a bar is clicked (passes the bar's name). */
  onBarClick?: (name: string) => void
}

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------

function CustomTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: { payload: BarDatum }[]
}) {
  if (!active || !payload?.length) return null
  const item = payload[0].payload

  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-color)] p-4 rounded-lg text-sm min-w-[160px]">
      <div className="flex items-center gap-2 mb-2">
        <div
          className="w-3 h-3 rounded-[2px]"
          style={{ backgroundColor: item.color }}
        />
        <span className="font-semibold text-[var(--text-primary)] text-xs">
          {item.name}
        </span>
      </div>
      {item.subLabel && (
        <p className="text-[10px] text-[var(--text-tertiary)] mb-2">
          {item.subLabel}
        </p>
      )}
      <div className="pt-2 border-t border-[var(--border-subtle)]">
        <div className="flex items-center justify-between gap-4">
          <span className="text-[11px] text-[var(--text-tertiary)]">Value</span>
          <span className="font-mono font-bold text-[var(--text-primary)] text-xs tabular-nums">
            {formatNumber(item.value)}
          </span>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Currency formatter
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Custom bar label
// ---------------------------------------------------------------------------

function BarLabel({ x, y, width, height, value, horizontal }: { x: number; y: number; width: number; height: number; value: number; horizontal?: boolean }) {
  if (horizontal) {
    return (
      <text
        x={x + width + 6}
        y={y + height / 2}
        textAnchor="start"
        dominantBaseline="central"
        className="fill-[var(--text-tertiary)] font-mono"
        style={{ fontSize: '0.625rem' }}
      >
        {formatNumber(value)}
      </text>
    )
  }

  return (
    <text
      x={x + width / 2}
      y={y - 6}
      textAnchor="middle"
      className="fill-[var(--text-tertiary)] font-mono"
      style={{ fontSize: '0.625rem' }}
    >
      {formatNumber(value)}
    </text>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const SimpleBar = React.memo(function SimpleBar({
  data,
  height = 320,
  loading,
  currency,
  horizontal = false,
  className,
  showGrid = true,
  showLabels = false,
  onBarClick,
}: SimpleBarProps) {
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
        <p className="text-sm">No data yet.</p>
      </div>
    )
  }

  const chartHeight = horizontal ? Math.max(height, data.length * 48) : height

  return (
    <div
      className={className}
      style={{ height: horizontal ? chartHeight : height }}
      role="img"
      aria-label="Bar chart"
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout={horizontal ? 'vertical' : 'horizontal'}
          margin={{
            top: 8,
            right: horizontal ? 60 : 16,
            bottom: 8,
            left: horizontal ? 8 : 8,
          }}
        >
          {showGrid && (
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="var(--slate-200)"
              horizontal={!horizontal}
              vertical={horizontal}
            />
          )}
          {horizontal ? (
            <>
              <XAxis
                type="number"
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 11, fill: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}
                tickFormatter={currency ? formatCompact : undefined}
              />
              <YAxis
                type="category"
                dataKey="name"
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 11, fill: 'var(--text-secondary)', fontFamily: 'var(--font-primary)' }}
                width={80}
              />
            </>
          ) : (
            <>
              <XAxis
                dataKey="name"
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
                dy={8}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 11, fill: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}
                tickFormatter={currency ? formatCompact : undefined}
                width={55}
              />
            </>
          )}
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'var(--slate-100)' }} />
          <Bar
            dataKey="value"
            radius={horizontal ? [0, 2, 2, 0] : [2, 2, 0, 0]}
            animationDuration={800}
            animationEasing="ease-out"
            cursor={onBarClick ? 'pointer' : 'default'}
            onClick={onBarClick ? (bar: { name?: string }) => onBarClick(bar.name ?? '') : undefined}
            label={
              showLabels
                ? (props: any) => <BarLabel {...props} horizontal={horizontal} />
                : undefined
            }
          >
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
})

export default SimpleBar
