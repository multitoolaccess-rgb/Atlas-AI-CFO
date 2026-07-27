'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import PageLayout from '@/components/layout/PageLayout'
import AnimatedPageSection from '@/components/ui/AnimatedPageSection'
import { GlobalFilterProvider } from '@/components/ui/GlobalFilterContext'
import FloatingTimeRangeBar from '@/components/ui/FloatingTimeRangeBar'
import { rulesService, type DebtsSummaryResponse } from '@/lib/api'
import DebtTable from '@/components/dashboard/DebtTable'
import PayoffProjectionChart from '@/components/dashboard/PayoffProjectionChart'
import PayoffComparison from '@/components/dashboard/PayoffComparison'
import ChartDonut from '@/components/charts/ChartDonut'
import TiltCard from '@/components/ui/TiltCard'
import { formatNumber } from '@/lib/format'
import {
  CreditCard,
  DollarSign,
  Percent,
  AlertTriangle,
  TrendingDown,
  X,
} from 'lucide-react'

const typeLabels: Record<string, string> = {
  credit_card: 'Credit Cards',
  loan: 'Loans',
  mortgage: 'Mortgages',
}

const typeColors: Record<string, string> = {
  credit_card: 'var(--danger-500)',
  loan: 'var(--warning-500)',
  mortgage: 'var(--info-500)',
}

function DebtsContent() {
  const [data, setData] = useState<DebtsSummaryResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const result = await rulesService.getDebtsSummary()
      setData(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load debt data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const composition = useMemo(() => {
    if (!data) return []
    const groups: Record<string, number> = {}
    for (const d of data.debts) {
      groups[d.account_type] = (groups[d.account_type] || 0) + d.balance
    }
    return Object.entries(groups).map(([type, amount]) => ({
      label: typeLabels[type] || type,
      value: amount,
      color: typeColors[type] || 'var(--slate-400)',
    }))
  }, [data])

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-on-surface tracking-tight">Debts</h1>
          <p className="text-sm text-on-surface-variant mt-1">Track loans, credit cards, and mortgages</p>
        </div>
      </div>

      {/* Floating bar — URL-synced via ?range=… (page-default YTD).
          Visual-only today: getDebtsSummary() is not range-aware yet. */}
      <FloatingTimeRangeBar />

      {error && (
        <div className="flex items-center gap-3 p-4 bg-danger-50 border border-danger-200 rounded-lg">
          <AlertTriangle className="w-5 h-5 text-danger-500 shrink-0" />
          <p className="text-sm text-danger-700">{error}</p>
          <button onClick={() => setError(null)} className="ml-auto"><X className="w-4 h-4" /></button>
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="card p-6 animate-pulse">
              <div className="h-4 bg-slate-200 rounded w-1/2 mb-3" />
              <div className="h-8 bg-slate-200 rounded w-3/4" />
            </div>
          ))}
        </div>
      ) : data ? (
        <>
          {/* KPI Cards with 3D tilt */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <TiltCard className="h-full">
              <div className="card p-6 h-full">
                <div className="flex items-center gap-2 mb-2">
                  <DollarSign className="w-4 h-4 text-danger-500" />
                  <span className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Total Debt</span>
                </div>
                <p className="text-2xl font-bold text-danger-600">{formatNumber(data.total_debt)}</p>
              </div>
            </TiltCard>
            <TiltCard className="h-full">
              <div className="card p-6 h-full">
                <div className="flex items-center gap-2 mb-2">
                  <Percent className="w-4 h-4 text-warning-500" />
                  <span className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Blended APR</span>
                </div>
                <p className="text-2xl font-bold text-on-surface">{data.blended_apr.toFixed(2)}%</p>
              </div>
            </TiltCard>
            <TiltCard className="h-full">
              <div className="card p-6 h-full">
                <div className="flex items-center gap-2 mb-2">
                  <TrendingDown className="w-4 h-4 text-info-500" />
                  <span className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Monthly Minimum</span>
                </div>
                <p className="text-2xl font-bold text-on-surface">{formatNumber(data.total_monthly_minimum)}</p>
              </div>
            </TiltCard>
            <TiltCard className="h-full">
              <div className="card p-6 h-full">
                <div className="flex items-center gap-2 mb-2">
                  <CreditCard className="w-4 h-4 text-primary-500" />
                  <span className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Accounts</span>
                </div>
                <p className="text-2xl font-bold text-on-surface">{data.debts.length}</p>
              </div>
            </TiltCard>
          </div>

          {/* Debt Composition Donut */}
          {data.debts.length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-1">
                <h3 className="text-xs font-bold uppercase tracking-wider text-on-surface mb-4">Debt Composition</h3>
                <ChartDonut
                  slices={composition}
                  centerLabel="Total Debt"
                  centerValue={data.total_debt}
                  height={360}
                  loading={loading}
                />
              </div>
              <div className="lg:col-span-2">
                <DebtTable debts={data.debts} />
              </div>
            </div>
          )}

          {data.debts.length === 0 && (
            <div className="card p-12 text-center">
              <CreditCard className="w-12 h-12 text-on-surface-variant/30 mx-auto mb-4" />
              <h3 className="text-lg font-bold text-on-surface mb-2">No debt accounts found</h3>
              <p className="text-sm text-on-surface-variant max-w-md mx-auto">
                Add credit cards, loans, or mortgage accounts to track your debt here.
                Go to <strong>Accounts</strong> and create an account with type &quot;Credit Card&quot;, &quot;Loan&quot;, or &quot;Mortgage&quot;.
              </p>
            </div>
          )}

          {/* Payoff Projections */}
          <PayoffProjectionChart debts={data.debts} />

          {/* Payoff Strategy Comparison */}
          <PayoffComparison debts={data.debts} />
        </>
      ) : null}
    </div>
  )
}

export default function DebtsPage() {
  return (
    <PageLayout>
      <GlobalFilterProvider>
        <AnimatedPageSection>
          <DebtsContent />
        </AnimatedPageSection>
      </GlobalFilterProvider>
    </PageLayout>
  )
}
