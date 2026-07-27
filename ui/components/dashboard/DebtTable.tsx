'use client'

import type { DebtItem } from '@/lib/api'

interface DebtTableProps {
  debts: DebtItem[]
}

const typeLabels: Record<string, string> = {
  credit_card: 'Credit Card',
  loan: 'Loan',
  mortgage: 'Mortgage',
}

import { formatNumber } from '@/lib/format'

export default function DebtTable({ debts }: DebtTableProps) {
  if (debts.length === 0) return null

  return (
    <div className="card overflow-hidden">
      <div className="p-4 border-b border-outline-variant/10">
        <h3 className="text-xs font-bold uppercase tracking-wider text-on-surface">Debt Accounts</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-outline-variant/10 dark:border-slate-700/50">
              <th className="text-left px-4 py-3 text-xs font-bold uppercase tracking-wider text-on-surface-variant">Account</th>
              <th className="text-left px-4 py-3 text-xs font-bold uppercase tracking-wider text-on-surface-variant">Type</th>
              <th className="text-right px-4 py-3 text-xs font-bold uppercase tracking-wider text-on-surface-variant">Balance</th>
              <th className="text-right px-4 py-3 text-xs font-bold uppercase tracking-wider text-on-surface-variant">APR</th>
              <th className="text-right px-4 py-3 text-xs font-bold uppercase tracking-wider text-on-surface-variant">Min Payment</th>
              <th className="text-right px-4 py-3 text-xs font-bold uppercase tracking-wider text-on-surface-variant">Utilization</th>
            </tr>
          </thead>
          <tbody>
            {debts.map((debt) => (
              <tr key={debt.account_id} className="border-b border-outline-variant/5 last:border-0 hover:bg-surface-container/50 transition-colors">
                <td className="px-4 py-3">
                  <span className="font-semibold text-on-surface">{debt.account_name}</span>
                </td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[0.65rem] font-bold uppercase tracking-wider bg-surface-container-high text-on-surface-variant">
                    {typeLabels[debt.account_type] || debt.account_type}
                  </span>
                </td>
                <td className="px-4 py-3 text-right font-bold text-danger-600 tabular-nums">
                  {formatNumber(debt.balance)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-on-surface-variant">
                  {debt.interest_rate != null ? `${debt.interest_rate.toFixed(2)}%` : '\u2014'}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-on-surface-variant">
                  {debt.minimum_payment != null ? formatNumber(debt.minimum_payment) : '\u2014'}
                </td>
                <td className="px-4 py-3 text-right">
                  {debt.utilization != null ? (
                    <div className="flex items-center justify-end gap-2">
                      <div className="w-16 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${
                            debt.utilization > 70 ? 'bg-danger-500' : debt.utilization > 30 ? 'bg-warning-500' : 'bg-success-500'
                          }`}
                          style={{ width: `${Math.min(debt.utilization, 100)}%` }}
                        />
                      </div>
                      <span className="text-xs tabular-nums text-on-surface-variant w-10 text-right">
                        {debt.utilization.toFixed(0)}%
                      </span>
                    </div>
                  ) : (
                    <span className="text-on-surface-variant">{'\u2014'}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
