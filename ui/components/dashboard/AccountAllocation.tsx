'use client'

import { useMemo } from 'react'
import { Landmark, CreditCard, TrendingUp, PiggyBank, Building2, HelpCircle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { Account } from '@/lib/api'

interface AccountAllocationProps {
  accounts: Account[]
  totalBalance: number
  loading?: boolean
  className?: string
}

const TYPE_CONFIG: Record<string, { label: string; color: string; bgClass: string; Icon: LucideIcon }> = {
  checking:  { label: 'Checking',    color: 'var(--primary-500)', bgClass: 'bg-[var(--primary-50)]',  Icon: Landmark },
  savings:   { label: 'Savings',     color: 'var(--success-500)', bgClass: 'bg-[var(--success-50)]',  Icon: PiggyBank },
  credit:    { label: 'Credit Card', color: 'var(--danger-500)',  bgClass: 'bg-[var(--danger-50)]',   Icon: CreditCard },
  investment:{ label: 'Investment',  color: 'var(--info-500)',    bgClass: 'bg-[var(--info-50)]',     Icon: TrendingUp },
  loan:      { label: 'Loan',        color: 'var(--warning-500)', bgClass: 'bg-[var(--warning-50)]',  Icon: Building2 },
}

const DEFAULT_CONFIG = { label: 'Other', color: 'var(--slate-400)', bgClass: 'bg-[var(--slate-50)]', Icon: HelpCircle as LucideIcon }

interface TypeAggregate {
  type: string
  label: string
  total: number
  count: number
  pct: number
  color: string
  bgClass: string
  Icon: LucideIcon
}

export default function AccountAllocation({ accounts, totalBalance, loading, className = '' }: AccountAllocationProps) {
  const aggregates = useMemo<TypeAggregate[]>(() => {
    const map = new Map<string, { total: number; count: number }>()
    for (const acc of accounts) {
      const key = (acc.account_type || 'other').toLowerCase()
      const existing = map.get(key) ?? { total: 0, count: 0 }
      existing.total += acc.current_balance
      existing.count += 1
      map.set(key, existing)
    }
    // Normalize against the SUM of absolute balances so percentages
    // stay 0-100 even with mixed-sign accounts (e.g. credit debt vs
    // checking). Using `abs(totalBalance)` would produce >100% when
    // liabilities partially offset assets.
    const sumOfAbsBalances = Array.from(map.values()).reduce(
      (s, v) => s + Math.abs(v.total),
      0,
    )
    const denom = Math.max(1, sumOfAbsBalances)
    return Array.from(map.entries())
      .map(([type, { total, count }]) => {
        const config = TYPE_CONFIG[type] ?? DEFAULT_CONFIG
        return {
          type,
          label: config.label,
          total,
          count,
          pct: (Math.abs(total) / denom) * 100,
          color: config.color,
          bgClass: config.bgClass,
          Icon: config.Icon,
        }
      })
      .sort((a, b) => Math.abs(b.total) - Math.abs(a.total))
  }, [accounts])

  if (loading) {
    return (
      <div className={`card p-6 ${className}`} aria-label="Account allocation" aria-busy="true">
        <h3 className="headline-md text-primary mb-4">Account Allocation</h3>
        <div className="space-y-4">
          {[0, 1, 2].map((i) => (
            <div key={i}>
              <div className="skeleton h-3 w-1/3 mb-2" />
              <div className="skeleton h-2 w-full" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (accounts.length === 0) {
    return (
      <div className={`card p-6 ${className}`} aria-label="Account allocation">
        <h3 className="headline-md text-primary mb-4">Account Allocation</h3>
        <p className="body-sm text-tertiary">No accounts to display.</p>
      </div>
    )
  }

  return (
    <div className={`card p-6 animate-fadeIn ${className}`} aria-label="Account allocation">
      <div className="flex-between mb-5">
        <h3 className="headline-md text-primary">Account Allocation</h3>
        <span className="label-sm text-tertiary">
          {accounts.length} account{accounts.length === 1 ? '' : 's'}
        </span>
      </div>

      <div className="space-y-4">
        {aggregates.map((agg) => {
          const Icon = agg.Icon
          return (
            <div key={agg.type} className="group">
              <div className="flex-between mb-1.5">
                <div className="flex items-center gap-2">
                  <div className={`w-7 h-7 rounded-[var(--radius-md)] flex items-center justify-center ${agg.bgClass}`}>
                    <Icon className="w-3.5 h-3.5" style={{ color: agg.color }} aria-hidden="true" />
                  </div>
                  <span className="label-md text-on-surface">{agg.label}</span>
                  <span className="text-[10px] text-tertiary">({agg.count})</span>
                </div>
                <span className="numeric-sm text-primary">
                  ${Math.abs(agg.total).toLocaleString('en-US', { maximumFractionDigits: 0 })}
                </span>
              </div>
              <div className="relative h-2 w-full bg-[var(--slate-100)] rounded-[var(--radius-full)] overflow-hidden">
                <div
                  className="h-full rounded-[var(--radius-full)] transition-all duration-700 ease-out group-hover:opacity-80"
                  style={{
                    width: `${Math.min(100, agg.pct)}%`,
                    backgroundColor: agg.color,
                  }}
                  role="progressbar"
                  aria-valuenow={Math.round(agg.pct)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
