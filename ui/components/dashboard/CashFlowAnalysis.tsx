'use client'

import { useMemo } from 'react'
import { ArrowDownRight, ArrowUpRight, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { formatCurrency } from '@/lib/format'
import { DashboardFocusLayer, DashboardFocusToggle, useDashboardFocus } from '@/components/dashboard/ExpandableCard'
interface CashFlowAnalysisProps {
  /** Range-scoped income from the Money Flow endpoint. */
  income: number
  /** Range-scoped spending from the Breakdown endpoint. */
  expenses: number
  /** Human-readable label for the active global range. */
  rangeLabel: string
  loading?: boolean
  className?: string
}

export default function CashFlowAnalysis({ income, expenses, rangeLabel, loading, className = '' }: CashFlowAnalysisProps) {
  const { focused, setFocused } = useDashboardFocus()
  const net = income - expenses
  const isPositive = net > 0
  const isZero = net === 0

  // Savings rate = (income - expenses) / income * 100
  const savingsRate = income > 0 ? ((income - expenses) / income) * 100 : 0

  // Bar widths relative to the larger of income / expenses
  const maxAmount = Math.max(income, expenses, 1)
  const incomePct = (income / maxAmount) * 100
  const expensesPct = (expenses / maxAmount) * 100

  // Expense-to-income ratio
  const burnRate = income > 0 ? (expenses / income) * 100 : 0

  if (loading) {
    return (
      <div className={`card p-6 ${className}`} aria-label="Cash flow analysis" aria-busy="true">
        <h3 className="headline-md text-primary mb-4">Cash Flow</h3>
        <div className="space-y-4">
          <div className="skeleton h-6 w-1/2" />
          <div className="skeleton h-4 w-full" />
          <div className="skeleton h-4 w-full" />
        </div>
      </div>
    )
  }

  return (
    <DashboardFocusLayer focused={focused} title="Cash Flow analysis">
      <div className={`card p-6 animate-fadeIn ${focused ? 'min-h-[calc(100vh-3rem)]' : ''} ${className}`} aria-label="Cash flow analysis">
        <div className="flex items-center justify-between gap-3 mb-5">
          <div>
            <h3 className="headline-md text-primary">Cash Flow</h3>
            <span className="label-sm text-tertiary">{rangeLabel}</span>
          </div>
          <DashboardFocusToggle focused={focused} onToggle={() => setFocused((value) => !value)} />
        </div>

      {/* Net cash flow hero */}
      <div className="flex items-center gap-3 mb-6">
        <div
          className={`w-10 h-10 rounded-[var(--radius-lg)] flex items-center justify-center ${
            isPositive
              ? 'bg-[var(--success-50)]'
              : isZero
                ? 'bg-[var(--slate-100)]'
                : 'bg-[var(--danger-50)]'
          }`}
        >
          {isPositive ? (
            <TrendingUp className="w-5 h-5 text-[var(--success-600)]" aria-hidden="true" />
          ) : isZero ? (
            <Minus className="w-5 h-5 text-[var(--slate-500)]" aria-hidden="true" />
          ) : (
            <TrendingDown className="w-5 h-5 text-[var(--danger-600)]" aria-hidden="true" />
          )}
        </div>
        <div>
          <p className="label-md text-tertiary">Net Cash Flow</p>
          <p className={`numeric-lg ${isPositive ? 'text-positive' : isZero ? 'text-neutral' : 'text-negative'}`}>
            {isPositive ? '+' : isZero ? '' : '−'}{formatCurrency(Math.abs(net))}
          </p>
        </div>
      </div>

      {/* Income bar */}
      <div className="mb-4">
        <div className="flex-between mb-1.5">
          <div className="flex items-center gap-2">
            <ArrowUpRight className="w-3.5 h-3.5 text-[var(--success-600)]" aria-hidden="true" />
            <span className="label-md text-on-surface">Income</span>
          </div>
          <span className="numeric-sm text-[var(--success-600)]">
            +{formatCurrency(income)}
          </span>
        </div>
        <div className="h-3 w-full bg-[var(--slate-100)] rounded-[var(--radius-full)] overflow-hidden">
          <div
            className="h-full rounded-[var(--radius-full)] bg-[var(--success-500)] transition-all duration-700 ease-out"
            style={{ width: `${incomePct}%` }}
            role="progressbar"
            aria-valuenow={Math.round(incomePct)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Income: ${formatCurrency(income)}`}
          />
        </div>
      </div>

      {/* Expenses bar */}
      <div className="mb-5">
        <div className="flex-between mb-1.5">
          <div className="flex items-center gap-2">
            <ArrowDownRight className="w-3.5 h-3.5 text-[var(--danger-600)]" aria-hidden="true" />
            <span className="label-md text-on-surface">Expenses</span>
          </div>
          <span className="numeric-sm text-[var(--danger-600)]">
            −{formatCurrency(expenses)}
          </span>
        </div>
        <div className="h-3 w-full bg-[var(--slate-100)] rounded-[var(--radius-full)] overflow-hidden">
          <div
            className="h-full rounded-[var(--radius-full)] bg-[var(--danger-500)] transition-all duration-700 ease-out"
            style={{ width: `${expensesPct}%` }}
            role="progressbar"
            aria-valuenow={Math.round(expensesPct)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Expenses: ${formatCurrency(expenses)}`}
          />
        </div>
      </div>

      {/* Bottom stats grid */}
      <div className="grid grid-cols-2 gap-3 pt-4 border-t border-[var(--border-subtle)]">
        <div>
          <p className="label-sm text-tertiary">Savings Rate</p>
          <p className={`text-base font-semibold ${savingsRate >= 0 ? 'text-[var(--success-700)]' : 'text-[var(--danger-700)]'}`}>
            {savingsRate.toFixed(1)}%
          </p>
        </div>
        <div>
          <p className="label-sm text-tertiary">Burn Rate</p>
          <p className={`text-base font-semibold ${burnRate <= 80 ? 'text-[var(--success-700)]' : burnRate <= 100 ? 'text-[var(--warning-700)]' : 'text-[var(--danger-700)]'}`}>
            {burnRate.toFixed(0)}%
          </p>
        </div>
      </div>
      </div>
    </DashboardFocusLayer>
  )
}
