'use client'

import { useEffect, useState } from 'react'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import BriefHero from '@/components/dashboard/BriefHero'
import TopNews from '@/components/dashboard/TopNews'
import EarningsCalendar from '@/components/dashboard/EarningsCalendar'
import MarketPulse from '@/components/dashboard/MarketPulse'
import LoadingIndicator from '@/components/ui/LoadingIndicator'
import type {
  BriefSummary,
  BriefHeroData,
  BriefNewsItem,
  BriefEarningsEvent,
  MarketContext,
} from '@/lib/marketBriefs'

/**
 * Daily Investment Brief - Redesigned
 * 
 * Robinhood/Fidelity/Bloomberg-style UI showing:
 * - Hero: Today's P&L and top movers
 * - Market: Quick market context (SPY, QQQ, VTI)
 * - News: 3-5 material news stories
 * - Earnings: Upcoming earnings this week
 * - Alerts: Watchlist and portfolio alerts
 * 
 * Design principles:
 * - Scannable: Card-based layout, clear hierarchy
 * - Fast: Aggressive caching (24h TTL)
 * - Reliable: No rate limit errors (15 calls max)
 * - Material: Only important information
 */
export default function DailyInvestmentBriefPage() {
  const [brief, setBrief] = useState<BriefSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedNews, setSelectedNews] = useState<BriefNewsItem | null>(null)
  const [selectedEarning, setSelectedEarning] = useState<BriefEarningsEvent | null>(null)

  // Load initial brief on mount
  useEffect(() => {
    loadBrief()
  }, [])

  const apiBaseUrl =
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    process.env.NEXT_PUBLIC_RULES_SERVICE_URL ||
    'http://127.0.0.1:8888'

  /**
   * Safely parse a response as JSON. If the backend returns an HTML
   * error page (e.g. a proxy 502/504 or Next.js error page), parse it
   * as text and surface it as a readable message instead of throwing
   * a raw "JSON.parse: unexpected character" SyntaxError.
   */
  const safeParseJson = async <T,>(response: Response): Promise<T> => {
    const contentType = response.headers.get('content-type') ?? ''
    if (contentType.includes('application/json')) {
      return (await response.json()) as T
    }
    // Non-JSON response (HTML error page, proxy error, etc.)
    const raw = await response.text()
    const snippet = raw.replace(/\s+/g, ' ').trim().slice(0, 120)
    throw new Error(
      `Backend returned ${response.status} (non-JSON): ${snippet || 'empty response'}`
    )
  }

  const loadBrief = async () => {
    try {
      setLoading(true)
      setError(null)

      const response = await fetch(`${apiBaseUrl}/api/v1/investments/brief/summary`, {
        credentials: 'include'
      })

      if (!response.ok) {
        const errorData = await safeParseJson<{ detail?: string }>(response)
        throw new Error(errorData.detail || 'Failed to load brief')
      }

      const data: BriefSummary = await safeParseJson<BriefSummary>(response)
      setBrief(data)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load brief'
      setError(message)
      console.error('Failed to load brief:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleRefresh = async () => {
    try {
      setRefreshing(true)
      setError(null)

      const response = await fetch(`${apiBaseUrl}/api/v1/investments/brief/refresh`, {
        method: 'POST',
        credentials: 'include'
      })

      if (!response.ok) {
        const errorData = await safeParseJson<{ detail?: string }>(response)
        throw new Error(errorData.detail || 'Failed to refresh brief')
      }

      const data: BriefSummary = await safeParseJson<BriefSummary>(response)
      setBrief(data)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to refresh brief'
      setError(message)
      console.error('Failed to refresh brief:', err)
    } finally {
      setRefreshing(false)
    }
  }

  if (loading) {
    return (
      <PageLayout>
        <PageHeader
          title="Daily Investment Brief"
          description="Portfolio overview and market insights"
        />
        <div className="space-y-4">
          <LoadingIndicator type="initial" message="Loading your brief..." />
        </div>
      </PageLayout>
    )
  }

  if (error) {
    return (
      <PageLayout>
        <PageHeader
          title="Daily Investment Brief"
          description="Portfolio overview and market insights"
        />
        <div className="rounded-lg border border-danger-200 bg-danger-50 p-4">
          <p className="text-sm text-danger-700 font-medium">Error loading brief</p>
          <p className="text-sm text-danger-600 mt-1">{error}</p>
          <button
            onClick={loadBrief}
            className="mt-3 px-3 py-2 text-sm font-medium rounded-lg bg-danger-600 text-white hover:bg-danger-700 transition-colors"
          >
            Try again
          </button>
        </div>
      </PageLayout>
    )
  }

  if (!brief) {
    return (
      <PageLayout>
        <PageHeader
          title="Daily Investment Brief"
          description="Portfolio overview and market insights"
        />
        <div className="rounded-lg border border-outline-variant/20 p-8 text-center">
          <p className="text-secondary">No portfolio data available</p>
          <p className="text-xs text-tertiary mt-1">Add holdings to see your Daily Investment Brief</p>
        </div>
      </PageLayout>
    )
  }

  return (
    <PageLayout>
      <PageHeader
        title="Daily Investment Brief"
        description="Portfolio overview and market insights"
      />

      {/* Warning banner if rate limited or stale */}
      {brief.warnings && brief.warnings.length > 0 && (
        <div className="rounded-lg border border-warning-200 bg-warning-50 p-3 mb-6">
          <p className="text-xs text-warning-700">
            {brief.warnings[0]}
          </p>
        </div>
      )}

      {/* Hero Section - Today's P&L */}
      <div className="mb-6">
        <BriefHero
          data={brief.hero}
          isLoading={refreshing}
          onRefresh={handleRefresh}
        />
      </div>

      {/* Market Context */}
      {brief.market && (
        <div className="mb-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-secondary mb-3">
            Market Overview
          </p>
          <MarketPulse market={brief.market} isLoading={refreshing} />
        </div>
      )}

      {/* Two-column layout: News and Earnings */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* News Column */}
        <div>
          <TopNews
            news={brief.news}
            isLoading={refreshing}
            onStoryClick={setSelectedNews}
          />
        </div>

        {/* Earnings Column */}
        <div>
          <EarningsCalendar
            earnings={brief.earnings}
            isLoading={refreshing}
            onEarningClick={setSelectedEarning}
          />
        </div>
      </div>

      {/* Data Quality Footer */}
      {brief.quality && (
        <div className="rounded-lg border border-outline-variant/20 p-4 bg-surface-container/30">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-secondary font-medium">Coverage</p>
              <p className="text-sm font-semibold text-on-surface">
                {brief.quality.coverage_covered}/{brief.quality.coverage_eligible}
              </p>
            </div>
            <div>
              <p className="text-xs text-secondary font-medium">Freshness</p>
              <p className={`text-sm font-semibold ${
                brief.quality.freshness === 'fresh'
                  ? 'text-success-600'
                  : brief.quality.freshness === 'stale'
                    ? 'text-warning-600'
                    : 'text-secondary'
              }`}>
                {brief.quality.freshness.charAt(0).toUpperCase() + brief.quality.freshness.slice(1)}
              </p>
            </div>
            <div>
              <p className="text-xs text-secondary font-medium">Last Updated</p>
              <p className="text-sm font-semibold text-on-surface">
                {new Date(brief.generated_at).toLocaleTimeString(undefined, {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </p>
            </div>
            <div>
              <p className="text-xs text-secondary font-medium">Data Basis</p>
              <p className="text-sm font-semibold text-on-surface">
                {brief.quality.coverage_basis}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Selected News Modal */}
      {selectedNews && (
        <NewsDetailModal
          news={selectedNews}
          onClose={() => setSelectedNews(null)}
        />
      )}

      {/* Selected Earning Modal */}
      {selectedEarning && (
        <EarningDetailModal
          earning={selectedEarning}
          onClose={() => setSelectedEarning(null)}
        />
      )}
    </PageLayout>
  )
}

interface NewsDetailModalProps {
  news: BriefNewsItem
  onClose: () => void
}

function NewsDetailModal({ news, onClose }: NewsDetailModalProps) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-surface-container rounded-lg max-w-2xl w-full max-h-96 overflow-y-auto p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h2 className="text-lg font-bold text-on-surface mb-2">
              {news.headline}
            </h2>
            <div className="flex items-center gap-2">
              {news.symbols.map((symbol) => (
                <span
                  key={symbol}
                  className="inline-block px-2 py-1 text-xs font-semibold rounded bg-primary/10 text-primary"
                >
                  {symbol}
                </span>
              ))}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-secondary hover:text-on-surface transition-colors text-2xl"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <p className="text-sm text-secondary leading-relaxed mb-4">
          {news.summary}
        </p>

        <div className="flex items-center justify-between pt-4 border-t border-outline-variant/20">
          <p className="text-xs text-tertiary">
            {news.source} • {new Date(news.published_at).toLocaleString()}
          </p>
          <a
            href={news.url}
            target="_blank"
            rel="noreferrer"
            className="px-3 py-2 text-sm font-medium text-primary hover:bg-primary/10 rounded-lg transition-colors"
          >
            Read full story →
          </a>
        </div>
      </div>
    </div>
  )
}

interface EarningDetailModalProps {
  earning: BriefEarningsEvent
  onClose: () => void
}

function EarningDetailModal({ earning, onClose }: EarningDetailModalProps) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-surface-container rounded-lg max-w-2xl w-full p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h2 className="text-lg font-bold text-on-surface">
              {earning.symbol} Earnings
            </h2>
            <p className="text-sm text-secondary mt-1">
              {earning.quarter} • {new Date(earning.date).toLocaleDateString()}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-secondary hover:text-on-surface transition-colors text-2xl"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="space-y-3 mb-4">
          <div className="flex items-center justify-between p-3 rounded-lg bg-surface-ambient">
            <p className="text-sm text-secondary">EPS Estimate</p>
            <p className="text-sm font-bold text-on-surface">
              ${earning.eps_estimate?.toFixed(2) || 'TBD'}
            </p>
          </div>
          {earning.eps_whisper && (
            <div className="flex items-center justify-between p-3 rounded-lg bg-surface-ambient">
              <p className="text-sm text-secondary">Whisper Estimate</p>
              <p className="text-sm font-bold text-on-surface">
                ${earning.eps_whisper.toFixed(2)}
              </p>
            </div>
          )}
          {earning.previous_eps && (
            <div className="flex items-center justify-between p-3 rounded-lg bg-surface-ambient">
              <p className="text-sm text-secondary">Previous EPS</p>
              <p className="text-sm font-bold text-on-surface">
                ${earning.previous_eps.toFixed(2)}
              </p>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between pt-4 border-t border-outline-variant/20">
          <p className="text-xs text-secondary">
            Confidence: {earning.confidence.charAt(0).toUpperCase() + earning.confidence.slice(1)}
          </p>
          <button
            onClick={onClose}
            className="px-3 py-2 text-sm font-medium text-primary hover:bg-primary/10 rounded-lg transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
