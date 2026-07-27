'use client'

import { useMemo } from 'react'
import { ArrowDownRight, ArrowUpRight, TrendingUp, Wallet, Activity } from 'lucide-react'
import CountUp from '@/components/ui/CountUp'
import WealthScoreRing from '@/components/dashboard/WealthScoreRing'
import TiltCard from '@/components/ui/TiltCard'
import { formatNumber } from '@/lib/format'
import type { DashboardSummary, DashboardBreakdownResponse, TrendDataPoint } from '@/lib/api'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface AIWealthOverviewProps {
  summary: DashboardSummary | null
  breakdown?: DashboardBreakdownResponse | null
  trends?: TrendDataPoint[] | null
  loading?: boolean
  className?: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Compute the monthly net cash-flow delta vs prior month from trends. */
function computeNetDelta(trends: TrendDataPoint[] | null | undefined): { delta: number; pct: number } | null {
  if (!trends || trends.length < 2) return null
  const current = trends[trends.length - 1]
  const prev = trends[trends.length - 2]
  const currentNet = current.income - current.spend
  const prevNet = prev.income - prev.spend
  if (prevNet === 0) return null
  const delta = currentNet - prevNet
  const pct = (delta / Math.abs(prevNet)) * 100
  return { delta, pct }
}

// ---------------------------------------------------------------------------
// Secondary hero tile
// ---------------------------------------------------------------------------

interface HeroTileProps {
  label: string
  value: number

  icon: React.ReactNode
  accentColor: string
  deltaLabel?: string
  deltaValue?: number | null
  loading?: boolean
  testId?: string
}

function HeroTile({ label, value, icon, accentColor, deltaLabel, deltaValue, loading, testId }: HeroTileProps) {
  const isPositive = (deltaValue ?? 0) > 0
  const isNegative = (deltaValue ?? 0) < 0
  const DeltaIcon = isPositive ? ArrowUpRight : isNegative ? ArrowDownRight : null
  const deltaColor = isPositive ? 'text-[var(--success-600)]' : isNegative ? 'text-[var(--danger-500)]' : 'text-[var(--text-tertiary)]'

  if (loading) {
    return (
      <div
        className="card p-5 flex flex-col gap-2 animate-pulse"
        aria-busy="true"
        data-testid={`${testId ?? label}-loading`}
      >
        <div className="skeleton h-4 w-1/3" />
        <div className="skeleton h-7 w-3/4" />
        <div className="skeleton h-3 w-1/2" />
      </div>
    )
  }

  return (
    <div
      className="card p-5 flex flex-col gap-2 transition-all duration-200"
      data-testid={testId}
    >
      <div className="flex items-center gap-2">
        {/* color-mix() requires Chrome 111+/Safari 16.2+/Firefox 113+. */}
        <span
          className="w-7 h-7 rounded-lg flex items-center justify-center"
          style={{ backgroundColor: `color-mix(in srgb, ${accentColor} 14%, transparent)` }}
        >
          {icon}
        </span>
        <span className="label-sm text-[var(--text-tertiary)]">{label}</span>
      </div>
      <p className="headline-md font-bold tabular-nums text-[var(--text-primary)]">
        {formatNumber(value)}
      </p>
      {deltaLabel && deltaValue != null && (
        <div className={`flex items-center gap-1 text-xs ${deltaColor}`}>
          {DeltaIcon && <DeltaIcon className="w-3 h-3" />}
          <span className="font-semibold">
            {isPositive ? '+' : ''}{Math.round(deltaValue)}%
          </span>
          <span className="text-[var(--text-tertiary)] ml-1">{deltaLabel}</span>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function AIWealthOverview({
  summary,
  breakdown,
  trends,
  loading,
  className,
}: AIWealthOverviewProps) {
  const netWorth = summary?.total_balance ?? 0
  const income = summary?.total_income_month ?? 0
  const expenses = summary?.total_expenses_month ?? 0
  const monthlyNet = income - expenses

  const netDelta = useMemo(() => computeNetDelta(trends), [trends])

  // Savings/invested from the breakdown Savings bucket
  const savedInvested = breakdown?.buckets?.find((b) => b.label === 'Savings')?.amount ?? 0

  // Compute income delta from trends
  const incomeDelta = useMemo(() => {
    if (!trends || trends.length < 2) return null
    const current = trends[trends.length - 1]
    const prev = trends[trends.length - 2]
    if (prev.income === 0) return null
    return ((current.income - prev.income) / prev.income) * 100
  }, [trends])

  const spendDelta = useMemo(() => {
    if (!trends || trends.length < 2) return null
    const current = trends[trends.length - 1]
    const prev = trends[trends.length - 2]
    if (prev.spend === 0) return null
    return ((current.spend - prev.spend) / prev.spend) * 100
  }, [trends])

  return (
    <section
      className={`mb-8 ${className ?? ''}`}
      aria-label="AI Wealth Overview"
      data-testid="ai-wealth-overview"
    >
      {/* Hero grid: giant net worth (left) + wealth score ring (right) + 3 tiles */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
        {/* Wealth summary — single integrated card, avoids the
            hero-metric cliché by keeping label/value inline and
            placing context in a compact sidebar. */}
        <TiltCard
          className="card p-6 lg:col-span-8 flex flex-col md:flex-row gap-6 items-stretch"
          data-testid="hero-net-worth"
        >
          <div className="flex-1 flex flex-col justify-center">
            <div className="flex items-center gap-2 mb-2">
              <Activity className="w-4 h-4 text-[var(--accent-electric)]" aria-hidden="true" />
              <span className="text-sm font-medium text-[var(--text-tertiary)]">Total Net Worth</span>
            </div>
            <p className="font-mono font-bold tabular-nums text-[var(--text-primary)] tracking-tight display-hero">
              {loading ? (
                <span className="skeleton inline-block h-12 w-56" aria-busy="true" />
              ) : (
                <CountUp
                  end={Math.round(netWorth)}
                  duration={1200}
                  className="text-[var(--text-primary)]"
                />
              )}
            </p>
            {netDelta && !loading && (
              <div
                className={`flex items-center gap-1.5 text-sm mt-2 ${
                  netDelta.delta > 0
                    ? 'text-positive'
                    : netDelta.delta < 0
                      ? 'text-negative'
                      : 'text-neutral'
                }`}
                data-testid="hero-net-worth-delta"
              >
                {netDelta.delta > 0 ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
                <span className="font-semibold tabular-nums">
                  {netDelta.delta > 0 ? '+' : ''}{formatNumber(netDelta.delta)}
                </span>
                <span className="text-[var(--text-tertiary)]">
                  ({netDelta.pct > 0 ? '+' : ''}{Math.round(netDelta.pct)}% vs last month)
                </span>
              </div>
            )}
          </div>

          {/* Compact metric sidebar — replaces the separate 2x2 tile grid. */}
          <div className="md:w-64 flex flex-col justify-center gap-3 border-t md:border-t-0 md:border-l border-[var(--border-subtle)] pt-4 md:pt-0 md:pl-6">
            <HeroTile
              label="Income MTD"
              value={income}
              icon={<TrendingUp className="w-3.5 h-3.5 text-positive" />}
              accentColor="var(--success-500)"
              deltaLabel="vs last mo"
              deltaValue={incomeDelta}
              loading={loading}
              testId="hero-income"
            />
            <HeroTile
              label="Spend MTD"
              value={expenses}
              icon={<Wallet className="w-3.5 h-3.5 text-negative" />}
              accentColor="var(--danger-500)"
              deltaLabel="vs last mo"
              deltaValue={spendDelta}
              loading={loading}
              testId="hero-spend"
            />
          </div>
        </TiltCard>

        {/* AI Wealth Score ring — spans 4 cols */}
        <TiltCard
          className="card p-6 lg:col-span-4 flex flex-col items-center justify-center"
          data-testid="hero-wealth-score"
        >
          <WealthScoreRing
            summary={summary}
            breakdown={breakdown ?? null}
            trends={trends ?? null}
            loading={loading}
            size={150}
          />
        </TiltCard>
      </div>
    </section>
  )
}
