'use client'

import { useMemo } from 'react'
import { Lightbulb, ArrowUpRight, ArrowDownRight } from 'lucide-react'
import type { TrendDataPoint } from '@/lib/api'
import { useThemeColors } from '@/lib/themeColors'
import { formatNumber } from '@/lib/format'

interface WhyDidThisChangeProps {
  trends: TrendDataPoint[]
  className?: string
}

interface Insight {
  label: string
  direction: 'up' | 'down'
  pct: number
  detail: string
  color: string
}

export default function WhyDidThisChange({ trends, className = '' }: WhyDidThisChangeProps) {
  const tc = useThemeColors()

  const insights = useMemo<Insight[]>(() => {
    if (trends.length < 2) return []
    const cur = trends[trends.length - 1]
    const prev = trends[trends.length - 2]

    const items: Insight[] = []

    // Income change
    if (prev.income > 0) {
      const pct = ((cur.income - prev.income) / prev.income) * 100
      if (Math.abs(pct) >= 5) {
        items.push({
          label: 'Income',
          direction: pct >= 0 ? 'up' : 'down',
          pct,
          detail: `${formatNumber(cur.income)} vs ${formatNumber(prev.income)} last month`,
          color: tc.income,
        })
      }
    }

    // Spend change
    if (prev.spend > 0) {
      const pct = ((cur.spend - prev.spend) / prev.spend) * 100
      if (Math.abs(pct) >= 5) {
        items.push({
          label: 'Spending',
          direction: pct >= 0 ? 'up' : 'down',
          pct,
          detail: `${formatNumber(cur.spend)} vs ${formatNumber(prev.spend)} last month`,
          color: tc.spend_series,
        })
      }
    }

    // Retained change
    if (prev.retained !== 0) {
      const pct = ((cur.retained - prev.retained) / Math.abs(prev.retained)) * 100
      if (Math.abs(pct) >= 5) {
        items.push({
          label: 'Net Retained',
          direction: pct >= 0 ? 'up' : 'down',
          pct,
          detail: `${formatNumber(cur.retained)} vs ${formatNumber(prev.retained)} last month`,
          color: tc.net_retained,
        })
      }
    }

    // Sort by absolute magnitude — biggest movers first
    items.sort((a, b) => Math.abs(b.pct) - Math.abs(a.pct))
    return items.slice(0, 3)
  }, [trends, tc])

  if (insights.length === 0) return null

  return (
    <div
      className={`flex items-start gap-3 p-4 rounded-xl bg-[var(--bg-secondary)] border border-[var(--border-color)] ${className}`}
      role="status"
      aria-label="Why did this change"
    >
      <div className="w-7 h-7 rounded-lg bg-[var(--warning-50)] flex items-center justify-center flex-shrink-0">
        <Lightbulb className="w-4 h-4 text-[var(--warning-600)]" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold text-[var(--text-primary)] mb-1.5">
          What changed this period
        </p>
        <div className="space-y-1">
          {insights.map((insight) => {
            const Icon = insight.direction === 'up' ? ArrowUpRight : ArrowDownRight
            return (
              <div key={insight.label} className="flex items-center gap-2 text-xs">
                <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: insight.color }} />
                <span className="text-[var(--text-secondary)] font-medium">{insight.label}</span>
                <span
                  className={`inline-flex items-center gap-0.5 font-semibold ${
                    insight.direction === 'up' ? 'text-[var(--success-600)]' : 'text-[var(--danger-500)]'
                  }`}
                >
                  <Icon className="w-3 h-3" />
                  {Math.abs(insight.pct).toFixed(0)}%
                </span>
                <span className="text-[var(--text-tertiary)] hidden sm:inline">— {insight.detail}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
