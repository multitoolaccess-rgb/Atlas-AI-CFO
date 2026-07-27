'use client'

import { useState, useEffect, useCallback, useMemo, type ReactNode } from 'react'
import PageLayout from '@/components/layout/PageLayout'
import { GlobalFilterProvider, useGlobalFilters, dateRangeFromPreset } from '@/components/ui/GlobalFilterContext'
import FloatingTimeRangeBar from '@/components/ui/FloatingTimeRangeBar'
import {
  rulesService,
  type IncomeBreakdownResponse,
  type Transaction,
} from '@/lib/api'
import DrilldownDrawer from '@/components/dashboard/DrilldownDrawer'
import BreakdownDonut from '@/components/charts/BreakdownDonut'
import VerticalBarChart from '@/components/charts/VerticalBarChart'
import TreemapChart, { type TreemapDatum } from '@/components/charts/TreemapChart'
import TiltCard from '@/components/ui/TiltCard'
import AnimatedSection from '@/components/ui/AnimatedSection'
import { formatNumber, formatMonthLabel } from '@/lib/format'
import {
  TrendingUp,
  DollarSign,
  Calendar,
  Layers,
} from 'lucide-react'

function IncomeContent() {
  // The floating bar reads timeRange from the unified context; this
  // page only consumes timeRange to pass into the BE range query.
  const { timeRange } = useGlobalFilters()
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
        rulesService.listTransactions({ limit: 500, sort_by: 'transaction_date', sort_dir: 'desc', from_date: from, to_date: to }),
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
    savings: 'var(--success-500)',
    debt: 'var(--warning-500)',
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
    savings: 'bg-success-500',
    debt: 'bg-warning-500',
    other: 'bg-slate-400',
  }

  const recentMonths = useMemo(() => {
    if (!data) return []
    return data.trend.slice(-6)
  }, [data])

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="space-y-1">
        <h1 className="text-2xl font-bold text-on-surface tracking-tight">Income</h1>
        <p className="text-sm text-on-surface-variant">Track all income sources and trends</p>
      </div>

      {/* Migrated from <FloatingFilterBar> colocated selector — bar provides its own. */}
      <FloatingTimeRangeBar />

      {error && (
        <div className="flex items-center gap-3 p-4 bg-danger-50 border border-danger-200 rounded-lg">
          <p className="text-sm text-danger-700">{error}</p>
        </div>
      )}

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
                <DollarSign className="w-4 h-4 text-success-500" />
                <span className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Total Income</span>
              </div>
              <p className="text-2xl font-bold text-success-600">{formatDisplay(data.total_income)}</p>
            </TiltCard>
            <TiltCard className="card p-6">
              <div className="flex items-center gap-2 mb-2">
                <Layers className="w-4 h-4 text-primary-500" />
                <span className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Sources</span>
              </div>
              <p className="text-2xl font-bold text-on-surface">{data.by_category.length}</p>
            </TiltCard>
            <TiltCard className="card p-6">
              <div className="flex items-center gap-2 mb-2">
                <Calendar className="w-4 h-4 text-info-500" />
                <span className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Groups</span>
              </div>
              <p className="text-2xl font-bold text-on-surface">{data.by_group.length}</p>
            </TiltCard>
          </div>

          {/* Income by Group */}
          {data.by_group.length > 0 && (
            <AnimatedSection animation="slideUp" delay={100}>
              <TiltCard>
                <BreakdownDonut
                  title="Income by Group"
                  data={data.by_group.map((g) => ({
                    id: g.group,
                    name: g.group.charAt(0).toUpperCase() + g.group.slice(1),
                    value: g.amount,
                    color: groupColorValues[g.group] || 'var(--slate-400)',
                  }))}
                  total={data.total_income}
                  onSelect={(d) => {
                    const groupTxns = transactions.filter((t) => {
                      const cat = data?.by_category.find((c) => c.category_name === t.category_name)
                      return cat?.budget_group === d.id
                    })
                    openDrilldown(
                      `${d.name} Income`,
                      `${groupTxns.length} transactions · ${formatDisplay(d.value)}`,
                      <div className="space-y-2">
                        {groupTxns.slice(0, 50).map((t) => (
                          <div key={t.id} className="flex items-center justify-between py-2 border-b border-outline-variant/10">
                            <div className="min-w-0">
                              <p className="text-sm text-on-surface truncate">{t.description}</p>
                              <p className="text-xs text-on-surface-variant">{t.transaction_date}{t.merchant_name ? ` · ${t.merchant_name}` : ''}</p>
                            </div>
                            <span className="text-sm font-mono font-semibold text-success-600">
                              +{formatDisplay(Math.abs(t.amount))}
                            </span>
                          </div>
                        ))}
                        {groupTxns.length === 0 && <p className="text-sm text-on-surface-variant py-4">No transactions found.</p>}
                      </div>,
                    )
                  }}
                />
              </TiltCard>
            </AnimatedSection>
          )}

          {/* Monthly Trend */}
          {recentMonths.length > 0 && (
            <AnimatedSection animation="slideUp" delay={150}>
              <div className="card p-6">
                <h3 className="text-xs font-bold uppercase tracking-wider text-on-surface mb-4">Monthly Trend</h3>
                <VerticalBarChart
                  data={recentMonths.map((m) => ({
                    id: m.month,
                    label: m.month,
                    value: m.amount,
                    color: 'var(--success-500)',
                  }))}
                  defaultColor="var(--success-500)"
                  onSelect={(d) => {
                    const monthTxns = transactions.filter((t) => t.transaction_date?.startsWith(d.id))
                    openDrilldown(
                      `Income in ${formatMonthLabel(d.id)}`,
                      `${monthTxns.length} transactions · ${formatDisplay(d.value)}`,
                      <div className="space-y-2">
                        {monthTxns.slice(0, 50).map((t) => (
                          <div key={t.id} className="flex items-center justify-between py-2 border-b border-outline-variant/10">
                            <div className="min-w-0">
                              <p className="text-sm text-on-surface truncate">{t.description}</p>
                              <p className="text-xs text-on-surface-variant">{t.transaction_date}{t.merchant_name ? ` · ${t.merchant_name}` : ''}</p>
                            </div>
                            <span className="text-sm font-mono font-semibold text-success-600">
                              +{formatDisplay(Math.abs(t.amount))}
                            </span>
                          </div>
                        ))}
                        {monthTxns.length === 0 && <p className="text-sm text-on-surface-variant py-4">No transactions found.</p>}
                      </div>,
                    )
                  }}
                />
              </div>
            </AnimatedSection>
          )}

          {/* Income Sources Treemap */}
          {data.by_category.length > 0 && (
            <AnimatedSection animation="slideUp" delay={200}>
              <TiltCard>
                <div className="card p-6">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-on-surface mb-4">Income Sources</h3>
                  <TreemapChart
                    data={data.by_category.map((cat) => ({
                      id: String(cat.category_id),
                      name: cat.category_name,
                      value: cat.amount,
                      color: groupColorValues[cat.budget_group] || 'var(--slate-400)',
                    }))}
                    onSelect={(d) => {
                      const catTxns = transactions.filter((t) =>
                        (t.category_name || 'Uncategorized').toLowerCase() === d.name.toLowerCase()
                      )
                      openDrilldown(
                        d.name,
                        `${catTxns.length} transactions · ${formatDisplay(d.value)}`,
                        <div className="space-y-2">
                          {catTxns.slice(0, 50).map((t) => (
                            <div key={t.id} className="flex items-center justify-between py-2 border-b border-outline-variant/10">
                              <div className="min-w-0">
                                <p className="text-sm text-on-surface truncate">{t.description}</p>
                                <p className="text-xs text-on-surface-variant">{t.transaction_date}{t.merchant_name ? ` · ${t.merchant_name}` : ''}</p>
                              </div>
                              <span className="text-sm font-mono font-semibold text-success-600">
                                +{formatDisplay(Math.abs(t.amount))}
                              </span>
                            </div>
                          ))}
                          {catTxns.length === 0 && <p className="text-sm text-on-surface-variant py-4">No transactions found.</p>}
                        </div>,
                      )
                    }}
                  />
                </div>
              </TiltCard>
            </AnimatedSection>
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
  return (
    <PageLayout>
      <GlobalFilterProvider>
        <IncomeContent />
      </GlobalFilterProvider>
    </PageLayout>
  )
}
