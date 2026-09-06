'use client'

import { useState, useEffect, useCallback, useMemo, type ReactNode } from 'react'
import PageLayout from '@/components/layout/PageLayout'
import { GlobalFilterProvider, useGlobalFilters, dateRangeFromPreset } from '@/components/ui/GlobalFilterContext'
import FloatingTimeRangeBar from '@/components/ui/FloatingTimeRangeBar'
import PageHeader from '@/components/ui/PageHeader'
import { useEmbeddedMoneyView } from '@/components/money/EmbeddedMoneyView'
import {
  rulesService,
  type IncomeBreakdownResponse,
  type Transaction,
} from '@/lib/api'
import DrilldownDrawer from '@/components/dashboard/DrilldownDrawer'
import GroupDonutCard from '@/components/dashboard/GroupDonutCard'
import MonthlyTrendCard from '@/components/dashboard/MonthlyTrendCard'
import CategoryBreakdownCard, { type CategoryBreakdownItem } from '@/components/dashboard/CategoryBreakdownCard'
import type { DonutDatum } from '@/components/charts/SimpleDonutChart'
import { useThemeColors, resolveGroupColor } from '@/lib/themeColors'
import { formatCurrency, formatMonthLabel } from '@/lib/format'
import {
  DollarSign,
  Calendar,
  Layers,
} from 'lucide-react'

function IncomeContent({ embedded = false }: { embedded?: boolean }) {
  // The floating bar reads timeRange from the unified context; this
  // page only consumes timeRange to pass into the BE range query.
  const { timeRange } = useGlobalFilters()
  const tc = useThemeColors()
  const [data, setData] = useState<IncomeBreakdownResponse | null>(null)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const { from, to } = dateRangeFromPreset(timeRange)
      const [result, txns] = await Promise.all([
        rulesService.getIncomeBreakdown(from, to),
        rulesService.listTransactions({ limit: 500, sort_by: 'transaction_date', sort_dir: 'desc', from_date: from, to_date: `${to}T23:59:59.999999` }),
      ])
      setData(result)
      setTransactions(txns)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load income data')
    } finally {
      setLoading(false)
    }
  }, [timeRange])

  useEffect(() => { loadData() }, [loadData])

  const formatDisplay = useCallback((n: number) => formatCurrency(n), [])

  // Canonical theme-aware hex colors — the same vocabulary the Overview
  // dashboard uses (Sankey groups / breakdown donut), so income/spending
  // charts stay visually aligned. Unknown group keys resolve to a stable
  // palette color instead of falling back to a single gray.
  const donutData: DonutDatum[] = useMemo(
    () =>
      data
        ? data.by_group.map((g) => ({
            id: g.group,
            name: g.group.charAt(0).toUpperCase() + g.group.slice(1),
            value: g.amount,
            color: resolveGroupColor(g.group, tc),
          }))
        : [],
    [data, tc],
  )

  const categoryItems: CategoryBreakdownItem[] = useMemo(
    () =>
      data
        ? data.by_category.map((c) => ({
            id: String(c.category_id),
            name: c.category_name,
            amount: c.amount,
            color: resolveGroupColor(c.budget_group, tc),
            group: c.budget_group,
          }))
        : [],
    [data, tc],
  )

  const recentMonths = useMemo(() => {
    if (!data) return []
    return data.trend.slice(-6)
  }, [data])

  const openGroupDrilldown = useCallback((d: DonutDatum) => {
    const groupTxns = transactions.filter((t) => {
      const cat = data?.by_category.find((c) => c.category_name === t.category_name)
      return cat?.budget_group === d.id
    })
    openDrilldown(
      `${d.name} Income`,
      `${groupTxns.length} transactions · ${formatDisplay(d.value)}`,
      <div className="space-y-2">
        {groupTxns.slice(0, 50).map((t) => (
          <div key={t.id} className="flex items-center justify-between py-2 border-b border-[var(--border-subtle)]">
            <div className="min-w-0">
              <p className="text-sm text-[var(--text-primary)] truncate">{t.description}</p>
              <p className="text-xs text-[var(--text-secondary)]">{t.transaction_date}{t.merchant_name ? ` · ${t.merchant_name}` : ''}</p>
            </div>
            <span className="text-sm font-mono font-semibold text-[var(--success-600)]">
              +{formatDisplay(Math.abs(t.amount))}
            </span>
          </div>
        ))}
        {groupTxns.length === 0 && <p className="text-sm text-[var(--text-secondary)] py-4">No transactions found.</p>}
      </div>,
    )
  }, [transactions, data, openDrilldown, formatDisplay])

  const openMonthDrilldown = useCallback((month: string) => {
    const monthTxns = transactions.filter((t) => t.transaction_date?.startsWith(month))
    openDrilldown(
      `Income in ${formatMonthLabel(month)}`,
      `${monthTxns.length} transactions · ${formatDisplay(monthTxns.reduce((s, t) => s + Math.abs(t.amount), 0))}`,
      <div className="space-y-2">
        {monthTxns.slice(0, 50).map((t) => (
          <div key={t.id} className="flex items-center justify-between py-2 border-b border-[var(--border-subtle)]">
            <div className="min-w-0">
              <p className="text-sm text-[var(--text-primary)] truncate">{t.description}</p>
              <p className="text-xs text-[var(--text-secondary)]">{t.transaction_date}{t.merchant_name ? ` · ${t.merchant_name}` : ''}</p>
            </div>
            <span className="text-sm font-mono font-semibold text-[var(--success-600)]">
              +{formatDisplay(Math.abs(t.amount))}
            </span>
          </div>
        ))}
        {monthTxns.length === 0 && <p className="text-sm text-[var(--text-secondary)] py-4">No transactions found.</p>}
      </div>,
    )
  }, [transactions, openDrilldown, formatDisplay])

  const openCategoryDrilldown = useCallback((item: CategoryBreakdownItem) => {
    const catTxns = transactions.filter((t) =>
      (t.category_name || 'Uncategorized').toLowerCase() === item.name.toLowerCase()
    )
    openDrilldown(
      item.name,
      `${catTxns.length} transactions · ${formatDisplay(item.amount)}`,
      <div className="space-y-2">
        {catTxns.slice(0, 50).map((t) => (
          <div key={t.id} className="flex items-center justify-between py-2 border-b border-[var(--border-subtle)]">
            <div className="min-w-0">
              <p className="text-sm text-[var(--text-primary)] truncate">{t.description}</p>
              <p className="text-xs text-[var(--text-secondary)]">{t.transaction_date}{t.merchant_name ? ` · ${t.merchant_name}` : ''}</p>
            </div>
            <span className="text-sm font-mono font-semibold text-[var(--success-600)]">
              +{formatDisplay(Math.abs(t.amount))}
            </span>
          </div>
        ))}
        {catTxns.length === 0 && <p className="text-sm text-[var(--text-secondary)] py-4">No transactions found.</p>}
      </div>,
    )
  }, [transactions, openDrilldown, formatDisplay])

  return (
    <div className="space-y-8">
      {!embedded && <><PageHeader title="Income" description="Track all income sources and trends." /><FloatingTimeRangeBar /></>}

      {error && (
        <div className="flex items-center gap-3 p-4 rounded-lg border border-[var(--danger-200)] bg-[var(--danger-50)]">
          <p className="text-sm text-[var(--danger-700)]">{error}</p>
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="card p-6 animate-pulse">
              <div className="skeleton h-4 w-1/2 mb-3" />
              <div className="skeleton h-8 w-3/4" />
            </div>
          ))}
        </div>
      ) : data ? (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="card p-6 relative overflow-hidden transition-all duration-200">
              <div className="flex items-start justify-between mb-3">
                <p className="label-sm text-tertiary">Total Income</p>
                <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${tc.income_accent}24` }}>
                  <DollarSign className="w-4 h-4" style={{ color: tc.income_accent }} />
                </div>
              </div>
              <p className="headline-xl text-[var(--text-primary)] mb-1 font-bold tracking-tight">{formatDisplay(data.total_income)}</p>
            </div>
            <div className="card p-6 relative overflow-hidden transition-all duration-200">
              <div className="flex items-start justify-between mb-3">
                <p className="label-sm text-tertiary">Sources</p>
                <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${tc.invest}24` }}>
                  <Layers className="w-4 h-4" style={{ color: tc.invest }} />
                </div>
              </div>
              <p className="headline-xl text-[var(--text-primary)] mb-1 font-bold tracking-tight">{data.by_category.length}</p>
            </div>
            <div className="card p-6 relative overflow-hidden transition-all duration-200">
              <div className="flex items-start justify-between mb-3">
                <p className="label-sm text-tertiary">Groups</p>
                <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${tc.flexible}24` }}>
                  <Calendar className="w-4 h-4" style={{ color: tc.flexible }} />
                </div>
              </div>
              <p className="headline-xl text-[var(--text-primary)] mb-1 font-bold tracking-tight">{data.by_group.length}</p>
            </div>
          </div>

          {/* Income by Group */}
          {data.by_group.length > 0 && (
            <GroupDonutCard
              title="Income by Group"
              totalLabel="Total Income"
              data={donutData}
              total={data.total_income}
              onSelect={openGroupDrilldown}
            />
          )}

          {/* Monthly Trend */}
          {recentMonths.length > 0 && (
            <MonthlyTrendCard
              title="Monthly Income"
              seriesName="Income"
              points={recentMonths}
              color={tc.income_accent}
              onSelect={openMonthDrilldown}
            />
          )}

          {/* Income Sources */}
          {categoryItems.length > 0 && (
            <CategoryBreakdownCard
              title="Income Sources"
              subtitle={`${categoryItems.length} sources · ${formatDisplay(data.total_income)}`}
              items={categoryItems}
              total={data.total_income}
              onSelect={openCategoryDrilldown}
            />
          )}
        </>
      ) : null}

      {/* Drilldown drawer — right-side slide-out for transaction detail */}
      <DrilldownDrawer
        open={drawerOpen}
        onClose={closeDrilldown}
        title={drawerTitle}
        subtitle={drawerSubtitle}
        breadcrumbs={['Income', drawerTitle]}
      >
        {drawerContent}
      </DrilldownDrawer>
    </div>
  )
}

export default function IncomePage() {
  const embedded = useEmbeddedMoneyView()
  if (embedded) return <IncomeContent embedded />
  return (
    <PageLayout>
      <GlobalFilterProvider>
        <IncomeContent />
      </GlobalFilterProvider>
    </PageLayout>
  )
}