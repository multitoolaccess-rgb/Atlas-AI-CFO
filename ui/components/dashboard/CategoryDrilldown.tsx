'use client'

import { useState, useMemo, useCallback } from 'react'
import { ArrowUpDown, DollarSign } from 'lucide-react'
import { type Transaction, type Category } from '@/lib/api'
import { formatCurrency, formatMonthLabel } from '@/lib/format'
import Modal from '@/components/ui/Modal'
import Button from '@/components/ui/Button'
import Breadcrumbs from '@/components/ui/Breadcrumbs'

interface CategoryDrilldownProps {
  open: boolean
  onClose: () => void
  category: Category | null
  transactions: Transaction[]
}

type SortField = 'date' | 'amount' | 'description'
type SortDir = 'asc' | 'desc'
type TimeFilter = 'this_month' | 'last_3_months' | 'all_time'

export default function CategoryDrilldown({
  open,
  onClose,
  category,
  transactions,
}: CategoryDrilldownProps) {
  const [sortField, setSortField] = useState<SortField>('date')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [timeFilter, setTimeFilter] = useState<TimeFilter>('this_month')

  const filteredAndSorted = useMemo(() => {
    if (!category) return []

    let filtered = transactions.filter(
      (t) => (t.category_name || 'Uncategorized') === category.name
    )

    // Apply time filter
    const now = new Date()
    const filterDate = new Date()
    switch (timeFilter) {
      case 'this_month':
        filtered = filtered.filter(
          (t) => new Date(t.transaction_date).getMonth() === now.getMonth() &&
            new Date(t.transaction_date).getFullYear() === now.getFullYear()
        )
        break
      case 'last_3_months':
        filterDate.setMonth(filterDate.getMonth() - 3)
        filtered = filtered.filter(
          (t) => new Date(t.transaction_date) >= filterDate
        )
        break
      case 'all_time':
        break
    }

    // Sort
    filtered.sort((a, b) => {
      let cmp = 0
      switch (sortField) {
        case 'date':
          cmp = new Date(a.transaction_date).getTime() - new Date(b.transaction_date).getTime()
          break
        case 'amount':
          cmp = Math.abs(a.amount) - Math.abs(b.amount)
          break
        case 'description':
          cmp = (a.description || '').localeCompare(b.description || '')
          break
      }
      return sortDir === 'asc' ? cmp : -cmp
    })

    return filtered
  }, [category, transactions, sortField, sortDir, timeFilter])

  const toggleSort = useCallback(
    (field: SortField) => {
      if (sortField === field) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
      } else {
        setSortField(field)
        setSortDir('desc')
      }
    },
    [sortField]
  )

  if (!category) return null

  const totalSpent = filteredAndSorted.reduce((s, t) => s + Math.abs(t.amount), 0)
  const count = filteredAndSorted.length

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="w-3 h-3 opacity-30" />
    return sortDir === 'asc' ? (
      <ArrowUpDown className="w-3 h-3" />
    ) : (
      <ArrowUpDown className="w-3 h-3 rotate-180" />
    )
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={category.name}
      size="lg"
      footer={
        <>
          <Button variant="tertiary" onClick={onClose}>
            Close
          </Button>
          <Button
            onClick={() => {
              onClose()
            }}
          >
            + Add Transaction
          </Button>
        </>
      }
    >
      {/* Time filter tabs */}
      <div className="flex gap-2 mb-4">
        {([
          ['this_month', 'This Month'],
          ['last_3_months', 'Last 3 Months'],
          ['all_time', 'All Time'],
        ] as [TimeFilter, string][]).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTimeFilter(key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              timeFilter === key
                ? 'bg-[var(--primary-500)] text-white'
                : 'bg-[var(--slate-100)] text-[var(--text-secondary)] hover:bg-[var(--slate-200)]'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Summary */}
      <div className="flex items-center justify-between mb-4 p-3 rounded-lg bg-[var(--bg-secondary)]">
        <div>
          <p className="text-xs text-[var(--text-tertiary)] uppercase tracking-wide font-semibold">
            Total Spent
          </p>
          <p className="text-lg font-semibold text-[var(--text-primary)] mt-1">
            {formatCurrency(totalSpent)}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs text-[var(--text-tertiary)] uppercase tracking-wide font-semibold">
            Transactions
          </p>
          <p className="text-lg font-semibold text-[var(--text-primary)] mt-1">{count}</p>
        </div>
      </div>

      {/* Sort controls */}
      <div className="flex gap-2 mb-4 pb-3 border-b border-[var(--border-subtle)]">
        <button
          onClick={() => toggleSort('date')}
          className="flex items-center gap-1 px-2 py-1 rounded text-xs hover:bg-[var(--bg-secondary)] transition-colors"
        >
          Date
          <SortIcon field="date" />
        </button>
        <button
          onClick={() => toggleSort('amount')}
          className="flex items-center gap-1 px-2 py-1 rounded text-xs hover:bg-[var(--bg-secondary)] transition-colors"
        >
          Amount
          <SortIcon field="amount" />
        </button>
        <button
          onClick={() => toggleSort('description')}
          className="flex items-center gap-1 px-2 py-1 rounded text-xs hover:bg-[var(--bg-secondary)] transition-colors"
        >
          Description
          <SortIcon field="description" />
        </button>
      </div>

      {/* Transaction list */}
      <div className="space-y-1 max-h-96 overflow-y-auto">
        {count === 0 ? (
          <div className="text-center py-8">
            <DollarSign className="w-8 h-8 mx-auto text-[var(--text-tertiary)] opacity-50 mb-2" />
            <p className="text-sm text-[var(--text-tertiary)]">No transactions found</p>
          </div>
        ) : (
          filteredAndSorted.map((txn) => (
            <div
              key={txn.id}
              className="flex items-center justify-between py-3 px-3 rounded-lg hover:bg-[var(--bg-secondary)] transition-colors border border-transparent hover:border-[var(--border-subtle)]"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-[var(--text-primary)] truncate">
                  {txn.description}
                </p>
                <p className="text-xs text-[var(--text-tertiary)]">
                  {formatMonthLabel(txn.transaction_date)}
                  {txn.merchant_name ? ` · ${txn.merchant_name}` : ''}
                </p>
              </div>
              <div className="text-right flex-shrink-0 ml-3">
                <p
                  className="text-sm font-mono font-semibold"
                  style={{
                    color: txn.amount < 0
                      ? 'var(--danger-500)'
                      : 'var(--success-600)',
                  }}
                >
                  {txn.amount < 0 ? '-' : '+'}
                  {formatCurrency(Math.abs(txn.amount))}
                </p>
              </div>
            </div>
          ))
        )}
      </div>
    </Modal>
  )
}
