'use client'

import React from 'react'
import {
  BarChart as ReBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import ChartWrapper from './ChartWrapper'
import { formatCompact, formatNumber } from '@/lib/format'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChartBarDatum {
  name: string
  value: number
  color: string
  subLabel?: string
}

export interface ChartBarProps {
  /** Bar data */
  data: ChartBarDatum[]
  /** Chart height in px */
  height?: number
  /** Loading skeleton */
  loading?: boolean
  /** Format values as currency */
  currency?: boolean
  /** Horizontal layout */
  horizontal?: boolean
  /** Additional CSS classes */
  className?: string
  /** Show grid lines */
  showGrid?: boolean
  /** Click handler */
  onBarClick?: (name: string) => void
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
  payload?: { payload: ChartBarDatum }[]
}) {
  if (!active || !payload?.length) return null
  const item = payload[0].payload

  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-color)] p-3 rounded-lg text-xs min-w-[140px]">
      <div className="flex items-center gap-1.5 mb-2">
        <div className="w-2.5 h-2.5 rounded-[2px]" style={{ backgroundColor: item.color }} />
        <span className="font-semibold text-[var(--text-primary)]">{item.name}</span>
      </div>
      {item.subLabel && (
        <p className="text-[10px] text-[var(--text-tertiary)] mb-1.5">{item.subLabel}</p>
      )}
      <div className="pt-1.5 border-t border-[var(--border-subtle)]">
        <span className="font-mono font-bold text-[var(--text-primary)]">{formatNumber(item.value)}</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const ChartBar = React.memo(function ChartBar({
  data,
  height = 320,
  loading = false,
  currency = false,
  horizontal = false,
  className,
  showGrid = true,
  onBarClick,
}: ChartBarProps) {
  const chartHeight = horizontal ? Math.max(height, data.length * 48) : height

  return (
    <ChartWrapper
      height={horizontal ? chartHeight : height}
      loading={loading}
      empty={!data.length}
      emptyMessage="No data yet."
      ariaLabel="Bar chart"
      className={className}
    >
      <ResponsiveContainer width="100%" height="100%">
        <ReBarChart
          data={data}
          layout={horizontal ? 'vertical' : 'horizontal'}
          margin={{
            top: 8,
            right: horizontal ? 60 : 16,
            bottom: 8,
            left: 8,
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
                tick={{ fontSize: 11, fill: 'var(--text-secondary)' }}
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
          <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--slate-100)' }} />
          <Bar
            dataKey="value"
            radius={horizontal ? [0, 2, 2, 0] : [2, 2, 0, 0]}
            animationDuration={800}
            animationEasing="ease-out"
            cursor={onBarClick ? 'pointer' : 'default'}
            onClick={
              onBarClick
                ? (bar: { name?: string }) => onBarClick(bar.name ?? '')
                : undefined
            }
          >
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Bar>
        </ReBarChart>
      </ResponsiveContainer>
    </ChartWrapper>
  )
})

export default ChartBar
