'use client'

import { Receipt, Shield, TrendingUp } from 'lucide-react'
import type { DashboardSummary } from '@/lib/api'

interface SecondaryInsightsProps {
  summary: DashboardSummary
}

export default function SecondaryInsights({ summary }: SecondaryInsightsProps) {
  const lastImportText = summary.last_import_at
    ? new Date(summary.last_import_at).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : 'Never'

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-8">
      <div className="card p-6 overflow-hidden relative">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-8 h-8 rounded-lg bg-[var(--primary-50)] flex items-center justify-center border border-[var(--primary-200)]">
            <TrendingUp className="w-4 h-4 text-[var(--primary-600)]" aria-hidden="true" />
          </div>
          <h4 className="headline-sm text-primary">Imports</h4>
        </div>
        <p className="text-2xl font-bold text-on-surface mb-1">
          {summary.import_batches_count}
        </p>
        <p className="text-sm text-tertiary">
          batch{summary.import_batches_count === 1 ? '' : 'es'}{' \u00b7 '}last {lastImportText}
        </p>
      </div>

      <div className="card p-6 overflow-hidden relative">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-8 h-8 rounded-lg bg-[var(--success-50)] flex items-center justify-center border border-[var(--success-200)]">
            <Shield className="w-4 h-4 text-[var(--success-600)]" aria-hidden="true" />
          </div>
          <h4 className="headline-sm text-primary">Accounts</h4>
        </div>
        <p className="text-2xl font-bold text-on-surface mb-1">
          {summary.accounts_count}
        </p>
        <p className="text-sm text-tertiary">
          active{' \u00b7 '}{summary.transactions_count} transactions
        </p>
      </div>

      <div className="card p-6 overflow-hidden relative">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-8 h-8 rounded-lg bg-[var(--warning-50)] flex items-center justify-center border border-[var(--warning-200)]">
            <Receipt className="w-4 h-4 text-[var(--warning-600)]" aria-hidden="true" />
          </div>
          <h4 className="headline-sm text-primary">Cash Flow</h4>
        </div>
        <p className="text-2xl font-bold text-on-surface mb-1">
          ${' '}
          {(summary.total_income_month - summary.total_expenses_month).toLocaleString('en-US', {
            maximumFractionDigits: 0,
          })}
        </p>
        <p className="text-sm text-tertiary">net this month</p>
      </div>
    </div>
  )
}
