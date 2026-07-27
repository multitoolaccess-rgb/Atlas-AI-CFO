'use client'

import { useMemo } from 'react'
import { calculateAmortization } from '@/lib/amortization'
import type { DebtItem } from '@/lib/api'
import { formatNumber } from '@/lib/format'
import { Clock, DollarSign, TrendingDown } from 'lucide-react'

interface PayoffProjectionChartProps {
  debts: DebtItem[]
}

export default function PayoffProjectionChart({ debts }: PayoffProjectionChartProps) {

  const projections = useMemo(() => {
    return debts
      .filter((d) => d.balance > 0 && d.interest_rate != null && d.minimum_payment != null && d.minimum_payment > 0)
      .map((debt) => {
        const result = calculateAmortization({
          balance: debt.balance,
          annualRate: (debt.interest_rate ?? 0) / 100,
          monthlyPayment: debt.minimum_payment ?? 0,
          months: 360,
        })
        return {
          ...debt,
          payoffMonths: result.payoffMonths,
          totalInterest: result.totalInterest,
          totalPaid: result.totalPaid,
          schedule: result.schedule.slice(0, 60), // Show first 5 years
        }
      })
      .sort((a, b) => b.balance - a.balance)
  }, [debts])

  if (projections.length === 0) return null

  return (
    <div className="card p-6">
      <h3 className="text-xs font-bold uppercase tracking-wider text-on-surface mb-4">Payoff Projections</h3>

      <div className="space-y-6">
        {projections.map((proj) => {
          // Build the chart data points (balance over time)
          const maxBalance = proj.balance
          const dataPoints = proj.schedule.filter((_, i) => i % 3 === 0) // Every 3rd month

          return (
            <div key={proj.account_id} className="border-b border-outline-variant/10 pb-4 last:border-0 last:pb-0">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-on-surface">{proj.account_name}</span>
                <span className="text-xs text-on-surface-variant">
                  {proj.interest_rate?.toFixed(2)}% APR
                </span>
              </div>

              {/* Stats row */}
              <div className="grid grid-cols-3 gap-3 mb-3">
                <div className="flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-info-500" />
                  <div>
                    <p className="text-[0.65rem] text-on-surface-variant">Payoff</p>
                    <p className="text-xs font-bold text-on-surface">
                      {proj.payoffMonths ? `${Math.ceil(proj.payoffMonths / 12)}y ${proj.payoffMonths % 12}m` : 'N/A'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <DollarSign className="w-3.5 h-3.5 text-warning-500" />
                  <div>
                    <p className="text-[0.65rem] text-on-surface-variant">Interest</p>
                    <p className="text-xs font-bold text-on-surface">{formatNumber(proj.totalInterest)}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <TrendingDown className="w-3.5 h-3.5 text-success-500" />
                  <div>
                    <p className="text-[0.65rem] text-on-surface-variant">Total Paid</p>
                    <p className="text-xs font-bold text-on-surface">{formatNumber(proj.totalPaid)}</p>
                  </div>
                </div>
              </div>

              {/* Balance projection bar chart */}
              {dataPoints.length > 0 && (
                <div className="flex items-end gap-0.5 h-12">
                  {dataPoints.map((pt, i) => {
                    const pct = maxBalance > 0 ? (pt.balance / maxBalance) * 100 : 0
                    return (
                      <div
                        key={pt.month}
                        className="flex-1 bg-primary-500/30 rounded-t-sm transition-all duration-300 hover:bg-primary-500/50"
                        style={{ height: `${Math.max(pct, 2)}%` }}
                        title={`Month ${pt.month}: ${formatNumber(pt.balance)}`}
                      />
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
