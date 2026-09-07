'use client'

import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import BriefHero from '@/components/dashboard/BriefHero'
import MarketPulse from '@/components/dashboard/MarketPulse'
import TopNews from '@/components/dashboard/TopNews'
import EarningsCalendar from '@/components/dashboard/EarningsCalendar'
import { fetchDailyBriefSummary, type BriefNewsItem, type BriefEarningsEvent, type BriefSummary } from '@/lib/marketBriefs'

/**
 * DailyBriefToday — the "Today" tab of Market Intelligence.
 *
 * Renders the daily snapshot (hero P&L, market context, portfolio news,
 * upcoming earnings, data-quality footer) composed server-side from the
 * same Market Intelligence evidence pipeline. This is the single folded-in
 * home of the former standalone Daily Investment Brief.
 */
export default function DailyBriefToday() {
  const [brief, setBrief] = useState<BriefSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedNews, setSelectedNews] = useState<BriefNewsItem | null>(null)
  const [selectedEarning, setSelectedEarning] = useState<BriefEarningsEvent | null>(null)

  const loadBrief = useCallback(async () => {
    try {
      setError(null)
      setBrief(null)
      setLoading(true)
      const next = await fetchDailyBriefSummary()
      setBrief(next)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load the daily brief'
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadBrief()
  }, [loadBrief])

  const handleRefresh = useCallback(async () => {
    try {
      setRefreshing(true)
      setError(null)
      const next = await fetchDailyBriefSummary()
      setBrief(next)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to refresh the daily brief'
      setError(message)
    } finally {
      setRefreshing(false)
    }
  }, [])

  if (loading) {
    return (
      <div className="space-y-4" aria-busy="true">
        <div className="h-40 rounded-[var(--radius-lg)] bg-[var(--surface-container)] animate-pulse" />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="h-52 rounded-[var(--radius-lg)] bg-[var(--surface-container)] animate-pulse" />
          <div className="h-52 rounded-[var(--radius-lg)] bg-[var(--surface-container)] animate-pulse" />
        </div>
      </div>
    )
  }

  if (error || !brief) {
    return (
      <div className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] p-6 text-center">
        <p className="text-sm font-medium text-[var(--text-primary)]">Daily brief unavailable</p>
        <p className="mx-auto mt-1 max-w-md text-sm text-[var(--text-secondary)]">
          {error ?? 'No portfolio data available. Add holdings to see your daily brief.'}
        </p>
        <button
          type="button"
          onClick={() => void loadBrief()}
          className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-md bg-[var(--interactive-primary)] px-4 text-sm font-medium text-[var(--accent-on-primary)] hover:bg-[var(--interactive-hover)]"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Try again
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {brief.warnings && brief.warnings.length > 0 && (
        <div className="rounded-lg border border-warning-200 bg-warning-50 p-3 dark:border-warning-800 dark:bg-warning-900/30">
          <p className="text-xs text-warning-700 dark:text-warning-300">{brief.warnings[0]}</p>
        </div>
      )}

      <BriefHero data={brief.hero} isLoading={refreshing} onRefresh={handleRefresh} />

      {brief.market && (
        <section aria-labelledby="today-market-overview">
          <p id="today-market-overview" className="mb-3 text-xs font-semibold uppercase tracking-wide text-secondary">
            Market Overview
          </p>
          <MarketPulse market={brief.market} isLoading={refreshing} />
        </section>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <TopNews news={brief.news} isLoading={refreshing} onStoryClick={setSelectedNews} />
        <EarningsCalendar earnings={brief.earnings} isLoading={refreshing} onEarningClick={setSelectedEarning} />
      </div>

      {brief.quality && (
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-color)] p-4">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div>
              <p className="text-xs font-medium text-secondary">Coverage</p>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {brief.quality.coverage_covered}/{brief.quality.coverage_eligible}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium text-secondary">Freshness</p>
              <p className={`text-sm font-semibold ${brief.quality.freshness === 'fresh' ? 'text-success-600' : 'text-secondary'}`}>
                {brief.quality.freshness.charAt(0).toUpperCase() + brief.quality.freshness.slice(1)}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium text-secondary">Last Updated</p>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {new Date(brief.generated_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium text-secondary">Data Basis</p>
              <p className="text-sm font-semibold text-[var(--text-primary)]">{brief.quality.coverage_basis}</p>
            </div>
          </div>
        </div>
      )}

      {/* Selected-story / selected-earning detail modal hooks (kept for parity with the standalone brief page) */}
      {selectedNews && (
        <dialog open onClose={() => setSelectedNews(null)} className="m-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-raised)] p-5 shadow-xl backdrop:bg-black/40" aria-label="News story">
          <h3 className="text-base font-semibold text-[var(--text-primary)]">{selectedNews.headline}</h3>
          <p className="mt-2 text-sm leading-6 text-secondary">{selectedNews.summary}</p>
          <p className="mt-3 text-xs text-tertiary">
            {selectedNews.source} · {new Date(selectedNews.published_at).toLocaleDateString()}
          </p>
          <button type="button" onClick={() => setSelectedNews(null)} className="mt-4 min-h-11 rounded-md border border-[var(--border-subtle)] px-3 text-sm text-secondary hover:bg-[var(--surface-ambient)]">
            Close
          </button>
        </dialog>
      )}
      {selectedEarning && (
        <dialog open onClose={() => setSelectedEarning(null)} className="m-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-raised)] p-5 shadow-xl backdrop:bg-black/40" aria-label="Earnings event">
          <h3 className="text-base font-semibold text-[var(--text-primary)]">{selectedEarning.symbol}</h3>
          <p className="mt-2 text-sm text-secondary">
            {new Date(selectedEarning.date).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })} · {selectedEarning.quarter}
          </p>
          <button type="button" onClick={() => setSelectedEarning(null)} className="mt-4 min-h-11 rounded-md border border-[var(--border-subtle)] px-3 text-sm text-secondary hover:bg-[var(--surface-ambient)]">
            Close
          </button>
        </dialog>
      )}
    </div>
  )
}