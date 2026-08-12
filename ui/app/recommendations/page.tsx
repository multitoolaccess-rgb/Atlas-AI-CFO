'use client'

import { useState } from 'react'
import { Sparkles, TrendingUp, Shield, Wallet, Target, BarChart3, RefreshCw, AlertTriangle } from 'lucide-react'
import { motion, useReducedMotion } from 'framer-motion'
import PageLayout from '@/components/layout/PageLayout'
import RecommendationCard from '@/components/dashboard/RecommendationCard'
import TiltCard from '@/components/ui/TiltCard'
import EmptyState from '@/components/ui/EmptyState'
import { rulesService } from '@/lib/api'
import { formatNumber } from '@/lib/format'
import PageHeader from '@/components/ui/PageHeader'

/**
 * Static AI recommendations. Kept as the "what should you do" panel;
 * the new Analyst Insights section (added in Phase 9) is the live
 * "what does Wall Street think" panel. Both complement \u2014 the static
 * advice is personalised to your accounts/goals (no API needed),
 * while the analyst data is real-time sentiment for a chosen ticker.
 */
const RECOMMENDATIONS = [
  {
    title: 'Rebalance emerging markets exposure',
    description:
      'Your current allocation to tech-heavy ETFs is 12% above your target profile. Selling 4.2k and moving to a Dividend Growth fund could lower portfolio volatility by ~8%.',
    impact: 'Reduced volatility, steadier compounding',
    priority: 'medium' as const,
    icon: TrendingUp,
  },
  {
    title: 'Increase emergency fund to 6 months',
    description:
      'Your cash reserves cover ~3.2 months of expenses. Topping up to 6 months (8.4k) protects you from a single income shock without forcing a sale of long-term holdings.',
    impact: 'Income insurance, no forced liquidations',
    priority: 'high' as const,
    icon: Shield,
  },
  {
    title: 'Capture the 15M goal trajectory gap',
    description:
      'At your current monthly net contribution, the 20-year projection lands ~2.1M short of 15M. Bumping monthly contributions by 400 closes the gap with room to spare.',
    impact: 'Hits your long-term goal 4 years early',
    priority: 'high' as const,
    icon: Target,
  },
  {
    title: 'Consolidate two high-fee credit cards',
    description:
      'You have 2 cards charging >22% APR with 1.8k of revolving balance. A balance transfer to a 0% APR card for 18 months saves ~330 in interest.',
    impact: '~330 saved over 18 months',
    priority: 'low' as const,
    icon: Wallet,
  },
]

// Latest-month aggregation derived from the BE's recommendation_trends
// array. We surface the most-recent ``period`` only (recommendation\n// counts are noisy across periods \u2014 a 1-month snapshot is the most\n// useful summary). Falls back to ``null`` when no trends are present.
type Trend = {
  period: string
  strongBuy: number
  buy: number
  hold: number
  sell: number
  strongSell: number
}

function aggregateLatest(trends: Trend[] | undefined): {
  period: string | null
  buy: number
  hold: number
  sell: number
} {
  if (!trends || trends.length === 0) {
    return { period: null, buy: 0, hold: 0, sell: 0 }
  }
  const latest = trends[0]
  return {
    period: latest.period,
    buy: latest.strongBuy + latest.buy,
    hold: latest.hold,
    sell: latest.sell + latest.strongSell,
  }
}

export default function RecommendationsPage() {
  const reduced = useReducedMotion()
  const [dismissed, setDismissed] = useState<Set<number>>(new Set())
  const visible = RECOMMENDATIONS.filter((_, i) => !dismissed.has(i))

  // Analyst Ratings state
  const [tickerInput, setTickerInput] = useState('')
  const [ticker, setTicker] = useState<string>('')
  const [analyst, setAnalyst] = useState<{
    symbol: string
    recommendation_trends: Trend[]
    price_target: {
      targetMean: number
      targetMedian: number
      targetHigh: number
      targetLow: number
    } | null
  } | null>(null)
  const [analystLoading, setAnalystLoading] = useState(false)
  const [analystError, setAnalystError] = useState<string | null>(null)

  const loadAnalyst = async () => {
    if (!tickerInput.trim()) return
    setAnalystLoading(true)
    setAnalystError(null)
    setAnalyst(null)
    setTicker(tickerInput.trim().toUpperCase())
    try {
      const data = await rulesService.getAnalystRatings(tickerInput.trim())
      setAnalyst(data)
    } catch (err: any) {
      const status = err?.response?.status
      if (status === 502) {
        setAnalystError(
          'Finnhub is having issues. Try again in a few minutes.',
        )
      } else if (status === 500) {
        setAnalystError(
          'Analyst ratings service is not configured. Set FINNHUB_API_KEY in the BE environment.',
        )
      } else if (status === 401) {
        setAnalystError('Session expired. Reload the page.')
      } else {
        setAnalystError(err?.response?.data?.detail ?? err?.message ?? 'Failed to fetch.')
      }
    } finally {
      setAnalystLoading(false)
    }
  }

  const agg = aggregateLatest(analyst?.recommendation_trends)

  return (
    <PageLayout>
      <PageHeader
        title="AI Recommendations"
        description="Personalized financial moves derived from your accounts, cash flow, and goals."
        className="mb-6"
      />
      {visible.length === 0 ? (
        <EmptyState
          testId="recs-empty"
          icon={<Sparkles className="h-6 w-6" />}
          title="You are all caught up"
          description="New recommendations will appear here when Atlas has enough current data to identify a reviewable next step."
          guidance={<p className="text-sm">Keep accounts and goals current to give future recommendations useful context.</p>}
        />
      ) : (
        <motion.div
          className="grid grid-cols-1 lg:grid-cols-2 gap-6"
          data-testid="recs-grid"
          initial={reduced ? false : { opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        >
          {visible.map((rec, i) => {
            const originalIndex = RECOMMENDATIONS.indexOf(rec)
            return (
              <TiltCard key={originalIndex}>
                <RecommendationCard
                  title={rec.title}
                  description={rec.description}
                  impact={rec.impact}
                  priority={rec.priority}
                  onApprove={() => console.log('Approve', rec.title)}
                  onDeny={() => console.log('Deny', rec.title)}
                  onViewDetails={() => console.log('View', rec.title)}
                />
              </TiltCard>
            )
          })}
        </motion.div>
      )}

      {/* Phase 9 \u2014 Analyst Insights (real-time sell-side ratings via Finnhub) */}
      <section
        className="card p-6 mt-8"
        data-testid="analyst-section"
        aria-label="Analyst insights"
      >
        <div className="flex items-center gap-3 mb-4">
          <BarChart3 className="w-5 h-5 text-primary" aria-hidden="true" />
          <div>
            <h2 className="headline-md text-primary">Analyst Insights</h2>
            <p className="body-sm text-secondary">
              Live sell-side consensus + price targets (via Finnhub free tier, 24h cache).
            </p>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row gap-2 mb-4">
          <input
            type="text"
            placeholder="Enter ticker (e.g. AAPL, MSFT)"
            value={tickerInput}
            onChange={(e) => setTickerInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') loadAnalyst()
            }}
            className="
              flex-1 px-3 py-2 rounded-[var(--radius-md)]
              border border-[var(--border-color)]
              bg-[var(--bg-primary)] text-[var(--text-primary)]
              focus-visible:outline-2 focus-visible:outline-offset-2
              focus-visible:outline-[var(--primary-500)]
            "
            data-testid="analyst-ticker-input"
            aria-label="Ticker symbol"
          />
          <button
            type="button"
            onClick={loadAnalyst}
            disabled={analystLoading || !tickerInput.trim()}
            className="
              px-4 py-2 rounded-[var(--radius-md)]
              bg-[var(--interactive-primary)] text-[var(--text-on-brand)]
              hover:bg-[var(--interactive-hover)]
              disabled:opacity-50 disabled:cursor-not-allowed
              flex items-center gap-2
            "
            data-testid="analyst-load-btn"
          >
            {analystLoading ? (
              <RefreshCw className="w-4 h-4 animate-spin" aria-hidden="true" />
            ) : (
              <BarChart3 className="w-4 h-4" aria-hidden="true" />
            )}
            {analystLoading ? 'Loading\u2026' : 'Load ratings'}
          </button>
        </div>

        {analystError && (
          <div
            className="
              flex items-start gap-2 p-3
              bg-[var(--danger-50)] text-[var(--danger-700)]
              border border-[var(--danger-200)]
              rounded-[var(--radius-md)]
            "
            role="alert"
            data-testid="analyst-error"
          >
            <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" aria-hidden="true" />
            <p className="text-sm">{analystError}</p>
          </div>
        )}

        {analyst && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div className="card p-3 bg-[var(--bg-tertiary)]">
              <div className="label-sm text-tertiary uppercase tracking-wider">
                Symbol
              </div>
              <div
                className="text-base font-semibold text-primary mt-1"
                data-testid="analyst-symbol"
              >
                {analyst.symbol}
              </div>
            </div>
            <div className="card p-3 bg-[var(--bg-tertiary)]">
              <div className="label-sm text-tertiary uppercase tracking-wider">
                Buy ({agg.period ?? '\u2014'})
              </div>
              <div
                className="text-base font-semibold text-[var(--success-700)] mt-1"
                data-testid="analyst-total-buy"
              >
                {agg.buy}
              </div>
            </div>
            <div className="card p-3 bg-[var(--bg-tertiary)]">
              <div className="label-sm text-tertiary uppercase tracking-wider">
                Hold ({agg.period ?? '\u2014'})
              </div>
              <div
                className="text-base font-semibold text-[var(--warning-700)] mt-1"
                data-testid="analyst-total-hold"
              >
                {agg.hold}
              </div>
            </div>
            <div className="card p-3 bg-[var(--bg-tertiary)]">
              <div className="label-sm text-tertiary uppercase tracking-wider">
                Sell ({agg.period ?? '\u2014'})
              </div>
              <div
                className="text-base font-semibold text-[var(--danger-700)] mt-1"
                data-testid="analyst-total-sell"
              >
                {agg.sell}
              </div>
            </div>

            {analyst.price_target && (
              <div className="md:col-span-4 grid grid-cols-2 md:grid-cols-4 gap-3 mt-2">
                <div className="card p-3 bg-[var(--bg-tertiary)]">
                  <div className="label-sm text-tertiary uppercase tracking-wider">
                    Mean Target
                  </div>
                  <div
                    className="text-base font-semibold text-primary mt-1"
                    data-testid="analyst-price-target"
                  >
                    {formatNumber(analyst.price_target.targetMean)}
                  </div>
                </div>
                <div className="card p-3 bg-[var(--bg-tertiary)]">
                  <div className="label-sm text-tertiary uppercase tracking-wider">
                    Median
                  </div>
                  <div className="text-base font-semibold text-primary mt-1">
                    {formatNumber(analyst.price_target.targetMedian)}
                  </div>
                </div>
                <div className="card p-3 bg-[var(--bg-tertiary)]">
                  <div className="label-sm text-tertiary uppercase tracking-wider">
                    High
                  </div>
                  <div className="text-base font-semibold text-[var(--success-700)] mt-1">
                    {formatNumber(analyst.price_target.targetHigh)}
                  </div>
                </div>
                <div className="card p-3 bg-[var(--bg-tertiary)]">
                  <div className="label-sm text-tertiary uppercase tracking-wider">
                    Low
                  </div>
                  <div className="text-base font-semibold text-[var(--danger-700)] mt-1">
                    {formatNumber(analyst.price_target.targetLow)}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      <div className="mt-8 card p-6">
        <h2 className="headline-md text-primary mb-2">Want more?</h2>
        <p className="body-md text-secondary">
          Connect more accounts or import more statements \u2014 the more data the
          copilot has, the sharper these recommendations get. Head to the
          Accounts tab to add a new connection.
        </p>
      </div>
    </PageLayout>
  )
}
