/**
 * Phase 52+ — dual-column Debit/Credit bookkeeping utilities.
 *
 * Banks report credit-card activity as two unsigned columns:
 *
 *   Debit  = a charge posted to your account  (debt ↑, money LEFT)
 *   Credit = a payment / refund applied        (debt ↓, money ENTERED)
 *
 * This module exposes two pure helpers used by ``/activity``:
 *
 *   - ``formatBookkeepingCell`` — render the per-cell display string
 *     + a `populated` sentinel so the row renderer can pick the
 *     right tone class without inspecting booleans inline.
 *   - ``computeBookkeepingTotals`` — sum charges / payments
 *     across a transaction list, skipping rows where both sides
 *     are ``null`` (FX-neutral zero-amount rows + legacy
 *     single-column imports that never carried bookkeeping data).
 *
 * Both are functional (no module state, no React hooks) so they
 * live outside ``app/activity/page.tsx`` and ship testable from
 * vitest without spinning up a jsdom harness.
 */

export interface BookkeepingCellRender {
  /** Display string for the Debit value (e.g. "$10.68" or "—"). */
  debitDisplay: string
  /** Display string for the Credit value (e.g. "$25.00" or "—"). */
  creditDisplay: string
  /** True when at least one side has a positive renderable value. */
  populated: boolean
}

function _fmtMoney(v: number): string {
  return (
    '$' +
    v.toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  )
}

/**
 * Format a single row's debit / credit values for table display.
 *
 * Both values must be strictly positive to render as currency —
 * a non-positive (or ``null`` / ``undefined``) value falls back
 * to the em-dash placeholder so the table stays aligned. This
 * matches the bank-statement invariant where Debit and Credit
 * columns are mutually exclusive per row under the new Phase
 * 52+ dual-column convention (a charge cannot also be a payment).
 *
 * @param debit  Non-negative amount posted as a charge. ``null`` /
 *               ``undefined`` renders as "—" (the row is not a charge).
 * @param credit Non-negative amount posted as a payment / refund.
 *               ``null`` / ``undefined`` renders as "—".
 */
export function formatBookkeepingCell(
  debit: number | null | undefined,
  credit: number | null | undefined,
): BookkeepingCellRender {
  const debitVal = typeof debit === 'number' && debit > 0 ? debit : null
  const creditVal = typeof credit === 'number' && credit > 0 ? credit : null
  return {
    debitDisplay: debitVal !== null ? _fmtMoney(debitVal) : '\u2014',
    creditDisplay: creditVal !== null ? _fmtMoney(creditVal) : '\u2014',
    populated: debitVal !== null || creditVal !== null,
  }
}

export interface BookkeepingTotals {
  /** Sum of all populated `debit` values (charges). */
  charges: number
  /** Sum of all populated `credit` values (payments). */
  payments: number
  /**
   * Net change to outstanding debt for the period:
   * ``charges - payments``. Positive = debt grew, negative = debt shrank.
   */
  netDebtDelta: number
  /** Number of rows that contributed to the totals (rows with at least
   *  one populated side). */
  populatedRows: number
}

/**
 * Aggregate debit / credit totals across a transaction list.
 *
 * Skips rows where BOTH ``debit`` and ``credit`` are ``null`` /
 * ``undefined`` so legacy single-column imports (where the BE
 * never persisted bookkeeping values) don't pollute the sum.
 * Rows with only ONE side populated contribute that side; rows
 * with BOTH sides contribute both (the bank-statement importer
 * populates both only for split-pair fee + interest rows).
 *
 * Defensive clamp: a future BE upgrade that ships a signed
 * (negative) ``debit`` or ``credit`` would otherwise silently
 * deflate ``charges`` / ``payments`` and produce a misleading
 * ``netDebtDelta``. We clamp each side to ``Math.max(0, side)``
 * so a single malformed row can never break the displayed
 * aggregate — the per-cell formatter already handles negatives
 * visually with an em-dash, so the totals agree with what the
 * user sees in the table.
 *
 * Asymmetry to preserve: ``populatedRows`` still COUNTS a
 * malformed (negative-side) row even though that row's bad
 * contribution is zeroed. This keeps the strip honest about
 * "N of M rows have debit/credit columns" without ignoring
 * malformed input — the per-cell formatter would render the
 * row as a partial table entry, and the aggregate should
 * agree. A future refactor that unifies the two into the
 * same null-like semantics should reconsider whether to also
 * drop the row from the count.
 *
 * Loops are O(N); no per-row allocations beyond the running
 * totals so the cost is negligible against the activity page's
 * 500-row cap.
 */
export function computeBookkeepingTotals<
  T extends { debit?: number | null; credit?: number | null },
>(transactions: T[]): BookkeepingTotals {
  let charges = 0
  let payments = 0
  let count = 0
  for (const t of transactions) {
    const hasD = typeof t.debit === 'number'
    const hasC = typeof t.credit === 'number'
    if (!hasD && !hasC) continue
    if (hasD) charges += Math.max(0, t.debit as number)
    if (hasC) payments += Math.max(0, t.credit as number)
    count += 1
  }
  return {
    charges,
    payments,
    netDebtDelta: charges - payments,
    populatedRows: count,
  }
}
