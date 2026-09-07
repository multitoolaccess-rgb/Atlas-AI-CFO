'use client'

import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { MarketContext } from '@/lib/marketBriefs'

interface MarketPulseProps {
  market: MarketContext
  isLoading?: boolean
}

/**
 * MarketPulse - Quick market overview (SPY, QQQ, VTI)
 * 
 * Displays:
 * - Top market indices (SPY, QQQ, VTI)
 * - Daily percentage changes
 * - Color-coded (green/red/gray)
 * - Minimal compact layout
 * - Zero API calls (served from main brief data)
 */
export default function MarketPulse({
  market,
  isLoading = false,
}: MarketPulseProps) {
  if (isLoading) {
    return (
      <div className="flex gap-2">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="flex-1 h-12 bg-surface-container animate-pulse rounded-lg"
          />
        ))}
      </div>
    )
  }

  if (!market || (!market.spy_change && !market.qqq_change && !market.vti_change)) {
    return null
  }

  return (
    <div className="flex gap-2 flex-wrap">
      {market.spy_change !== undefined && market.spy_change !== null && (
        <MarketTicker ticker="SPY" change={market.spy_change} />
      )}
      {market.qqq_change !== undefined && market.qqq_change !== null && (
        <MarketTicker ticker="QQQ" change={market.qqq_change} />
      )}
      {market.vti_change !== undefined && market.vti_change !== null && (
        <MarketTicker ticker="VTI" change={market.vti_change} />
      )}
    </div>
  )
}

interface MarketTickerProps {
  ticker: string
  change: number
}

function MarketTicker({ ticker, change }: MarketTickerProps) {
  const isPositive = change > 0
  const isNegative = change < 0

  const color = isPositive
    ? 'bg-success-50 text-success-600'
    : isNegative
      ? 'bg-danger-50 text-danger-600'
      : 'bg-surface-container text-secondary'

  const Icon = isPositive ? TrendingUp : isNegative ? TrendingDown : Minus

  return (
    <div className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-current/10 ${color} text-sm font-medium`}>
      <span className="font-bold">{ticker}</span>
      <Icon className="w-4 h-4" aria-hidden="true" />
      <span className="tabular-nums">
        {isNegative ? '−' : isPositive ? '+' : ''}{Math.abs(change).toFixed(2)}%
      </span>
    </div>
  )
}
