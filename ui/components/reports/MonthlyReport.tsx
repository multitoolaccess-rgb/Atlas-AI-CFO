'use client'

import { useState } from 'react'
import { Download, Calendar } from 'lucide-react'
import Button from '@/components/ui/Button'
import Select from '@/components/ui/Select'
import { formatCurrency } from '@/lib/format'

interface MonthlyReportData {
  month: string
  totalIncome: number
  totalExpenses: number
  netChange: number
  goalsProgress: Array<{
    name: string
    progress: number
    target: number
  }>
}

interface MonthlyReportProps {
  data: MonthlyReportData | null
  months: string[]
  selectedMonth: string
  onMonthChange: (month: string) => void
  loading?: boolean
  className?: string
}

/**
 * Generates a monthly summary showing income, expenses, net change,
 * and progress toward financial goals. Includes export to PDF.
 */
export default function MonthlyReport({
  data,
  months,
  selectedMonth,
  onMonthChange,
  loading = false,
  className = '',
}: MonthlyReportProps) {
  const handleExportPDF = () => {
    if (!data) return

    // Create a simple text-based export (PDF generation would need a library)
    const content = `
MONTHLY FINANCIAL REPORT - ${data.month}
========================================

SUMMARY
-------
Total Income:     ${formatCurrency(data.totalIncome)}
Total Expenses:   ${formatCurrency(data.totalExpenses)}
Net Change:       ${formatCurrency(data.netChange)}

GOALS PROGRESS
--------------
${data.goalsProgress
  .map(
    (goal) =>
      `${goal.name}: ${formatCurrency(goal.progress)} / ${formatCurrency(goal.target)} (${((goal.progress / goal.target) * 100).toFixed(0)}%)`
  )
  .join('\n')}

Generated: ${new Date().toLocaleString()}
    `.trim()

    const element = document.createElement('a')
    element.setAttribute(
      'href',
      'data:text/plain;charset=utf-8,' + encodeURIComponent(content)
    )
    element.setAttribute('download', `monthly-report-${data.month}.txt`)
    element.style.display = 'none'
    document.body.appendChild(element)
    element.click()
    document.body.removeChild(element)
  }

  if (loading) {
    return (
      <div className={`card p-6 animate-pulse ${className}`}>
        <div className="h-8 bg-slate-200 rounded w-1/2 mb-4" />
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-4 bg-slate-200 rounded w-full" />
          ))}
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className={`card p-6 text-center text-[var(--text-tertiary)] ${className}`}>
        <p>No data available</p>
      </div>
    )
  }

  return (
    <div className={`card p-6 space-y-6 ${className}`}>
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h3 className="headline-md text-primary">Monthly Report</h3>
          <p className="text-sm text-[var(--text-secondary)] mt-1">
            Financial summary for {data.month}
          </p>
        </div>
        <div className="flex gap-2 w-full sm:w-auto">
          <Select
            options={months.map((m) => ({ value: m, label: m }))}
            value={selectedMonth}
            onChange={(e) => onMonthChange(e.target.value)}
            className="flex-1 sm:flex-none"
          />
          <Button
            onClick={handleExportPDF}
            variant="secondary"
            title="Export report as TXT file"
          >
            <Download className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Financial Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-4 rounded-lg bg-[var(--success-50)] border border-[var(--success-200)]">
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--success-700)] mb-1">
            Total Income
          </p>
          <p className="text-2xl font-bold text-[var(--success-600)]">
            {formatCurrency(data.totalIncome)}
          </p>
        </div>
        <div className="p-4 rounded-lg bg-[var(--danger-50)] border border-[var(--danger-200)]">
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--danger-700)] mb-1">
            Total Expenses
          </p>
          <p className="text-2xl font-bold text-[var(--danger-500)]">
            {formatCurrency(data.totalExpenses)}
          </p>
        </div>
        <div
          className="p-4 rounded-lg border-2"
          style={{
            backgroundColor: data.netChange >= 0 ? 'var(--primary-50)' : 'var(--warning-50)',
            borderColor: data.netChange >= 0 ? 'var(--primary-200)' : 'var(--warning-200)',
          }}
        >
          <p className="text-xs font-semibold uppercase tracking-wider mb-1" style={{
            color: data.netChange >= 0 ? 'var(--primary-700)' : 'var(--warning-700)',
          }}>
            Net Change
          </p>
          <p className="text-2xl font-bold" style={{
            color: data.netChange >= 0 ? 'var(--primary-600)' : 'var(--warning-600)',
          }}>
            {data.netChange >= 0 ? '+' : ''}{formatCurrency(data.netChange)}
          </p>
        </div>
      </div>

      {/* Goals Progress */}
      {data.goalsProgress.length > 0 && (
        <div className="border-t border-[var(--border-subtle)] pt-6">
          <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-3">
            Goals Progress
          </h4>
          <div className="space-y-3">
            {data.goalsProgress.map((goal) => {
              const pct = Math.min((goal.progress / goal.target) * 100, 100)
              return (
                <div key={goal.name}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-[var(--text-secondary)]">
                      {goal.name}
                    </span>
                    <span className="text-xs text-[var(--text-tertiary)]">
                      {pct.toFixed(0)}%
                    </span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-[var(--border-subtle)] overflow-hidden">
                    <div
                      className="h-full bg-[var(--primary-500)] transition-all duration-300"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <p className="text-xs text-[var(--text-tertiary)] mt-0.5">
                    {formatCurrency(goal.progress)} of {formatCurrency(goal.target)}
                  </p>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between pt-4 border-t border-[var(--border-subtle)] text-xs text-[var(--text-tertiary)]">
        <span>Generated {new Date().toLocaleString()}</span>
        <span>Monthly Financial Report</span>
      </div>
    </div>
  )
}
