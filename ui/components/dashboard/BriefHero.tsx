'use client'

import { TrendingUp, TrendingDown, Minus, RefreshCw } from 'lucide-react'
import { formatCurrency } from '@/lib/format'
import { BriefHeroData, HoldingChange } from '@/lib/marketBriefs'

interface BriefHeroProps {
  data: BriefHeroData
  isLoading?: boolean
  onRefresh?: () => void
}

/**
 * BriefHero - Hero section showing today's portfolio P&L
 * 
 * Displays:
 * - Large green/red daily P&L
 * - Percentage change
 * - Top gainer and loser
 * - Market context badges
 * - Refresh button
 * - Last updated timestamp
 */
export default function BriefHero({
  data,
  isLoading = false,
  onRefresh,
}: BriefHeroProps) {
  const isPositive = data.daily_pnl > 0
  const isNegative = data.daily_pnl < 0
  
  const heroColor = isPositive 
    ? 'text-success-600' 
    : isNegative 
      ? 'text-danger-600' 
      : 'text-secondary'
  
  const heroBgColor = isPositive
    ? 'bg-success-50'
    : isNegative
      ? 'bg-danger-50'
      : 'bg-surface-container'

  const TrendIcon = isPositive ? TrendingUp : isNegative ? TrendingDown : Minus

  return (
    <div className={`rounded-xl border border-outline-variant/20 p-6 ${heroBgColor}`}>
      {/* Header with refresh button */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-secondary">
          TODAY'S BRIEF
        </h2>
        <button
          onClick={onRefresh}
          disabled={isLoading}
          className="p-2 rounded-lg hover:bg-surface-container transition-colors disabled:opacity-50"
          aria-label="Refresh brief"
        >
          <RefreshCw 
            className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`}
            aria-hidden="true"
          />
        </button>
      </div>

      {/* Main P&L display */}
      <div className="flex items-baseline gap-3 mb-6">
        <div className="flex items-center gap-2">
          <TrendIcon className={`w-8 h-8 ${heroColor}`} aria-hidden="true" />
          <div>
            <div className={`text-4xl font-bold tabular-nums ${heroColor}`}>
              {isNegative ? '-' : isPositive ? '+' : ''}{formatCurrency(Math.abs(data.daily_pnl))}
            </div>
            <div className={`text-lg font-semibold ${heroColor}`}>
              {isNegative ? '−' : isPositive ? '+' : ''}{Math.abs(data.daily_pct).toFixed(2)}%
            </div>
          </div>
        </div>
      </div>

      {/* Market context badges */}
      <div className="flex flex-wrap gap-2 mb-6">
        {data.market_context && (
          <>
            {data.market_context.spy_change !== undefined && data.market_context.spy_change !== null && (
              <MarketBadge 
                ticker="SPY" 
                change={data.market_context.spy_change}
              />
            )}
            {data.market_context.qqq_change !== undefined && data.market_context.qqq_change !== null && (
              <MarketBadge 
                ticker="QQQ" 
                change={data.market_context.qqq_change}
              />
            )}
            {data.market_context.vti_change !== undefined && data.market_context.vti_change !== null && (
              <MarketBadge 
                ticker="VTI" 
                change={data.market_context.vti_change}
              />
            )}
          </>
        )}
      </div>

      {/* Top movers */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        {data.top_gainer && (
          <div className="bg-surface-container/50 rounded-lg p-3">
            <p className="text-xs text-secondary mb-1">Top Gainer</p>
            <p className="text-sm font-semibold text-success-600">
              {data.top_gainer.symbol}
            </p>
            <p className="text-xs text-success-600">
              ↑ {data.top_gainer.change_pct.toFixed(1)}%
            </p>
          </div>
        )}
        {data.top_loser && (
          <div className="bg-surface-container/50 rounded-lg p-3">
            <p className="text-xs text-secondary mb-1">Top Loser</p>
            <p className="text-sm font-semibold text-danger-600">
              {data.top_loser.symbol}
            </p>
            <p className="text-xs text-danger-600">
              ↓ {Math.abs(data.top_loser.change_pct).toFixed(1)}%
            </p>
          </div>
        )}
      </div>

      {/* Last updated */}
      <div className="text-xs text-secondary">
        Last updated: {(typeof data.updated_at === 'string' 
          ? new Date(data.updated_at) 
          : data.updated_at
        ).toLocaleTimeString(undefined, {
          hour: '2-digit',
          minute: '2-digit',
          timeZoneName: 'short'
        })}
      </div>
    </div>
  )
}

function MarketBadge({ ticker, change }: { ticker: string; change: number }) {
  const isPositive = change > 0
  const color = isPositive ? 'text-success-600' : change < 0 ? 'text-danger-600' : 'text-secondary'
  const icon = isPositive ? '▲' : change < 0 ? '▼' : '—'
  
  return (
    <div className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-surface-container text-sm font-medium ${color}`}>
      <span>{ticker}</span>
      <span>{icon}</span>
      <span>{Math.abs(change).toFixed(2)}%</span>
    </div>
  )
}
