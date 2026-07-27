'use client'

import { useState, useEffect, useCallback, useMemo, type ReactNode } from 'react'
import PageLayout from '@/components/layout/PageLayout'
import { GlobalFilterProvider, useGlobalFilters, dateRangeFromPreset } from '@/components/ui/GlobalFilterContext'
import FloatingTimeRangeBar from '@/components/ui/FloatingTimeRangeBar'
import {
  rulesService,
  type ExpenseBreakdownResponse,
  type Transaction,
} from '@/lib/api'
import MerchantSpendTable from '@/components/dashboard/MerchantSpendTable'
import InsightsBanner from '@/components/dashboard/InsightsBanner'
import DrilldownDrawer from '@/components/dashboard/DrilldownDrawer'
import BreakdownDonut from '@/components/charts/BreakdownDonut'
import VerticalBarChart from '@/components/charts/VerticalBarChart'

import TiltCard from '@/components/ui/TiltCard'
import AnimatedSection from '@/components/ui/AnimatedSection'
import { formatNumber } from '@/lib/format'
import {
  TrendingDown,
  DollarSign,
  Layers,
  AlertTriangle,
  X,
} from 'lucide-react'

function ExpensesContent() {
  // The floating bar reads timeRange from the unified context; this
  // page only consumes timeRange to pass into the BE range query.
  const { timeRange } = useGlobalFilters()
  const [data, setData] = useState<ExpenseBreakdownResponse | null>(null)
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
        rulesService.getExpenseBreakdown(from, to),
        rulesService.listTransactions({ limit: 500, sort_by: 'transaction_date', sort_dir: 'desc', from_date: from, to_date: to }),
      ])
      setData(result)
      setTransactions(txns)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load expense data')
    } finally {
      setLoading(false)
    }
  }, [timeRange])

  useEffect(() => { loadData() }, [loadData])

  const formatDisplay = (n: number) => formatNumber(n)

  // Phase D — use the canonical category group color map.
  // The BE `by_group` response uses budget_group keys (fixed/flexible/etc)
  // AND category group keys (Income/Expenses/etc). Map both for coverage.
  const groupColorValues: Record<string, string> = {
    Income: 'var(--success-500)',
    Expenses: 'var(--danger-500)',
    Debt: 'var(--warning-500)',
    Investments: 'var(--info-500)',
    Transfer: 'var(--slate-400)',
    fixed: 'var(--primary-500)',
    flexible: 'var(--info-500)',
    debt: 'var(--warning-500)',
    savings: 'var(--success-500)',
    other: 'var(--slate-400)',
  }
  const groupColors: Record<string, string> = {
    Income: 'bg-success-500',
    Expenses: 'bg-danger-500',
    Debt: 'bg-warning-500',
    Investments: 'bg-info-500',
    Transfer: 'bg-slate-400',
    fixed: 'bg-primary-500',
    flexible: 'bg-info-500',
    debt: 'bg-warning-500',
    savings: 'bg-success-500',
    other: 'bg-slate-400',
  }

  const recentMonths = useMemo(() => data ? data.trend.slice(-6) : [], [data])

  return (
    <div className="space-y-8">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold text-on-surface tracking-tight">Expenses</h1>
        <p className="text-sm text-on-surface-variant">Analyze spending patterns and categories</p>
      </div>

      {/* Migrated from <FloatingFilterBar> colocated selector — bar provides its own. */}
      <FloatingTimeRangeBar />

      {error && (
        <div className="flex items-center gap-3 p-4 bg-danger-50 border border-danger-200 rounded-lg">
          <AlertTriangle className="w-5 h-5 text-danger-500 shrink-0" />
          <p className="text-sm text-danger-700">{error}</p>
          <button onClick={() => setError(null)} className="ml-auto"><X className="w-4 h-4" /></button>
        </div>
      )}

      {/* Anomaly insights — non-blocking, fails silently */}
      <InsightsBanner limit={3} />

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="card p-6 animate-pulse">
              <div className="h-4 bg-slate-200 rounded w-1/2 mb-3" />
              <div className="h-8 bg-slate-200 rounded w-3/4" />
            </div>
          ))}
        </div>
      ) : data ? (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <TiltCard className="card p-6">
              <div className="flex items-center gap-2 mb-2">
                <DollarSign className="w-4 h-4 text-danger-500" />
                <span className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Total Expenses</span>
              </div>
              <p className="text-2xl font-bold text-danger-600">{formatDisplay(data.total_expenses)}</p>
            </TiltCard>
            <TiltCard className="card p-6">
              <div className="flex items-center gap-2 mb-2">
                <TrendingDown className="w-4 h-4 text-warning-500" />
                <span className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Categories</span>
              </div>
              <p className="text-2xl font-bold text-on-surface">{data.by_category.length}</p>
            </TiltCard>
            <TiltCard className="card p-6">
              <div className="flex items-center gap-2 mb-2">
                <Layers className="w-4 h-4 text-info-500" />
                <span className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Groups</span>
              </div>
              <p className="text-2xl font-bold text-on-surface">{data.by_group.length}</p>
            </TiltCard>
          </div>

          {/* Expense by Group */}
          {data.by_group.length > 0 && (
            <BreakdownDonut
              title="Spending by Group"
              data={data.by_group.map((g) => ({
                id: g.group,
                name: g.group.charAt(0).toUpperCase() + g.group.slice(1),
                value: g.amount,
                color: groupColorValues[g.group] || 'var(--slate-400)',
              }))}
              total={data.total_expenses}
              onSelect={(d) => {
                const groupTxns = transactions.filter((t) => {
                  const cat = data?.by_category.find((c) => c.category_name === t.category_name)
                  return cat?.budget_group === d.id
                })
                openDrilldown(
                  `${d.name} Expenses`,
                  `${groupTxns.length} transactions · ${formatDisplay(d.value)}`,
                  <div className="space-y-2">
                    {groupTxns.slice(0, 50).map((t) => (
                      <div key={t.id} className="flex items-center justify-between py-2 border-b border-outline-variant/10">
                        <div className="min-w-0">
                          <p className="text-sm text-on-surface truncate">{t.description}</p>
                          <p className="text-xs text-on-surface-variant">{t.transaction_date}{t.merchant_name ? ` · ${t.merchant_name}` : ''}</p>
                        </div>
                        <span className="text-sm font-mono font-semibold text-danger-500">
                          ${Math.abs(t.amount).toFixed(2)}
                        </span>
                      </div>
                    ))}
                    {groupTxns.length === 0 && <p className="text-sm text-on-surface-variant py-4">No transactions found.</p>}
                  </div>,
                )
              }}
            />
          )}

          {/* Monthly Trend */}
          {recentMonths.length > 0 && (
            <div className="card p-6">
              <h3 className="text-xs font-bold uppercase tracking-wider text-on-surface mb-4">Monthly Trend</h3>
              <VerticalBarChart
                data={recentMonths.map((m) => ({
                  id: m.month,
                  label: m.month,
                  value: m.amount,
                  color: 'var(--danger-500)',
                }))}
                defaultColor="var(--danger-500)"
                onSelect={(d) => {
                  const monthTxns = transactions.filter((t) => t.transaction_date?.startsWith(d.id))
                  openDrilldown(
                    `Expenses in ${d.label}`,
                    `${monthTxns.length} transactions · ${formatDisplay(d.value)}`,
                    <div className="space-y-2">
                      {monthTxns.slice(0, 50).map((t) => (
                        <div key={t.id} className="flex items-center justify-between py-2 border-b border-outline-variant/10">
                          <div className="min-w-0">
                            <p className="text-sm text-on-surface truncate">{t.description}</p>
                            <p className="text-xs text-on-surface-variant">{t.transaction_date}{t.merchant_name ? ` · ${t.merchant_name}` : ''}</p>
                          </div>
                          <span className="text-sm font-mono font-semibold text-danger-500">
                            ${Math.abs(t.amount).toFixed(2)}
                          </span>
                        </div>
                      ))}
                      {monthTxns.length === 0 && <p className="text-sm text-on-surface-variant py-4">No transactions found.</p>}
                    </div>,
                  )
                }}
              />
            </div>
          )}

          {/* Expense Categories */}
          {data.by_category.length > 0 && (
            <div className="card p-6">
              <h3 className="text-xs font-bold uppercase tracking-wider text-on-surface mb-4">Expense Categories</h3>
              <div className="space-y-2">
                {data.by_category.map((cat) => (
                  <div
                    key={cat.category_id}
                    className="flex items-center justify-between py-2 border-b border-outline-variant/10 last:border-0 cursor-pointer hover:bg-slate-50 rounded px-1 transition-colors"
                    onClick={() => {
                      const catTxns = transactions.filter((t) =>
                        (t.category_name || 'Uncategorized').toLowerCase() === cat.category_name.toLowerCase()
                      )
                      openDrilldown(
                        cat.category_name,
                        `${catTxns.length} transactions · ${formatDisplay(cat.amount)}`,
                        <div className="space-y-2">
                          {catTxns.slice(0, 50).map((t) => (
                            <div key={t.id} className="flex items-center justify-between py-2 border-bborder-outline-variant/10">
                            <div className="min-w-0">
                                <p className="text-sm text-on-surface truncate">{t.description}</p>
                                <p className="text-xs text-on-surface-variant">{t.transaction_date}{t.merchant_name ? ` · ${t.merchant_name}` : ''}</p>
                              </div>
                              <span className="text-sm font-mono font-semibold text-danger-500">
                                ${Math.abs(t.amount).toFixed(2)}
                              </span>
                            </div>
                          ))}
                          {catTxns.length === 0 && <p className="text-sm text-on-surface-variant py-4">No transactions found.</p>}
                        </div>,
                      )
                    }}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <div className={`w-2 h-2 rounded-full shrink-0 ${groupColors[cat.budget_group] || 'bg-slate-400'}`} />
                      <span className="text-sm font-semibold text-on-surface truncate">{cat.category_name}</span>
                      <span className="text-[0.6rem] uppercase tracking-wider text-on-surface-variant">{cat.budget_group}</span>
                    </div>                        <span className="text-sm font-bold text-danger-600 tabular-nums ml-4 shrink-0">{formatDisplay(cat.amount)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Top Merchants */}
          <MerchantSpendTable transactions={transactions} limit={10} />
        </>
      ) : null}

      {/* Drilldown drawer — right-side slide-out for transaction detail */}
      <DrilldownDrawer
        open={drawerOpen}
        onClose={closeDrilldown}
        title={drawerTitle}
        subtitle={drawerSubtitle}
        breadcrumbs={['Expenses', drawerTitle]}
      >
        {drawerContent}
      </DrilldownDrawer>
    </div>
  )
}

export default function ExpensesPage() {
  return (
    <PageLayout>
      <GlobalFilterProvider>
        <ExpensesContent />
      </GlobalFilterProvider>
    </PageLayout>
  )
}
