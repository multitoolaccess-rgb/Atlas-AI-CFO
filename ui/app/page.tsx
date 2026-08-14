'use client'

import { Suspense, useCallback, useMemo, useState } from 'react'
import dynamic from 'next/dynamic'
import Sidebar from '@/components/layout/Sidebar'
import Header from '@/components/layout/Header'
import { SidebarProvider, useSidebar } from '@/components/layout/SidebarContext'
import AIWealthOverview from '@/components/dashboard/AIWealthOverview'
import AlertsPanel from '@/components/dashboard/AlertsPanel'
import ApprovalQueue from '@/components/dashboard/ApprovalQueue'
import FinancialPlans from '@/components/dashboard/FinancialPlans'
import ReviewQueueBadge from '@/components/dashboard/ReviewQueueBadge'
import ErrorBanner from '@/components/ui/ErrorBanner'
import CopilotRoot from '@/components/copilot/CopilotRoot'
import { WealthSimulationProvider } from '@/components/simulation/WealthSimulationContext'
import { DashboardFilterProvider } from '@/components/dashboard/DashboardFilterContext'
import { useCachedFetch } from '@/lib/cache'
import { classifyErrorMessage } from '@/lib/errors'
import { rulesService, type AnomalyItem, type DashboardSummary, type InsightItem, type Profile, type Transaction, type UpcomingBillItem } from '@/lib/api'

const WealthTimeline = dynamic(() => import('@/components/simulation/WealthTimeline'), { ssr: false })
const MoneyFlowSimulator = dynamic(() => import('@/components/simulation/MoneyFlowSimulator'), { ssr: false })
const LifeEventSimulator = dynamic(() => import('@/components/simulation/LifeEventSimulator'), { ssr: false })
const FinancialDNA = dynamic(() => import('@/components/simulation/FinancialDNA'), { ssr: false })
const FinancialTwin = dynamic(() => import('@/components/simulation/FinancialTwin'), { ssr: false })

/** The cross-domain home deliberately owns only urgent summaries and actions. */
function MissionControl() {
  const { collapsed } = useSidebar()
  const [retryCount, setRetryCount] = useState(0)
  const retry = useCallback(() => setRetryCount((count) => count + 1), [])
  const { data: profile, loading: profileLoading, errorCause: profileError } = useCachedFetch<Profile>('mission-control-profile', () => rulesService.getProfile(), [retryCount], { group: 'mission-control' })
  const { data: summary, loading: summaryLoading, errorCause: summaryError } = useCachedFetch<DashboardSummary>('mission-control-summary', () => rulesService.getDashboardSummary(), [retryCount], { group: 'mission-control' })
  const { data: transactions } = useCachedFetch<Transaction[]>('mission-control-transactions', () => rulesService.listTransactions({ limit: 100 }), [retryCount], { group: 'mission-control' })
  const { data: anomalies } = useCachedFetch<{ anomalies: AnomalyItem[] }>('mission-control-anomalies', () => rulesService.getDashboardAnomalies().catch(() => ({ anomalies: [] })), [retryCount], { group: 'mission-control' })
  const { data: bills } = useCachedFetch<{ bills: UpcomingBillItem[] }>('mission-control-bills', () => rulesService.getDashboardUpcomingBills().catch(() => ({ bills: [] })), [retryCount], { group: 'mission-control' })
  const { data: insights } = useCachedFetch<{ insights: InsightItem[] }>('mission-control-insights', () => rulesService.getDashboardInsights().catch(() => ({ insights: [] })), [retryCount], { group: 'mission-control' })
  const loading = profileLoading || summaryLoading
  const error = profileError ?? summaryError
  const transactionList = useMemo(() => transactions ?? [], [transactions])

  return <>
    <Sidebar /><Header profile={profile ?? null} loading={loading} />
    <main id="main-content" className="atlas-page-main min-w-0 px-4 py-7 sm:px-6 lg:px-10 ml-[var(--layout-ml)]" style={{ '--layout-ml': collapsed ? '4.5rem' : '16rem' } as React.CSSProperties} data-testid="mission-control-page">
      {Boolean(error) && <ErrorBanner title="Couldn't load Mission Control:" message={classifyErrorMessage(error)} variant="warning" onRetry={retry} />}
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3"><div><h1 className="headline-xl text-primary">Mission Control</h1><p className="body-md text-secondary">Your highest-priority financial summaries and actions.</p></div>{transactionList.length > 0 && <ReviewQueueBadge transactions={transactionList} />}</header>
      {loading ? <div className="glass-surface p-8 rounded-xl" aria-busy="true"><div className="skeleton h-6 w-1/4 mb-6" /><div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16 w-full" />)}</div></div> : <div className="space-y-6"><AIWealthOverview summary={summary ?? null} breakdown={null} trends={null} loading={false} /><div className="grid gap-4 lg:grid-cols-2"><AlertsPanel anomalies={anomalies?.anomalies ?? []} upcomingBills={bills?.bills ?? []} insights={insights?.insights ?? []} loading={false} /><ApprovalQueue /></div><FinancialPlans summary={summary ?? null} loading={false} />{summary && <details className="card p-5"><summary className="cursor-pointer font-semibold text-primary">Simulation workspace</summary><p className="mt-2 text-sm text-secondary">Existing planning tools remain available here until Scenario Lab is activated in Step 4.</p><WealthSimulationProvider netWorth={summary.total_balance ?? 0} initialMonthlyContribution={(summary.total_income_month ?? 0) - (summary.total_expenses_month ?? 0)} initialAnnualReturnRate={0.07}><div className="mt-5 space-y-5"><WealthTimeline pastTrends={[]} netWorth={summary.total_balance ?? 0} futureYears={10} /><div className="grid gap-4 lg:grid-cols-2"><MoneyFlowSimulator /><LifeEventSimulator /></div><FinancialDNA summary={summary} /><FinancialTwin /></div></WealthSimulationProvider></details>}</div>}
    </main>
    <CopilotRoot insights={insights?.insights ?? []} />
  </>
}

export default function Home() {
  return <SidebarProvider><Suspense fallback={null}><DashboardFilterProvider><MissionControl /></DashboardFilterProvider></Suspense></SidebarProvider>
}
