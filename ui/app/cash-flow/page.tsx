'use client'

import dynamic from 'next/dynamic'
import { useMemo } from 'react'
import { useSearchParams } from 'next/navigation'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import PageTabs from '@/components/ui/PageTabs'
import AnalyticalContextBar from '@/components/ui/AnalyticalContextBar'
import AnalyticalPageFrame from '@/components/ui/AnalyticalPageFrame'
import { AtlasFilterProvider, useAtlasFilters } from '@/components/ui/AtlasFilterContext'
import { getTimeRangeDates } from '@/components/ui/TimeRangeSelector'
import CashFlowAnalysis from '@/components/dashboard/CashFlowAnalysis'
import IncomePage from '@/app/income/page'
import ExpensesPage from '@/app/expenses/page'
import ActivityPage from '@/app/activity/page'
import { EmbeddedMoneyView } from '@/components/money/EmbeddedMoneyView'
import { useCachedFetch } from '@/lib/cache'
import { rulesService, type DashboardFlowsResponse, type DashboardSummary } from '@/lib/api'

const SankeyHero = dynamic(() => import('@/components/dashboard/SankeyHero'), { ssr: false })

const cashFlowTabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'income', label: 'Income' },
  { id: 'spending', label: 'Spending' },
  { id: 'transactions', label: 'Transactions' },
] as const

function CashFlowOverview() {
  const { timeRange } = useAtlasFilters()
  const { from, to } = useMemo(() => getTimeRangeDates(timeRange), [timeRange])
  const { data: summary, loading: summaryLoading } = useCachedFetch<DashboardSummary>(
    'cash-flow-summary', () => rulesService.getDashboardSummary(), [timeRange], { group: 'cash-flow' },
  )
  const { data: flows, loading: flowsLoading } = useCachedFetch<DashboardFlowsResponse>(
    'cash-flow-flows', () => rulesService.getDashboardFlows(from, to), [from, to], { group: 'cash-flow' },
  )
  return <AnalyticalPageFrame header={null}
    primaryVisualization={<SankeyHero flows={flows ?? null} loading={flowsLoading} />}
    attentionRail={<CashFlowAnalysis summary={summary ?? null} loading={summaryLoading} />}
    supportingModules={<p className="text-sm text-[var(--text-secondary)]">Select Income, Spending, or Transactions for the authoritative detail behind this flow.</p>}
  />
}

function CashFlowWorkspace() {
  const searchParams = useSearchParams()
  const view = cashFlowTabs.some((tab) => tab.id === searchParams.get('view')) ? searchParams.get('view')! : 'overview'
  const content = view === 'income' ? <EmbeddedMoneyView><IncomePage /></EmbeddedMoneyView>
    : view === 'spending' ? <EmbeddedMoneyView><ExpensesPage /></EmbeddedMoneyView>
      : view === 'transactions' ? <EmbeddedMoneyView><ActivityPage /></EmbeddedMoneyView> : <CashFlowOverview />
  return <section className="space-y-6" data-testid="cash-flow-page">
    <PageHeader title="Cash Flow" description="Understand what came in, where it went, and what remains available." />
    <PageTabs tabs={cashFlowTabs} activeId={view} queryKey="view" />
    <AnalyticalContextBar showCompare coverage={<span>Range applies to Money data</span>} freshness={<span>URL-synced</span>} />
    {content}
  </section>
}

export default function CashFlowPage() {
  return <PageLayout><AtlasFilterProvider><CashFlowWorkspace /></AtlasFilterProvider></PageLayout>
}
