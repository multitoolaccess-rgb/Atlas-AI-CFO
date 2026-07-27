'use client'

import { Clock } from 'lucide-react'
import type { Transaction } from '@/lib/api'
import {
  computeBookkeepingTotals,
  formatBookkeepingCell,
} from '@/lib/bookkeeping'

interface RecentActivityProps {
  transactions: Transaction[]
  loading?: boolean
}

function formatAmount(amount: number): { display: string; positive: boolean } {
  const positive = amount > 0
  return {
    positive,
    display:
      (positive ? '+' : '\u2212') +
      '$' +
      Math.abs(amount).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
  }
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '\u2014'
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  } catch {
    return String(iso)
  }
}

// Phase 52+ — short delta-formatter reused by the bookkeeping footer
// under the table. Mirrors the ``formatAmount``'s +/- convention
// ``(use + for positive, − for negative)`` so the footer reads the
// same as the rows. Returns ``null`` when the value is zero so the
// caller can render an em-dash instead of "$0.00" noise.
function formatNetDelta(delta: number): string {
  if (delta === 0) return '\u2014'
  const abs = Math.abs(delta).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return (delta > 0 ? '+' : '\u2212') + '$' + abs
}

export default function RecentActivity({ transactions, loading }: RecentActivityProps) {
  // Phase 52+ — pre-compute bookkeeping totals once for the visible
  // set so the footer can render a "Net debt activity today: +$X"
  // line when at least one of the latest-5 rows carries populated
  // debit / credit columns. Skipped silently when the visible set
  // is legacy (checking / savings rows where both columns are NULL).
  const bookkeepingTotals = computeBookkeepingTotals(transactions)
  return (
    <div className="card p-6 mt-8">
      <div className="flex-between mb-5">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[var(--primary-50)] flex items-center justify-center border border-[var(--primary-200)]">
            <Clock className="w-4 h-4 text-[var(--primary-600)]" aria-hidden="true" />
          </div>
          <div>
            <h3 className="headline-md text-primary">Recent Activity</h3>
            <p className="text-xs text-tertiary">{transactions.length} latest transactions</p>
          </div>
        </div>
        <a className="label-md text-primary hover:text-primary-700 hover:underline transition-colors" href="#">
          View All
        </a>
      </div>

      {loading ? (
        <p className="text-sm text-secondary">Loading transactions\u2026</p>
      ) : transactions.length === 0 ? (
        <p className="text-sm text-secondary">
          No transactions yet. Upload a CSV / PDF / OFX statement via the imports tab to get started.
        </p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="text-left">
                <tr className="bg-gradient-to-r from-[var(--primary-200)]/20 to-transparent">
                  <th className="py-3 px-3 first:rounded-l-lg last:rounded-r-lg label-md text-[var(--primary-700)]">Description</th>
                  <th className="py-3 px-3 label-md text-[var(--primary-700)]">Merchant</th>
                  {/*
                    Phase 52+ — Debit / Credit columns. Mirror of the
                    Activity page's table: surface the bank's native
                    bookkeeping view directly so the user can see
                    expenses (debit) vs payments (credit) at a glance
                    on the dashboard. Empty / em-dash for legacy rows
                    so a checkings-only snapshot reads cleanly.
                  */}
                  <th
                    className="py-3 px-3 label-md text-[var(--primary-700)] whitespace-nowrap"
                    title="Charge posted to the account (debt increases). Bank-statement column."
                  >
                    Debit
                  </th>
                  <th
                    className="py-3 px-3 label-md text-[var(--primary-700)] whitespace-nowrap"
                    title="Payment / refund applied (debt decreases). Bank-statement column."
                  >
                    Credit
                  </th>
                  <th className="py-3 px-3 label-md text-[var(--primary-700)]">Amount</th>
                  <th className="py-3 px-3 label-md text-[var(--primary-700)]">Status</th>
                  <th className="py-3 px-3 label-md text-[var(--primary-700)] text-right">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/10">
                {transactions.map((tx, idx) => {
                  const { display, positive } = formatAmount(tx.amount)
                  const {
                    debitDisplay,
                    creditDisplay,
                    populated: bookkeepingPopulated,
                  } = formatBookkeepingCell(tx.debit, tx.credit)
                  const StatusBadge = (
                    <span
                      className={`px-2 py-1 rounded-md text-[10px] font-bold uppercase ${
                        tx.is_pending
                          ? 'bg-surface-container-high text-on-surface-variant'
                          : 'bg-secondary/15 text-secondary-container'
                      }`}
                    >
                      {tx.is_pending ? 'Pending' : 'Completed'}
                    </span>
                  )
                  return (
                    <tr key={tx.id} className={`group transition-colors ${idx % 2 === 0 ? 'bg-[var(--bg-tertiary)]/30' : ''} hover:bg-[var(--primary-50)]/60`} data-testid={`recent-activity-row-${tx.id}`}>
                      <td className="py-3.5 px-3">
                        <span className="body-md font-semibold text-on-surface">{tx.description}</span>
                      </td>
                      <td className="py-3.5 px-3 body-md text-on-surface-variant">
                        {tx.merchant_name ?? '\u2014'}
                      </td>
                      <td
                        className={`py-3.5 px-3 body-md font-mono tabular-nums whitespace-nowrap ${
                          bookkeepingPopulated && tx.debit
                            ? 'text-[var(--danger-700)] font-semibold'
                            : 'text-tertiary'
                        }`}
                        data-testid={`recent-activity-row-${tx.id}-debit`}
                      >
                        {debitDisplay}
                      </td>
                      <td
                        className={`py-3.5 px-3 body-md font-mono tabular-nums whitespace-nowrap ${
                          bookkeepingPopulated && tx.credit
                            ? 'text-[var(--success-700)] font-semibold'
                            : 'text-tertiary'
                        }`}
                        data-testid={`recent-activity-row-${tx.id}-credit`}
                      >
                        {creditDisplay}
                      </td>
                      <td
                        className={`py-3.5 px-3 body-md font-bold ${
                          bookkeepingPopulated
                            ? 'text-tertiary font-normal'
                            : positive
                              ? 'text-success-600'
                              : 'text-error'
                        }`}
                        data-testid={`recent-activity-row-${tx.id}-amount`}
                        title={
                          bookkeepingPopulated
                            ? 'Amount = Debit − Credit. Already shown in the Debit/Credit columns for this row.'
                            : 'Signed amount (legacy single-column import).'
                        }
                      >
                        {bookkeepingPopulated ? '\u2014' : display}
                      </td>
                      <td className="py-3.5 px-3">{StatusBadge}</td>
                      <td className="py-3.5 px-3 body-md text-on-surface-variant text-right">
                        {formatDate(tx.transaction_date)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {/*
            Phase 52+ — bookkeeping footer. Renders ONLY when at
            least one of the latest-5 rows carries populated
            debit / credit data so a checkings-only dashboard
            stays compact (no useless em-dash strip). Three
            up-front numbers — Charges / Payments / Net Δ — give
            the user a single-glance read of the latest credit-card
            activity without bouncing them to /activity.
          */}
          {bookkeepingTotals.populatedRows > 0 && (
            <div
              className="
                mt-3 pt-3 border-t border-outline-variant/20
                flex items-center justify-end gap-4 flex-wrap
              "
              data-testid="recent-activity-bookkeeping-footer"
              role="group"
              aria-label="Recent bookkeeping at a glance"
            >
              <span className="label-xs uppercase tracking-wider text-tertiary">
                Bookkeeping
              </span>
              <span
                className="label-sm text-[var(--danger-700)] font-semibold tabular-nums"
                data-testid="recent-activity-bookkeeping-charges"
              >
                Charges ${
                  bookkeepingTotals.charges.toLocaleString('en-US', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })
                }
              </span>
              <span
                className="label-sm text-[var(--success-700)] font-semibold tabular-nums"
                data-testid="recent-activity-bookkeeping-payments"
              >
                Payments ${
                  bookkeepingTotals.payments.toLocaleString('en-US', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })
                }
              </span>
              <span
                className={`label-sm font-semibold tabular-nums ${
                  bookkeepingTotals.netDebtDelta > 0
                    ? 'text-[var(--danger-700)]'
                    : bookkeepingTotals.netDebtDelta < 0
                      ? 'text-[var(--success-700)]'
                      : 'text-tertiary'
                }`}
                data-testid="recent-activity-bookkeeping-net-delta"
              >
                Net {formatNetDelta(bookkeepingTotals.netDebtDelta)}
              </span>
            </div>
          )}
        </>
      )}
    </div>
  )
}
