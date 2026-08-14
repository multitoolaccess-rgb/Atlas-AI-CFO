'use client'

import { useMemo } from 'react'
import { useSearchParams } from 'next/navigation'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import PageTabs from '@/components/ui/PageTabs'
import AnalyticalContextBar from '@/components/ui/AnalyticalContextBar'
import AnalyticalPageFrame from '@/components/ui/AnalyticalPageFrame'
import { AtlasFilterProvider } from '@/components/ui/AtlasFilterContext'
import RecurringTransactions from '@/components/dashboard/RecurringTransactions'
import BudgetingPage from '@/app/budgeting/page'
import { EmbeddedMoneyView } from '@/components/money/EmbeddedMoneyView'
import { useCachedFetch } from '@/lib/cache'
import { rulesService, type Transaction } from '@/lib/api'

const planTabs = [{ id: 'budget', label: 'Budget' }, { id: 'commitments', label: 'Commitments' }, { id: 'calendar', label: 'Calendar' }] as const

function PlanCommitments({ calendar = false }: { calendar?: boolean }) {
  const { data, loading } = useCachedFetch<Transaction[]>('plan-recurring-transactions', () => rulesService.listTransactions({ limit: 500 }), [], { group: 'plan' })
  const title = calendar ? 'Commitment calendar' : 'Recurring commitments'
  return <AnalyticalPageFrame header={null}
    primaryVisualization={<RecurringTransactions transactions={data ?? []} loading={loading} />}
    attentionRail={<section className="card p-5"><h2 className="headline-sm text-primary">{title}</h2><p className="mt-2 text-sm text-[var(--text-secondary)]">Recurring patterns are detected from your existing transactions. Open the transaction record to confirm timing before making a plan change.</p></section>}
    supportingModules={<p className="text-sm text-[var(--text-secondary)]">This view intentionally does not project or create commitments that are not present in your transaction history.</p>}
  />
}

function PlanWorkspace() {
  const searchParams = useSearchParams()
  const view = planTabs.some((tab) => tab.id === searchParams.get('view')) ? searchParams.get('view')! : 'budget'
  const content = view === 'budget' ? <EmbeddedMoneyView><BudgetingPage /></EmbeddedMoneyView> : <PlanCommitments calendar={view === 'calendar'} />
  return <section className="space-y-6" data-testid="plan-page">
    <PageHeader title="Plan" description="Turn monthly intent into a plan you can still change." />
    <PageTabs tabs={planTabs} activeId={view} queryKey="view" />
    <AnalyticalContextBar showRange={false} pageSlot={<span className="text-xs text-[var(--text-secondary)]">Plan period stays authoritative in Budget.</span>} coverage={<span>Existing account data</span>} freshness={<span>URL-synced</span>} />
    {content}
  </section>
}

export default function PlanPage() {
  return <PageLayout><AtlasFilterProvider><PlanWorkspace /></AtlasFilterProvider></PageLayout>
}
