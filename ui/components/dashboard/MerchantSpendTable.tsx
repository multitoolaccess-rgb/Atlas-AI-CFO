'use client'

import { useMemo } from 'react'
import { formatNumber } from '@/lib/format'
import type { Transaction } from '@/lib/api'

interface MerchantSpendTableProps {
  transactions: Transaction[]
  limit?: number
}

export default function MerchantSpendTable({ transactions, limit = 10 }: MerchantSpendTableProps) {
  const merchants = useMemo(() => {
    const grouped: Record<string, { total: number; count: number }> = {}
    for (const t of transactions) {
      if (t.amount >= 0) continue // only expenses
      const name = t.merchant_name || t.description || 'Unknown'
      if (!grouped[name]) grouped[name] = { total: 0, count: 0 }
      grouped[name].total += Math.abs(t.amount)
      grouped[name].count += 1
    }
    return Object.entries(grouped)
      .map(([name, data]) => ({ name, ...data }))
      .sort((a, b) => b.total - a.total)
      .slice(0, limit)
  }, [transactions, limit])

  if (merchants.length === 0) return null

  const maxTotal = merchants[0]?.total || 1

  return (
    <div className="card p-6">
      <h3 className="text-xs font-bold uppercase tracking-wider text-on-surface mb-4">Top Merchants</h3>
      <div className="space-y-3">
        {merchants.map((m, i) => {
          const pct = (m.total / maxTotal) * 100
          return (
            <div key={m.name} className="flex items-center gap-3">
              <span className="text-xs font-bold text-on-surface-variant w-5 text-right shrink-0">{i + 1}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-semibold text-on-surface truncate">{m.name}</span>
                  <span className="text-xs text-on-surface-variant ml-2 shrink-0">
                    {m.count} txn{m.count !== 1 ? 's' : ''}
                  </span>
                </div>
                <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-danger-500 rounded transition-all duration-500"
                    style={{ width: `${Math.max(pct, 2)}%` }}
                  />
                </div>
              </div>
              <span className="text-sm font-bold text-danger-600 tabular-nums w-16 text-right shrink-0">
                {formatNumber(m.total)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
