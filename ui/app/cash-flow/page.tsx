'use client'

import dynamic from 'next/dynamic'
import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { useSearchParams } from 'next/navigation'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import PageTabs from '@/components/ui/PageTabs'
import AnalyticalContextBar from '@/components/ui/AnalyticalContextBar'
import AnalyticalPageFrame from '@/components/ui/AnalyticalPageFrame'
import { AtlasFilterProvider, useAtlasFilters } from '@/components/ui/AtlasFilterContext'
import { getTimeRangeDates } from '@/components/ui/TimeRangeSelector'
import CashFlowAnalysis from '@/components/dashboard/CashFlowAnalysis'
import DrilldownDrawer from '@/components/dashboard/DrilldownDrawer'
import IncomePage from '@/app/income/page'
import ExpensesPage from '@/app/expenses/page'
import ActivityPage from '@/app/activity/page'
import { EmbeddedMoneyView } from '@/components/money/EmbeddedMoneyView'
import { useCachedFetch } from '@/lib/cache'
import { formatNumber } from '@/lib/format'
import {
  classifyCashflow,
  rulesService,
  type Category,
  type DashboardBreakdownResponse,
  type DashboardFlowsResponse,
  type DashboardSummary,
  type DashboardTrendsResponse,
  type Transaction,
} from '@/lib/api'

const SankeyHero = dynamic(() => import('@/components/dashboard/SankeyHero'), { ssr: false })
const TrendChart = dynamic(() => import('@/components/dashboard/TrendChart'), { ssr: false })
const BreakdownPanel = dynamic(() => import('@/components/dashboard/BreakdownPanel'), { ssr: false })
const FinancialHealthGauges = dynamic(() => import('@/components/dashboard/FinancialHealthGauges'), { ssr: false })
const SpendByCategoryBar = dynamic(() => import('@/components/dashboard/SpendByCategoryBar'), { ssr: false })

const cashFlowTabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'income', label: 'Income' },
  { id: 'spending', label: 'Spending' },
  { id: 'transactions', label: 'Transactions' },
] as const

function CashFlowOverview() {
  const { timeRange } = useAtlasFilters()
  const { from, to } = useMemo(() => getTimeRangeDates(timeRange), [timeRange])
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerTitle, setDrawerTitle] = useState('')
  const [drawerSubtitle, setDrawerSubtitle] = useState<string | undefined>()
  const [drawerContent, setDrawerContent] = useState<ReactNode>(null)
  const { data: summary, loading: summaryLoading } = useCachedFetch<DashboardSummary>(
    'cash-flow-summary', () => rulesService.getDashboardSummary(), [timeRange], { group: 'cash-flow' },
  )
  const { data: flows, loading: flowsLoading } = useCachedFetch<DashboardFlowsResponse>(
    'cash-flow-flows', () => rulesService.getDashboardFlows(from, to), [from, to], { group: 'cash-flow' },
  )
  const { data: trends, loading: trendsLoading } = useCachedFetch<DashboardTrendsResponse | null>(
    'cash-flow-trends', () => {
      const months = Math.min(36, Math.max(1, (new Date(to).getFullYear() - new Date(from).getFullYear()) * 12 + new Date(to).getMonth() - new Date(from).getMonth() + 1))
      return rulesService.getDashboardTrends(months).catch(() => null)
    }, [from, to], { group: 'cash-flow' },
  )
  const { data: breakdown, loading: breakdownLoading } = useCachedFetch<DashboardBreakdownResponse | null>(
    'cash-flow-breakdown', () => rulesService.getDashboardBreakdown(from, to).catch(() => null), [from, to], { group: 'cash-flow' },
  )
  const { data: transactionData, loading: transactionsLoading } = useCachedFetch<Transaction[]>(
    'cash-flow-transactions', () => rulesService.listTransactions({ limit: 100 }), [timeRange], { group: 'cash-flow' },
  )
  const { data: categoryData } = useCachedFetch<Category[]>(
    'cash-flow-categories', () => rulesService.listCategories().catch(() => []), [], { group: 'cash-flow' },
  )
  const transactions = useMemo(() => transactionData ?? [], [transactionData])
  const categories = useMemo(() => categoryData ?? [], [categoryData])
  const colorByName = useMemo(() => new Map(categories.map((category) => [category.name.toLowerCase(), category.color || 'var(--slate-400)'])), [categories])
  const openDrilldown = useCallback((title: string, subtitle: string, content: ReactNode) => {
    setDrawerTitle(title)
    setDrawerSubtitle(subtitle)
    setDrawerContent(content)
    setDrawerOpen(true)
  }, [])
  const transactionRows = useCallback((items: Transaction[], amountClass: string) => <div className="space-y-2">{items.slice(0, 50).map((transaction) => <div key={transaction.id} className="flex items-center justify-between border-b border-[var(--border-color)] py-2"><div className="min-w-0"><p className="truncate text-sm text-on-surface">{transaction.description}</p><p className="text-xs text-tertiary">{transaction.transaction_date}{transaction.merchant_name ? ` · ${transaction.merchant_name}` : ''}</p></div><span className={`font-mono text-sm font-semibold ${amountClass}`}>{transaction.amount < 0 ? '-' : '+'}{Math.abs(transaction.amount).toFixed(2)}</span></div>)}{items.length === 0 && <p className="py-4 text-sm text-tertiary">No transactions found.</p>}</div>, [])
  const handleSegmentClick = useCallback((label: string) => {
    const matching = transactions.filter((transaction) => label === 'Uncategorized' ? !transaction.category_name : transaction.category_name?.toLowerCase() === label.toLowerCase())
    openDrilldown(label, `${matching.length} transactions`, transactionRows(matching, 'text-on-surface'))
  }, [openDrilldown, transactionRows, transactions])
  const handleCategoryClick = useCallback((categoryName: string) => {
    const matching = transactions.filter((transaction) => (transaction.category_name || 'Uncategorized').toLowerCase() === categoryName.toLowerCase())
    const total = matching.reduce((sum, transaction) => sum + Math.max(0, classifyCashflow({ amount: transaction.amount, account_type: transaction.account_type ?? null, description: transaction.description ?? null }).expenseEffect), 0)
    openDrilldown(categoryName, `${matching.length} transactions · ${formatNumber(total)} total`, transactionRows(matching, 'text-negative'))
  }, [openDrilldown, transactionRows, transactions])
  const handleGaugeClick = useCallback((metric: string) => {
    const labels: Record<string, string> = { savings: 'Savings Rate', debt: 'Debt Load', investment: 'Investment Rate', cashBuffer: 'Cash Buffer' }
    openDrilldown(labels[metric] ?? metric, 'Financial health metric detail', <p className="text-sm text-[var(--text-secondary)]">Expand the Financial Health card for the formula breakdown, numerator, denominator, and status thresholds for this metric.</p>)
  }, [openDrilldown])
  const loading = summaryLoading || flowsLoading || trendsLoading || breakdownLoading || transactionsLoading
  return <><AnalyticalPageFrame header={null}
    primaryVisualization={<SankeyHero flows={flows ?? null} loading={flowsLoading} />}
    attentionRail={<CashFlowAnalysis summary={summary ?? null} loading={summaryLoading} />}
    supportingModules={<div className="space-y-4"><div className="grid gap-4 lg:grid-cols-3"><TrendChart trends={trends?.trends ?? []} loading={loading} className="lg:col-span-2" /><BreakdownPanel breakdown={breakdown ?? null} trends={trends?.trends ?? null} loading={loading} onSegmentClick={handleSegmentClick} /></div><div className="grid gap-4 lg:grid-cols-2"><FinancialHealthGauges summary={summary ?? null} breakdown={breakdown ?? null} trends={trends?.trends ?? null} loading={loading} onGaugeClick={handleGaugeClick} /><SpendByCategoryBar transactions={transactions} colorByName={colorByName} categories={categories} loading={loading} onCategoryClick={handleCategoryClick} /></div><p className="text-sm text-[var(--text-secondary)]">Select Income, Spending, or Transactions for the authoritative detail behind this flow.</p></div>}
    drilldown={{ title: 'Cash Flow detail', preserveFilterContext: true }}
  /><DrilldownDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title={drawerTitle} subtitle={drawerSubtitle} breadcrumbs={['Cash Flow', drawerTitle]}>{drawerContent}</DrilldownDrawer></>
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
