'use client'

import { Suspense, useCallback, useMemo, useState } from 'react'
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
import { DashboardFilterProvider } from '@/components/dashboard/DashboardFilterContext'
import { useCachedFetch } from '@/lib/cache'
import { classifyErrorMessage } from '@/lib/errors'
import { rulesService, type AnomalyItem, type DashboardSummary, type InsightItem, type Profile, type Transaction, type UpcomingBillItem } from '@/lib/api'


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
      {loading ? <div className="glass-surface p-8 rounded-xl" aria-busy="true"><div className="skeleton h-6 w-1/4 mb-6" /><div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16 w-full" />)}</div></div> : <div className="space-y-6"><AIWealthOverview summary={summary ?? null} breakdown={null} trends={null} loading={false} /><div className="grid gap-4 lg:grid-cols-2"><AlertsPanel anomalies={anomalies?.anomalies ?? []} upcomingBills={bills?.bills ?? []} insights={insights?.insights ?? []} loading={false} /><ApprovalQueue /></div><FinancialPlans summary={summary ?? null} loading={false} /><section className="card flex flex-wrap items-center justify-between gap-4 p-5" data-testid="scenario-lab-promo"><div><p className="label-md text-secondary">Need a what-if?</p><h2 className="mt-1 headline-sm text-primary">Use the server-backed Scenario Lab</h2><p className="mt-1 max-w-2xl text-sm leading-6 text-secondary">Model one supported, goal-scoped change against an immutable baseline. Results are deterministic analysis, not execution.</p></div><a href="/scenario-lab" className="btn-primary inline-flex min-h-11 items-center px-4 py-2 text-sm">Open Scenario Lab</a></section></div>}
    </main>
    <CopilotRoot insights={insights?.insights ?? []} />
  </>
}

export default function Home() {
  return <SidebarProvider><Suspense fallback={null}><DashboardFilterProvider><MissionControl /></DashboardFilterProvider></Suspense></SidebarProvider>
}
