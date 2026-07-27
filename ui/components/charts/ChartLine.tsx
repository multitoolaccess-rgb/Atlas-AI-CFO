'use client'

import React from 'react'
import {
  LineChart as ReLineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import ChartWrapper from './ChartWrapper'
import { formatCompact, formatNumber } from '@/lib/format'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface LineSeriesConfig {
  key: string
  name: string
  color: string
  strokeDasharray?: string
}

export interface ChartLineProps {
  /** Data array — each object should contain xKey + all series keys */
  data: Record<string, unknown>[]
  /** Series configuration */
  series: LineSeriesConfig[]
  /** Key used for X-axis labels */
  xKey: string
  /** Chart height in px */
  height?: number
  /** Loading skeleton */
  loading?: boolean
  /** Format Y-axis ticks as currency */
  currency?: boolean
  /** Additional CSS classes */
  className?: string
  /** Show grid lines */
  showGrid?: boolean
  /** Y-axis label */
  yAxisLabel?: string
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
  label,
}: {
  active?: boolean
  payload?: { name: string; value: number; color: string }[]
  label?: string
}) {
  if (!active || !payload?.length) return null

  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-color)] p-3 rounded-lg text-xs min-w-[140px]">
      <p className="text-[var(--text-tertiary)] mb-2 font-semibold">{label}</p>
      {payload.map((entry, i) => (
        <div key={i} className="flex items-center justify-between gap-4 py-0.5">
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }} />
            <span className="text-[var(--text-primary)]">{entry.name}</span>
          </div>
          <span className="font-mono font-semibold text-[var(--text-primary)]">
            {formatNumber(entry.value)}
          </span>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const ChartLine = React.memo(function ChartLine({
  data,
  series,
  xKey,
  height = 320,
  loading = false,
  currency = false,
  className,
  showGrid = true,
  yAxisLabel,
}: ChartLineProps) {
  return (
    <ChartWrapper
      height={height}
      loading={loading}
      empty={!data.length}
      emptyMessage="No trend data yet."
      ariaLabel="Line chart"
      className={className}
    >
      <ResponsiveContainer width="100%" height="100%">
        <ReLineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          {showGrid && (
            <CartesianGrid strokeDasharray="3 3" stroke="var(--slate-200)" vertical={false} />
          )}
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
            tick={{ fontSize: 11, fill: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}
            tickFormatter={currency ? formatCompact : undefined}
            width={60}
            label={
              yAxisLabel
                ? { value: yAxisLabel, angle: -90, position: 'insideLeft', style: { fontSize: 10, fill: 'var(--text-tertiary)' } }
                : undefined
            }
          />
          <Tooltip
            content={<ChartTooltip />}
            cursor={{ stroke: 'var(--slate-300)', strokeDasharray: '4 4' }}
          />
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
              animationDuration={900}
              animationEasing="ease-out"
            />
          ))}
        </ReLineChart>
      </ResponsiveContainer>
    </ChartWrapper>
  )
})

export default ChartLine
