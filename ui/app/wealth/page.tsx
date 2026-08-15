'use client'

import dynamic from 'next/dynamic'
import { useSearchParams } from 'next/navigation'
import { ArrowRight, Orbit, Wallet } from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import PageTabs from '@/components/ui/PageTabs'
import AnalyticalContextBar from '@/components/ui/AnalyticalContextBar'
import AnalyticalPageFrame from '@/components/ui/AnalyticalPageFrame'
import { AtlasFilterProvider } from '@/components/ui/AtlasFilterContext'
import EmptyState from '@/components/ui/EmptyState'
import AccountAllocation from '@/components/dashboard/AccountAllocation'
import DebtsContent from '@/components/debts/DebtsContent'
import { useCachedFetch } from '@/lib/cache'
import { formatNumber } from '@/lib/format'
import { rulesService, type Account, type DebtItem, type DashboardSummary, type Goal, type Holding } from '@/lib/api'

const FinancialUniverse = dynamic(() => import('@/components/universe/FinancialUniverse'), {
  ssr: false,
  loading: () => <div className="card h-[600px] flex items-center justify-center" aria-busy="true"><div className="skeleton h-full w-full" /></div>,
})

const wealthTabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'assets', label: 'Assets' },
  { id: 'debts', label: 'Debts' },
  { id: 'universe', label: 'Universe view' },
] as const

type WealthView = (typeof wealthTabs)[number]['id']

function useWealthData() {
  const summary = useCachedFetch<DashboardSummary>('wealth-summary', () => rulesService.getDashboardSummary(), [], { group: 'wealth' })
  const accounts = useCachedFetch<Account[]>('wealth-accounts', () => rulesService.listAccounts(), [], { group: 'wealth' })
  const holdings = useCachedFetch<Holding[]>('wealth-holdings', () => rulesService.listHoldings(), [], { group: 'wealth' })
  const goals = useCachedFetch<Goal[]>('wealth-goals', () => rulesService.listGoals(), [], { group: 'wealth' })
  const debts = useCachedFetch<DebtItem[]>('wealth-debts', () => rulesService.getDebtsSummary().then((result) => result.debts), [], { group: 'wealth' })
  return { summary, accounts, holdings, goals, debts }
}

function WealthOverview({ summary, accounts, debts, goals }: { summary: DashboardSummary | null; accounts: Account[]; debts: DebtItem[]; goals: Goal[] }) {
  const netWorth = summary?.total_balance ?? 0
  const totalDebt = debts.reduce((total, debt) => total + debt.balance, 0)
  const activeGoals = goals.length
  return <AnalyticalPageFrame
    header={null}
    positionStrip={<div className="grid grid-cols-1 gap-3 sm:grid-cols-3" data-testid="wealth-position-strip">
      <section className="card p-5"><p className="label-sm text-tertiary">Net worth</p><p className="numeric-lg text-primary mt-2">{formatNumber(netWorth)}</p><p className="text-xs text-secondary mt-1">Authoritative account balance total</p></section>
      <section className="card p-5"><p className="label-sm text-tertiary">Debt exposure</p><p className="numeric-lg text-danger mt-2">{formatNumber(totalDebt)}</p><p className="text-xs text-secondary mt-1">{debts.length} debt account{debts.length === 1 ? '' : 's'}</p></section>
      <section className="card p-5"><p className="label-sm text-tertiary">Goals in view</p><p className="numeric-lg text-primary mt-2">{activeGoals}</p><p className="text-xs text-secondary mt-1">Open the specialist Goals workspace for forecasts</p></section>
    </div>}
    primaryVisualization={<AccountAllocation accounts={accounts} totalBalance={netWorth} loading={false} />}
    attentionRail={<section className="card p-5"><h2 className="headline-sm text-primary">Where to go next</h2><div className="mt-4 space-y-3 text-sm"><a className="flex items-center justify-between gap-3 text-secondary hover:text-primary" href="/wealth?view=assets">Review account and asset coverage <ArrowRight className="h-4 w-4" aria-hidden="true" /></a><a className="flex items-center justify-between gap-3 text-secondary hover:text-primary" href="/portfolio">Open Portfolio analysis <ArrowRight className="h-4 w-4" aria-hidden="true" /></a><a className="flex items-center justify-between gap-3 text-secondary hover:text-primary" href="/goals">Open Goals and forecasts <ArrowRight className="h-4 w-4" aria-hidden="true" /></a></div></section>}
    supportingModules={<p className="text-sm text-secondary">This overview intentionally keeps only bounded wealth signals. Full holdings analysis, debt payoff analysis, goal projections, and the Universe visualization live in their specialist views.</p>}
  />
}

function AssetsView({ accounts, holdings }: { accounts: Account[]; holdings: Holding[] }) {
  const total = accounts.reduce((sum, account) => sum + account.current_balance, 0)
  return <AnalyticalPageFrame
    header={null}
    primaryVisualization={<section className="space-y-4"><AccountAllocation accounts={accounts} totalBalance={total} loading={false} /><section className="card overflow-hidden"><div className="p-5 border-b border-[var(--border-color)]"><h2 className="headline-sm text-primary">Asset positions</h2><p className="text-sm text-secondary mt-1">Imported holdings remain authoritative in Portfolio; this tab is a compact coverage view.</p></div>{holdings.length === 0 ? <EmptyState testId="wealth-assets-empty" icon={<Wallet className="h-6 w-6" />} title="No asset positions found" description="Connect an investment account or import a portfolio statement to see positions here." action={<a href="/data-connections?view=accounts" className="btn-primary inline-flex items-center px-4 py-2 text-sm font-semibold">Open Accounts</a>} /> : <div className="overflow-x-auto"><table className="w-full text-sm"><caption className="sr-only">Asset position summary</caption><thead><tr className="text-left text-xs text-tertiary border-b border-[var(--border-color)]"><th className="px-5 py-3">Position</th><th className="px-5 py-3">Account</th><th className="px-5 py-3 text-right">Value</th></tr></thead><tbody>{holdings.slice(0, 12).map((holding) => <tr key={holding.id} className="border-b border-[var(--border-color)] last:border-0"><td className="px-5 py-3 font-medium text-primary">{holding.symbol || holding.description || 'Unlabeled position'}</td><td className="px-5 py-3 text-secondary">{accounts.find((account) => account.id === holding.account_id)?.account_name ?? 'Account unavailable'}</td><td className="px-5 py-3 text-right tabular-nums text-primary">{formatNumber(holding.live_value ?? holding.current_value)}</td></tr>)}</tbody></table>{holdings.length > 12 && <p className="p-4 text-xs text-secondary">Showing 12 positions. Open Portfolio for the complete holdings table.</p>}</div>}</section></section>}
    attentionRail={<section className="card p-5"><h2 className="headline-sm text-primary">Specialist analysis</h2><p className="text-sm text-secondary mt-2">Allocation, performance, risk, analyst coverage, and holding actions have one authoritative home in Portfolio.</p><a href="/portfolio" className="btn-secondary inline-flex items-center gap-2 mt-4 px-3 py-2 text-sm">Open Portfolio <ArrowRight className="h-4 w-4" aria-hidden="true" /></a></section>}
  />
}

function UniverseView({ accounts, goals, debts, error }: { accounts: Account[]; goals: Goal[]; debts: DebtItem[]; error?: string }) {
  if (error) return <section role="alert" className="card p-6 border border-warning-300"><h2 className="headline-sm text-primary">Universe data unavailable</h2><p className="text-sm text-secondary mt-2">Atlas could not load the source records for this view. No visualization is shown until the source data is available.</p></section>
  return <section className="space-y-3"><div className="flex items-center gap-2 text-sm text-secondary"><Orbit className="h-4 w-4" aria-hidden="true" />Optional visual mode for accounts, goals, and debts. The underlying records remain the source of truth.</div><FinancialUniverse accounts={accounts} goals={goals} debts={debts} /></section>
}

function WealthWorkspace() {
  const searchParams = useSearchParams()
  const requested = searchParams.get('view')
  const view: WealthView = wealthTabs.some((tab) => tab.id === requested) ? requested as WealthView : 'overview'
  const { summary, accounts, holdings, goals, debts } = useWealthData()
  const dataError = summary.error ?? accounts.error ?? holdings.error ?? goals.error ?? debts.error
  const loading = summary.loading || accounts.loading || holdings.loading || goals.loading || debts.loading
  const content = loading ? <AnalyticalPageFrame header={null} state="loading" stateSlot={<p className="card p-6 text-sm text-secondary" role="status">Loading Wealth data…</p>} /> : dataError && view !== 'universe' ? <AnalyticalPageFrame header={null} state="error" stateSlot={<section className="card p-6"><h2 className="headline-sm text-primary">Wealth data unavailable</h2><p className="text-sm text-secondary mt-2">Atlas could not load the source records for this view. Try again from the source page or return later.</p></section>} /> : view === 'overview' ? <WealthOverview summary={summary.data} accounts={accounts.data ?? []} debts={debts.data ?? []} goals={goals.data ?? []} /> : view === 'assets' ? <AssetsView accounts={accounts.data ?? []} holdings={holdings.data ?? []} /> : view === 'debts' ? <DebtsContent embedded /> : <UniverseView accounts={accounts.data ?? []} goals={goals.data ?? []} debts={debts.data ?? []} error={dataError ?? undefined} />
  return <section data-testid="wealth-page" className="space-y-6"><PageHeader title="Wealth" description="See your balance sheet, assets, liabilities, and long-term position in one place." /><PageTabs tabs={wealthTabs} activeId={view} queryKey="view" /><AnalyticalContextBar showRange={false} pageSlot={<span className="text-xs text-secondary">Wealth tabs preserve source-specific filters.</span>} coverage={<span>{accounts.data?.length ?? 0} accounts</span>} freshness={<span>Source records</span>} />{content}</section>
}

export default function WealthPage() {
  return <PageLayout><AtlasFilterProvider><WealthWorkspace /></AtlasFilterProvider></PageLayout>
}
