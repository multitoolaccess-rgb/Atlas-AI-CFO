'use client'

import { useState, useCallback, useMemo, Suspense, type ReactNode } from 'react'
import dynamic from 'next/dynamic'
import Sidebar from '@/components/layout/Sidebar'
import Header from '@/components/layout/Header'
import { SidebarProvider, useSidebar } from '@/components/layout/SidebarContext'
import AIWealthOverview from '@/components/dashboard/AIWealthOverview'
import FinancialPlans from '@/components/dashboard/FinancialPlans'
import CategoryMovers from '@/components/dashboard/CategoryMovers'
import AlertsPanel from '@/components/dashboard/AlertsPanel'
import ApprovalQueue from '@/components/dashboard/ApprovalQueue'
import FinancialHealthGauges from '@/components/dashboard/FinancialHealthGauges'
import RecentActivity from '@/components/dashboard/RecentActivity'
import RecurringTransactions from '@/components/dashboard/RecurringTransactions'
import ReviewQueueBadge from '@/components/dashboard/ReviewQueueBadge'
import WhyDidThisChange from '@/components/dashboard/WhyDidThisChange'
import { DashboardFilterProvider, useDashboardFilters } from '@/components/dashboard/DashboardFilterContext'
import GlobalFilterBar from '@/components/dashboard/GlobalFilterBar'
import DrilldownDrawer from '@/components/dashboard/DrilldownDrawer'
import { getTimeRangeDates } from '@/components/ui/TimeRangeSelector'
import ErrorBanner from '@/components/ui/ErrorBanner'
import TiltCard from '@/components/ui/TiltCard'
import { Receipt, RefreshCw, Upload, Orbit } from 'lucide-react'
import { useCachedFetch } from '@/lib/cache'
import { classifyErrorMessage } from '@/lib/errors'
import AnimatedSection from '@/components/ui/AnimatedSection'
import { formatNumber } from '@/lib/format'

// --- Phase 4 + 5 — AI Copilot + Wealth Simulation Suite ---
import CopilotRoot from '@/components/copilot/CopilotRoot'
import { WealthSimulationProvider } from '@/components/simulation/WealthSimulationContext'
const WealthTimeline = dynamic(() => import('@/components/simulation/WealthTimeline'), { ssr: false, loading: () => <div className="card p-6 h-[280px]"><div className="skeleton h-full w-full" /></div> })
const MoneyFlowSimulator = dynamic(() => import('@/components/simulation/MoneyFlowSimulator'), { ssr: false, loading: () => <div className="card p-6 h-[280px]"><div className="skeleton h-full w-full" /></div> })
const LifeEventSimulator = dynamic(() => import('@/components/simulation/LifeEventSimulator'), { ssr: false, loading: () => <div className="card p-6 h-[280px]"><div className="skeleton h-full w-full" /></div> })
const FinancialDNA = dynamic(() => import('@/components/simulation/FinancialDNA'), { ssr: false, loading: () => <div className="card p-6 h-[320px]"><div className="skeleton h-full w-full" /></div> })
const FinancialTwin = dynamic(() => import('@/components/simulation/FinancialTwin'), { ssr: false, loading: () => <div className="card p-6 h-[200px]"><div className="skeleton h-full w-full" /></div> })

// --- Dynamic imports for chart-heavy components ---
const SankeyHero = dynamic(() => import('@/components/dashboard/SankeyHero'), {
  ssr: false,
  loading: () => (
    <div className="card p-6" aria-busy="true">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="skeleton w-8 h-8" />
          <div className="skeleton h-6 w-48" />
        </div>
        <div className="skeleton h-5 w-32" />
      </div>
      <div className="skeleton h-[400px] w-full" />
    </div>
  ),
})

const TrendChart = dynamic(() => import('@/components/dashboard/TrendChart'), {
  ssr: false,
  loading: () => <div className="card p-6"><div className="skeleton h-[320px] w-full" /></div>,
})

const BreakdownPanel = dynamic(() => import('@/components/dashboard/BreakdownPanel'), {
  ssr: false,
  loading: () => <div className="card p-6"><div className="skeleton h-[260px] w-full" /></div>,
})

const SpendByCategoryBar = dynamic(() => import('@/components/dashboard/SpendByCategoryBar'), {
  ssr: false,
  loading: () => (
    <div className="card p-6" aria-busy="true">
      <div className="skeleton h-6 w-1/3 mb-4" />
      <div className="space-y-3">
        {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-4 w-full" />)}
      </div>
    </div>
  ),
})

const BentoGrid = dynamic(() => import('@/components/dashboard/BentoGrid'), {
  ssr: false,
  loading: () => (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-8">
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="card p-6 h-48"><div className="skeleton h-full w-full" /></div>
      ))}
    </div>
  ),
})

import {
  rulesService,
  classifyCashflow,
  type DashboardSummary,
  type DashboardFlowsResponse,
  type DashboardTrendsResponse,
  type DashboardBreakdownResponse,
  type Profile,
  type Transaction,
  type Account,
  type Category,
  type AnomalyItem,
  type UpcomingBillItem,
  type InsightItem,
} from '@/lib/api'

/**
 * Phase 35 — Money Flow Dashboard Redesign.
 *
 * Data is fetched via `useCachedFetch` (module-level cache with
 * stale-while-revalidate). Navigating away and back shows cached
 * data instantly instead of a loading spinner.
 */
function HomeInner() {
  const [retryCount, setRetryCount] = useState(0)
  const handleRetry = useCallback(() => setRetryCount((c) => c + 1), [])
  const { collapsed } = useSidebar()
  const { timeRange } = useDashboardFilters()

  // Drilldown drawer state
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerTitle, setDrawerTitle] = useState('')
  const [drawerSubtitle, setDrawerSubtitle] = useState<string | undefined>()
  const [drawerContent, setDrawerContent] = useState<ReactNode>(null)

  const openDrilldown = useCallback((title: string, subtitle?: string, content?: React.ReactNode) => {
    setDrawerTitle(title)
    setDrawerSubtitle(subtitle)
    setDrawerContent(content ?? <p className="text-sm text-[var(--text-tertiary)]">No details available.</p>)
    setDrawerOpen(true)
  }, [])
  const closeDrilldown = useCallback(() => setDrawerOpen(false), [])

  // Transactions — fetched early so drilldown handlers can close over them.
  // Also used for rangedRefreshing and coverageDates below.
  const { data: txnData, loading: txnLoading } = useCachedFetch<Transaction[]>(
    'dashboard-transactions',
    () => rulesService.listTransactions({ limit: 100 }),
    [retryCount, timeRange],
    { group: 'dashboard' },
  )
  const transactions = useMemo(() => txnData ?? [], [txnData])

  const handleSegmentClick = useCallback((label: string) => {
    const txns = transactions.filter((t) => {
      if (label === 'Uncategorized') return !t.category_name
      return t.category_name?.toLowerCase() === label.toLowerCase()
    })
    openDrilldown(
      label,
      `${txns.length} transactions`,
      <div className="space-y-2">
        {txns.slice(0, 50).map((t) => (
          <div key={t.id} className="flex items-center justify-between py-2 border-b border-[var(--border-color)]">
            <div className="min-w-0">
              <p className="text-sm text-on-surface truncate">{t.description}</p>
              <p className="text-xs text-tertiary">{t.transaction_date}</p>
            </div>
            <span className={`text-sm font-mono font-semibold ${t.amount < 0 ? 'text-negative' : 'text-positive'}`}>
              {t.amount < 0 ? '-' : '+'}{Math.abs(t.amount).toFixed(2)}
            </span>
          </div>
        ))}
        {txns.length === 0 && <p className="text-sm text-tertiary py-4">No transactions found.</p>}
      </div>,
    )
  }, [transactions, openDrilldown])

  const handleCategoryClick = useCallback((categoryName: string) => {
    const txns = transactions.filter((t) => {
      const name = t.category_name || 'Uncategorized'
      return name.toLowerCase() === categoryName.toLowerCase()
    })
    const total = txns.reduce((s, t) => {
      const cr = classifyCashflow({ amount: t.amount, account_type: t.account_type ?? null, description: t.description ?? null })
      return s + Math.max(0, cr.expenseEffect)
    }, 0)
    openDrilldown(
      categoryName,
      `${txns.length} transactions · ${formatNumber(total)} total`,
      <div className="space-y-2">
        {txns.slice(0, 50).map((t) => (
          <div key={t.id} className="flex items-center justify-between py-2 border-b border-[var(--border-color)]">
            <div className="min-w-0">
              <p className="text-sm text-on-surface truncate">{t.description}</p>
              <p className="text-xs text-tertiary">{t.transaction_date}{t.merchant_name ? ` · ${t.merchant_name}` : ''}</p>
            </div>
            <span className="text-sm font-mono font-semibold text-negative">
              {Math.abs(t.amount).toFixed(2)}
            </span>
          </div>
        ))}
        {txns.length === 0 && <p className="text-sm text-tertiary py-4">No transactions found.</p>}
      </div>,
    )
  }, [transactions, openDrilldown])

  const handleGaugeClick = useCallback((metric: string) => {
    const labels: Record<string, string> = {
      savings: 'Savings Rate',
      debt: 'Debt Load',
      investment: 'Investment Rate',
      cashBuffer: 'Cash Buffer',
    }
    openDrilldown(
      labels[metric] ?? metric,
      'Financial health metric detail',
      <p className="text-sm text-[var(--text-secondary)]">
        Expand the Financial Health card below the chart to see the formula breakdown, numerator/denominator values, and status thresholds for this metric.
      </p>,
    )
  }, [openDrilldown])

  // ---- Cached data fetching -------------------------------------------
  // Each endpoint gets its own useCachedFetch call. The hook handles:
  //   - Module-level caching (survives page navigation)
  //   - Stale-while-revalidate (instant stale data + background refresh)
  //   - DataRefresh integration (uploads/mutations invalidate cache)

  // Static endpoints — only re-fetch on manual retry
  const { data: profileData, loading: profileLoading, errorCause: profileErrorCause } =
    useCachedFetch<Profile>('dashboard-profile', () => rulesService.getProfile(), [retryCount], { group: 'dashboard' })
  const { data: summaryData, loading: summaryLoading, errorCause: summaryErrorCause } =
    useCachedFetch<DashboardSummary>('dashboard-summary', () => rulesService.getDashboardSummary(), [retryCount], { group: 'dashboard' })
  const { data: accountsData, loading: accountsLoading } =
    useCachedFetch<Account[]>('dashboard-accounts', () => rulesService.listAccounts(), [retryCount], { group: 'dashboard' })
  const { data: categoriesData } =
    useCachedFetch<Category[]>('dashboard-categories', () => rulesService.listCategories().catch(() => []), [retryCount], { group: 'dashboard' })
  const { data: anomaliesData } =
    useCachedFetch<{ anomalies: AnomalyItem[]; count: number }>('dashboard-anomalies', () => rulesService.getDashboardAnomalies().catch(() => ({ anomalies: [], count: 0 })), [retryCount], { group: 'dashboard' })
  const { data: billsData } =
    useCachedFetch<{ bills: UpcomingBillItem[]; count: number }>('dashboard-bills', () => rulesService.getDashboardUpcomingBills().catch(() => ({ bills: [], count: 0 })), [retryCount], { group: 'dashboard' })
  const { data: insightsData } =
    useCachedFetch<{ insights: InsightItem[] }>('dashboard-insights', () => rulesService.getDashboardInsights().catch(() => ({ insights: [] })), [retryCount], { group: 'dashboard' })

  // Ranged endpoints — re-fetch on retry OR time range change
  // (transactions are already fetched above for drilldown handlers)
  const { data: flowsData, loading: flowsLoading } =
    useCachedFetch<DashboardFlowsResponse | null>('dashboard-flows', () => {
      const { from, to } = getTimeRangeDates(timeRange)
      return rulesService.getDashboardFlows(from, to).catch(() => null)
    }, [retryCount, timeRange], { group: 'dashboard' })

  const { data: trendsData, loading: trendsLoading } =
    useCachedFetch<DashboardTrendsResponse | null>('dashboard-trends', () => {
      const { from, to } = getTimeRangeDates(timeRange)
      const monthsDiff = Math.min(36, Math.max(1,
        (new Date(to).getFullYear() - new Date(from).getFullYear()) * 12 +
        (new Date(to).getMonth() - new Date(from).getMonth()) + 1,
      ))
      return rulesService.getDashboardTrends(monthsDiff).catch(() => null)
    }, [retryCount, timeRange], { group: 'dashboard' })

  const { data: breakdownData, loading: breakdownLoading } =
    useCachedFetch<DashboardBreakdownResponse | null>('dashboard-breakdown', () => {
      const { from, to } = getTimeRangeDates(timeRange)
      return rulesService.getDashboardBreakdown(from, to).catch(() => null)
    }, [retryCount, timeRange], { group: 'dashboard' })

  // ---- Derived state ---------------------------------------------------
  const profile = profileData ?? null
  const summary = summaryData ?? null
  const accounts = accountsData ?? []
  const categories = useMemo(() => categoriesData ?? [], [categoriesData])
  const anomalies = anomaliesData?.anomalies ?? []
  const upcomingBills = billsData?.bills ?? []
  const insights = insightsData?.insights ?? []
  const flows = flowsData ?? null
  const trends = trendsData ?? null
  const breakdown = breakdownData ?? null

  const errorCause = profileErrorCause ?? summaryErrorCause
  const error = errorCause ? classifyErrorMessage(errorCause) : null
  const loading = profileLoading || summaryLoading || accountsLoading
  const ready = !loading && !!summary
  const rangedRefreshing = flowsLoading || trendsLoading || breakdownLoading || txnLoading

  const categoryColorMap = useMemo(() => {
    const m = new Map<string, string>()
    for (const c of categories) {
      m.set(c.name.toLowerCase(), c.color || 'var(--slate-400)')
    }
    return m
  }, [categories])

  const coverageDates = useMemo(() => {
    if (transactions.length === 0) return { earliest: null, latest: null }
    const dates = transactions.map((t) => t.transaction_date).sort()
    return { earliest: dates[0], latest: dates[dates.length - 1] }
  }, [transactions])

  return (
    <>
      <Sidebar />
      <Header profile={profile} loading={loading} />
      <main
        id="main-content"
        className="p-8 pt-4 transition-all duration-300 ease-in-out ml-[var(--layout-ml)]"
        style={{ '--layout-ml': collapsed ? '4.5rem' : '16rem' } as React.CSSProperties}
      >
        {error && (
          <ErrorBanner
            title="Couldn't load dashboard:"
            message={error}
            variant="warning"
            onRetry={handleRetry}
          />
        )}

        {/* Greeting header (compact) + review badge */}
        <div className="mb-4 flex items-end justify-between flex-wrap gap-3">
          <div>
            <h1 className="headline-xl text-primary mb-1">
              {profile?.full_name ? `Hello, ${profile.full_name}` : 'Hello'}
            </h1>
            <p className="body-md text-secondary">
              {loading || !summary
                ? 'Fetching your latest figures…'
                : summary.transactions_count > 0
                  ? `${summary.transactions_count} transactions tracked across ${summary.accounts_count} accounts.`
                  : 'Connect an account or upload a statement to get started.'}
            </p>
          </div>
          {ready && transactions.length > 0 && (
            <ReviewQueueBadge transactions={transactions} />
          )}
        </div>

        {/* Row 1: AI Wealth Overview hero — net worth + wealth score + tiles.
            No entrance animation — a hero should NOT compete with the chart
            that follows; the surrounding sections do the choreography. */}
        <AIWealthOverview
          summary={ready ? summary : null}
          breakdown={breakdown}
          trends={trends?.trends ?? null}
          loading={!ready || rangedRefreshing}
        />

        {/* Row 2: Sankey Hero — full-width money flow centerpiece.
            Uses fade-in-only (not slideUp) so chart re-renders during
            time-range changes don't feel like a punch-pickup. */}
        <div className="fade-in-only mb-8">
          <SankeyHero
            flows={flows}
            loading={!ready || rangedRefreshing}
          />
        </div>

        {/* Row 2.5: Universe teaser — gateway to 3D financial galaxy.
            Quick fade-in since this is a navigational CTA, not content. */}
        {ready && (
          <AnimatedSection animation="fadeIn" delay={0} className="mb-8">
            <TiltCard>
              <a
                href="/universe"
                className="card flex items-center justify-between p-4 group hover-lift"
                aria-label="Open Financial Universe"
              >
              <div className="flex items-center gap-3">
                <span className="w-10 h-10 rounded-lg bg-[var(--space-800)] flex items-center justify-center">
                  <Orbit className="w-5 h-5 text-[var(--accent-cyan)]" aria-hidden="true" />
                </span>
                <div>
                  <h3 className="headline-md text-primary group-hover:text-[var(--accent-cyan)] transition-colors">
                    Financial Universe
                  </h3>
                  <p className="body-sm text-on-surface-variant">
                    Explore your accounts, goals, and debts as a 3D galaxy.
                  </p>
                </div>
              </div>
              <span className="text-sm font-semibold text-[var(--accent-cyan)] opacity-0 group-hover:opacity-100 transition-opacity">
                Enter →
              </span>
            </a>
            </TiltCard>
          </AnimatedSection>
        )}

        {/* 'Why did this change' insight — fades in alongside the filter bar.
            Per Phase 3, this is part of the same visual band as the filter,
            so they share one fade rather than competing slideUps. */}
        {ready && trends?.trends && trends.trends.length >= 2 && (
          <AnimatedSection animation="fadeIn" delay={50} className="mb-4">
            <WhyDidThisChange trends={trends.trends} className="mb-4" />
          </AnimatedSection>
        )}

        {/* Global filter bar — time range + data coverage */}
        {ready && (
          <GlobalFilterBar
            earliestDate={coverageDates.earliest}
            latestDate={coverageDates.latest}
          />
        )}

        {/* Row 3: Trend Chart (Area) + Breakdown Panel (Stacked Bar).
            Sankey→Breakdown narrative connection: TrendChart at col-2
            (its primary visual area), BreakdownPanel beside it so a click
            on a Breakdown segment naturally scrolls to it from the
            Sankey hover path. */}
        <AnimatedSection animation="fadeIn" delay={100} className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-8">
          <TrendChart
            trends={trends?.trends ?? []}
            loading={!ready || rangedRefreshing}
            className="lg:col-span-2"
          />
          <BreakdownPanel
            breakdown={breakdown}
            trends={trends?.trends ?? null}
            loading={!ready || rangedRefreshing}
            className="lg:col-span-1"
            onSegmentClick={handleSegmentClick}
          />
        </AnimatedSection>

        {/* Row 3.5: Financial Health Gauges + Spending by Category Bar */}
        <AnimatedSection animation="slideUp" delay={250} className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-8">
          <FinancialHealthGauges
            summary={ready ? summary : null}
            breakdown={breakdown}
            trends={trends?.trends ?? null}
            loading={!ready || rangedRefreshing}
            onGaugeClick={handleGaugeClick}
          />
          <SpendByCategoryBar
            transactions={transactions}
            colorByName={categoryColorMap}
            loading={!ready || rangedRefreshing}
            onCategoryClick={handleCategoryClick}
            categories={categories}
          />
        </AnimatedSection>

        {/* Subscriptions & Recurring — detected from transaction patterns */}
        {ready && transactions.length >= 2 && (
          <AnimatedSection animation="slideUp" delay={300} className="mb-8">
            <RecurringTransactions
              transactions={transactions}
              loading={rangedRefreshing}
            />
          </AnimatedSection>
        )}

        {/* Row 4: Financial Plans / Projections */}
        <AnimatedSection animation="slideUp" delay={350}>
          <FinancialPlans summary={ready ? summary : null} loading={!ready} />
        </AnimatedSection>

        {/* Row 4.5: Wealth Simulation Suite (Phase 5)
            Single shared provider so MoneyFlowSimulator / LifeEventSimulator
            state flows into WealthTimeline + FinancialTwin. */}
        {ready && summary && (
          <AnimatedSection animation="slideUp" delay={400}>
            <WealthSimulationProvider
              netWorth={summary.total_balance ?? 0}
              initialMonthlyContribution={
                (summary.total_income_month ?? 0) - (summary.total_expenses_month ?? 0)
              }
              initialAnnualReturnRate={0.07}
            >
              {/* Timeline — full-width centerpiece */}
              <TiltCard className="mb-8" data-testid="simulation-suite">
                <WealthTimeline
                  pastTrends={trends?.trends ?? []}
                  netWorth={summary.total_balance ?? 0}
                  futureYears={10}
                />
              </TiltCard>

              {/* Simulator + Life Events + DNA */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
                <TiltCard className="md:col-span-2">
                  <MoneyFlowSimulator />
                </TiltCard>
                <TiltCard className="md:col-span-1">
                  <LifeEventSimulator />
                </TiltCard>
              </div>

              {/* Twin — full-width narrative row */}
              <TiltCard className="mb-8">
                <FinancialTwin />
              </TiltCard>
            </WealthSimulationProvider>
          </AnimatedSection>
        )}

        {/* Row 4.55: Financial DNA — separate (pure data, not simulator-aware) */}
        {ready && summary && (
          <AnimatedSection animation="slideUp" delay={450} className="mb-8">
            <TiltCard>
              <FinancialDNA summary={summary} />
            </TiltCard>
          </AnimatedSection>
        )}

        {/* Row 4.5: BentoGrid */}
        {ready && (
          <AnimatedSection animation="slideUp" delay={500} className="mt-8">
            <BentoGrid
              summary={summary!}
              accounts={accounts}
              trends={trends}
              breakdown={breakdown}
            />
          </AnimatedSection>
        )}

        {/* Row 4.75: Phase 3 — Asymmetric Bento band.
            CategoryMovers is the wide sentiment strip (text + percentage
            pills + tone-coded borders); AlertsPanel rides its right side
            as a complementary card. The 8+4 split reinforces the brief's
            "one wide sentiment strip" pattern — strip is unmistakably the
            visual center, AlertsPanel is a smaller companion, NOT a
            parallel full-width row (which would flatten the rhythm).
            Falls back gracefully when either side has no data. */}
        {ready && (
          <div className="fade-in-only mt-8 grid grid-cols-1 lg:grid-cols-12 gap-4">
            <div className="min-w-0 lg:col-span-8">
              <CategoryMovers
                insights={insights}
                loading={rangedRefreshing}
                variant="strip"
              />
            </div>
            <div className="min-w-0 lg:col-span-4">
              <AlertsPanel
                anomalies={anomalies}
                upcomingBills={upcomingBills}
                insights={insights}
                loading={rangedRefreshing}
              />
            </div>
          </div>
        )}

        {/* Row 5: Approval Queue */}
        {ready && (
          <AnimatedSection animation="slideUp" delay={600} className="mt-8">
            <ApprovalQueue />
          </AnimatedSection>
        )}

        {/* Row 5: Recent Activity */}
        {ready && (
          <AnimatedSection animation="slideUp" delay={650}>
            <RecentActivity transactions={transactions.slice(0, 10)} loading={false} />
          </AnimatedSection>
        )}
        {!ready && (
          <div className="glass-surface p-8 mt-8 rounded-xl hover-lift" aria-busy="true">
            <div className="skeleton h-6 w-1/4 mb-6" />
            <div className="space-y-3">
              {[0, 1, 2, 3, 4].map((i) => (
                <div key={i} className="skeleton h-10 w-full" />
              ))}
            </div>
          </div>
        )}

        {/* Row 6: System status bar — replaces the identical 4-card grid
            with a single inline strip that still surfaces the same data. */}
        {ready && summary && (
          <AnimatedSection animation="slideUp" delay={700}>
            <div
              className="glass-surface px-5 py-4 rounded-xl flex flex-wrap items-center gap-x-6 gap-y-2 mt-8"
              aria-label="System status"
            >
            <div className="flex items-center gap-2 text-sm">
              <Upload className="w-4 h-4 text-[var(--primary-600)]" aria-hidden="true" />
              <span className="text-[var(--text-tertiary)]">Imports</span>
              <span className="font-semibold text-[var(--text-primary)]">
                {summary.import_batches_count} batch{summary.import_batches_count === 1 ? '' : 'es'}
              </span>
            </div>
            <div className="hidden sm:block w-px h-4 bg-[var(--border-subtle)]" aria-hidden="true" />
            <div className="flex items-center gap-2 text-sm">
              <RefreshCw className="w-4 h-4 text-positive" aria-hidden="true" />
              <span className="text-[var(--text-tertiary)]">Last Sync</span>
              <span className="font-semibold text-[var(--text-primary)]">
                {summary.last_sync
                  ? new Date(summary.last_sync).toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                    })
                  : 'Never'}
              </span>
            </div>
            <div className="hidden sm:block w-px h-4 bg-[var(--border-subtle)]" aria-hidden="true" />
            <div className="flex items-center gap-2 text-sm">
              <Receipt className="w-4 h-4 text-[var(--info-600)]" aria-hidden="true" />
              <span className="text-[var(--text-tertiary)]">Last Import</span>
              <span className="font-semibold text-[var(--text-primary)]">
                {summary.last_import_at
                  ? new Date(summary.last_import_at).toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                    })
                  : 'Never'}
              </span>
            </div>
            <div className="hidden sm:block w-px h-4 bg-[var(--border-subtle)]" aria-hidden="true" />
            <div className="flex items-center gap-2 text-sm">
              <Receipt className="w-4 h-4 text-[var(--warning-600)]" aria-hidden="true" />
              <span className="text-[var(--text-tertiary)]">Transactions</span>
              <span className="font-semibold text-[var(--text-primary)]">
                {summary.transactions_count} tracked
              </span>
            </div>
            </div>
          </AnimatedSection>
        )}
      </main>

      {/* Drilldown drawer */}
      <DrilldownDrawer
        open={drawerOpen}
        onClose={closeDrilldown}
        title={drawerTitle}
        subtitle={drawerSubtitle}
        breadcrumbs={['Dashboard', drawerTitle]}
      >
        {drawerContent}
      </DrilldownDrawer>

      {/* Phase 4 — Persistent AI Copilot (orb + dock) */}
      <CopilotRoot insights={insights} />
    </>
  )
}

export default function Home() {
  return (
    <SidebarProvider>
      <Suspense fallback={null}>
        <DashboardFilterProvider>
          <HomeInner />
        </DashboardFilterProvider>
      </Suspense>
    </SidebarProvider>
  )
}
