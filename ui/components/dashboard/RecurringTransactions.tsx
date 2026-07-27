'use client'

import { useMemo } from 'react'
import { Repeat } from 'lucide-react'
import { formatNumber } from '@/lib/format'
import type { Transaction } from '@/lib/api'
import ExpandableCard from '@/components/dashboard/ExpandableCard'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface RecurringTransactionsProps {
  transactions: Transaction[]
  loading?: boolean
  className?: string
}

interface DetectedSubscription {
  merchant: string
  avgAmount: number
  frequency: 'weekly' | 'biweekly' | 'monthly' | 'quarterly' | 'yearly'
  frequencyLabel: string
  occurrences: number
  lastDate: string
  estimatedMonthly: number
}

// ---------------------------------------------------------------------------
// Detection logic
// ---------------------------------------------------------------------------

/** Normalize merchant name for grouping. */
function normalizeMerchant(txn: Transaction): string {
  const raw = (txn.merchant_name || txn.description || '').trim().toUpperCase()
  // Strip common noise: card numbers, reference IDs, dates
  return raw
    .replace(/\b\d{4,}\b/g, '')           // long numbers (card refs, IDs)
    .replace(/\b(?:REF|CONF|AUTH)\b/gi, '') // reference prefixes
    .replace(/\s+/g, ' ')
    .trim()
}

/** Classify the interval between two dates into a frequency bucket. */
function classifyInterval(avgDays: number): DetectedSubscription['frequency'] | null {
  if (avgDays >= 5 && avgDays <= 9) return 'weekly'
  if (avgDays >= 12 && avgDays <= 16) return 'biweekly'
  if (avgDays >= 25 && avgDays <= 35) return 'monthly'
  if (avgDays >= 80 && avgDays <= 100) return 'quarterly'
  if (avgDays >= 350 && avgDays <= 380) return 'yearly'
  return null
}

const FREQUENCY_LABELS: Record<DetectedSubscription['frequency'], string> = {
  weekly: 'Weekly',
  biweekly: 'Biweekly',
  monthly: 'Monthly',
  quarterly: 'Quarterly',
  yearly: 'Yearly',
}

const MONTHLY_MULTIPLIER: Record<DetectedSubscription['frequency'], number> = {
  weekly: 4.33,
  biweekly: 2.17,
  monthly: 1,
  quarterly: 1 / 3,
  yearly: 1 / 12,
}

/** Detect recurring subscriptions from a list of transactions. */
export function detectRecurring(transactions: Transaction[]): DetectedSubscription[] {
  // Group by normalized merchant
  const groups = new Map<string, Transaction[]>()
  for (const txn of transactions) {
    const key = normalizeMerchant(txn)
    if (!key || key.length < 2) continue
    const group = groups.get(key) ?? []
    group.push(txn)
    groups.set(key, group)
  }

  const results: DetectedSubscription[] = []

  for (const [merchant, txns] of groups) {
    // Need at least 2 transactions to detect a pattern
    if (txns.length < 2) continue

    // Sort by date ascending
    const sorted = [...txns].sort(
      (a, b) => new Date(a.transaction_date).getTime() - new Date(b.transaction_date).getTime(),
    )

    // Compute intervals between consecutive transactions
    const intervals: number[] = []
    for (let i = 1; i < sorted.length; i++) {
      const days =
        (new Date(sorted[i].transaction_date).getTime() -
          new Date(sorted[i - 1].transaction_date).getTime()) /
        (1000 * 60 * 60 * 24)
      intervals.push(days)
    }

    // Average interval
    const avgDays = intervals.reduce((s, d) => s + d, 0) / intervals.length

    // Classify frequency
    const frequency = classifyInterval(avgDays)
    if (!frequency) continue

    // Check consistency: at least 70% of intervals should be within ±30% of average
    const tolerance = avgDays * 0.3
    const consistent = intervals.filter((d) => Math.abs(d - avgDays) <= tolerance).length
    if (consistent / intervals.length < 0.7) continue

    // Compute average amount (use absolute value since expenses are negative)
    const avgAmount =
      Math.abs(txns.reduce((s, t) => s + Math.abs(t.amount), 0)) / txns.length

    // Skip micro-transactions (< $1) and very large amounts
    if (avgAmount < 1 || avgAmount > 50_000) continue

    const estimatedMonthly = avgAmount * MONTHLY_MULTIPLIER[frequency]

    results.push({
      merchant: txns[0].merchant_name || txns[0].description || merchant,
      avgAmount,
      frequency,
      frequencyLabel: FREQUENCY_LABELS[frequency],
      occurrences: txns.length,
      lastDate: sorted[sorted.length - 1].transaction_date,
      estimatedMonthly,
    })
  }

  // Sort by estimated monthly cost (highest first)
  results.sort((a, b) => b.estimatedMonthly - a.estimatedMonthly)
  return results
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function RecurringTransactions({
  transactions,
  loading,
  className = '',
}: RecurringTransactionsProps) {
  const subscriptions = useMemo(() => detectRecurring(transactions), [transactions])

  const totalMonthly = subscriptions.reduce((s, sub) => s + sub.estimatedMonthly, 0)

  const expandedContent =
    subscriptions.length > 0 ? (
      <div className="space-y-2">
        {subscriptions.map((sub) => (
          <div
            key={sub.merchant}
            className="flex items-center justify-between p-3 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-color)]"
          >
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-on-surface truncate">{sub.merchant}</p>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-xs text-[var(--text-tertiary)]">
                  {sub.frequencyLabel} · {sub.occurrences} occurrences
                </span>
              </div>
            </div>
            <div className="text-right flex-shrink-0 ml-3">
              <p className="text-sm font-bold text-on-surface">{formatNumber(sub.avgAmount)}</p>
              <p className="text-xs text-[var(--text-tertiary)]">per {sub.frequency === 'monthly' ? 'mo' : sub.frequency === 'weekly' ? 'wk' : sub.frequency === 'yearly' ? 'yr' : sub.frequency.slice(0, 2)}</p>
            </div>
          </div>
        ))}
      </div>
    ) : undefined

  if (subscriptions.length === 0 && !loading) return null

  return (
    <ExpandableCard
      title="Subscriptions & Recurring"
      subtitle={
        subscriptions.length > 0
          ? `${subscriptions.length} detected · ~${formatNumber(totalMonthly)}/mo`
          : 'Scanning for patterns…'
      }
      icon={<Repeat className="w-4 h-4 text-[var(--primary-600)]" />}
      expandedContent={expandedContent}
      className={className}
    >
      {loading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-14 w-full rounded-lg" />
          ))}
        </div>
      ) : subscriptions.length === 0 ? (
        <div className="text-center py-6">
          <Repeat className="w-8 h-8 text-[var(--text-tertiary)] mx-auto mb-2 opacity-50" />
          <p className="text-sm text-[var(--text-tertiary)]">
            No recurring patterns detected yet.
          </p>
          <p className="text-xs text-[var(--text-tertiary)] mt-1">
            Add more transactions over time for pattern detection.
          </p>
        </div>
      ) : (
        <>
          {/* Top 3 summary cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-2">
            {subscriptions.slice(0, 3).map((sub) => (
              <div
                key={sub.merchant}
                className="p-3 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-color)]"
              >
                <p className="text-xs font-semibold text-on-surface truncate mb-1">{sub.merchant}</p>
                <p className="text-base font-bold text-on-surface">{formatNumber(sub.avgAmount)}</p>
                <p className="text-xs text-[var(--text-tertiary)]">{sub.frequencyLabel}</p>
              </div>
            ))}
          </div>
        </>
      )}
    </ExpandableCard>
  )
}
