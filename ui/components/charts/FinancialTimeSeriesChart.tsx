'use client'

import { useMemo, useState } from 'react'
import ChartLine, { type LineSeriesConfig } from './ChartLine'

export type FinancialDataState = 'observed' | 'derived' | 'estimated' | 'stale' | 'missing' | 'unknown' | 'insufficient_history' | 'unavailable'

export interface FinancialTimeSeriesPoint {
  timestamp: string
  [key: string]: string | number | null
}

export interface FinancialTimeSeriesChartProps {
  title: string
  data: FinancialTimeSeriesPoint[]
  series: LineSeriesConfig[]
  xKey?: string
  unit: string
  asOf?: string | null
  source?: string | null
  freshness?: FinancialDataState
  height?: number
  loading?: boolean
  emptyMessage?: string
}

function labelForState(state: FinancialDataState | undefined) {
  return state ? state.replaceAll('_', ' ') : 'unknown'
}

function displayDate(value: string | null | undefined) {
  if (!value) return 'Unavailable'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString()
}

export default function FinancialTimeSeriesChart({
  title,
  data,
  series,
  xKey = 'timestamp',
  unit,
  asOf,
  source,
  freshness = 'unknown',
  height = 300,
  loading = false,
  emptyMessage = 'No canonical time-series data is available.',
}: FinancialTimeSeriesChartProps) {
  const [tableOpen, setTableOpen] = useState(false)
  const hasData = data.length > 0
  const summary = useMemo(() => {
    if (!hasData) return emptyMessage
    return `${title}. ${data.length} observations. Unit: ${unit}. As of ${displayDate(asOf)}. State: ${labelForState(freshness)}.`
  }, [asOf, data.length, emptyMessage, freshness, hasData, title, unit])

  return <section className="card p-4" aria-labelledby={`${title.replaceAll(' ', '-').toLowerCase()}-title`}>
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 id={`${title.replaceAll(' ', '-').toLowerCase()}-title`} className="font-semibold text-primary">{title}</h2><p className="mt-1 text-xs text-secondary">Unit: {unit} · As of: {displayDate(asOf)} · State: {labelForState(freshness)}</p>{source && <p className="mt-1 text-xs text-tertiary">Source: {source}</p>}</div>
      {hasData && <button type="button" onClick={() => setTableOpen((open) => !open)} aria-expanded={tableOpen} className="min-h-11 rounded-md border border-[var(--border-subtle)] px-3 text-xs font-medium text-secondary hover:bg-[var(--surface-ambient)]">{tableOpen ? 'Hide data table' : 'View data table'}</button>}
    </div>
    <p className="sr-only" role="note">{summary}</p>
    <div className="mt-3"><ChartLine data={data as Record<string, unknown>[]} series={series} xKey={xKey} height={height} currency={unit.toLowerCase().includes('currency')} /></div>
    {tableOpen && hasData && <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[420px] text-left text-xs"><caption className="sr-only">{title} data table</caption><thead className="border-b border-[var(--border-subtle)] text-tertiary"><tr><th scope="col" className="px-2 py-2 font-medium">Date</th>{series.map((item) => <th key={item.key} scope="col" className="px-2 py-2 text-right font-medium">{item.name}</th>)}</tr></thead><tbody className="divide-y divide-[var(--border-subtle)]">{data.map((point) => <tr key={point.timestamp}><th scope="row" className="px-2 py-2 font-mono font-normal text-secondary">{point.timestamp}</th>{series.map((item) => <td key={item.key} className="px-2 py-2 text-right font-mono text-primary">{point[item.key] == null ? 'Unavailable' : String(point[item.key])}</td>)}</tr>)}</tbody></table></div>}
  </section>
}
