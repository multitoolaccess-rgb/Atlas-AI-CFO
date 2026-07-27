/**
 * Vitest unit tests for `ui/lib/bookkeeping.ts` — Phase 52+ dual-
 * column Debit/Credit bookkeeping utilities.
 *
 * Covers:
 *   1. `formatBookkeepingCell` — positive renders, null/undefined
 *      fall-back to em-dash, zero / negative fall-back (defensive),
 *      mutually-exclusive single-side rendering, both-sides
 *      populated (split-pair fee + interest rows).
 *   2. `computeBookkeepingTotals` — empty input, mixed populated /
 *      legacy rows, sign-of-delta semantics ("charges - payments"
 *      positive means debt grew).
 *
 * The FX-neutral zero-amount case (amount == 0 → both NULL) is the
 * most important edge case: with both sides null the transaction
 * must drop out of the totals so a $0 FX-rate record can never
 * inflate any aggregate.
 */
import { describe, expect, it } from 'vitest'
import {
  computeBookkeepingTotals,
  formatBookkeepingCell,
} from '@/lib/bookkeeping'

describe('formatBookkeepingCell — Phase 52+ dual-column cell rendering', () => {
  it('renders a positive debit and null credit as dollar / em-dash', () => {
    const out = formatBookkeepingCell(10.68, null)
    expect(out.debitDisplay).toBe('$10.68')
    expect(out.creditDisplay).toBe('\u2014')
    expect(out.populated).toBe(true)
  })

  it('renders a positive credit and null debit as em-dash / dollar', () => {
    const out = formatBookkeepingCell(null, 25.0)
    expect(out.debitDisplay).toBe('\u2014')
    expect(out.creditDisplay).toBe('$25.00')
    expect(out.populated).toBe(true)
  })

  it('renders both sides populated (split-pair fee + interest rows)', () => {
    const out = formatBookkeepingCell(2.5, 100.0)
    expect(out.debitDisplay).toBe('$2.50')
    expect(out.creditDisplay).toBe('$100.00')
    expect(out.populated).toBe(true)
  })

  it('renders em-dash for both sides when both are null', () => {
    const out = formatBookkeepingCell(null, null)
    expect(out.debitDisplay).toBe('\u2014')
    expect(out.creditDisplay).toBe('\u2014')
    expect(out.populated).toBe(false)
  })

  it('renders em-dash for both sides when both are undefined', () => {
    const out = formatBookkeepingCell(undefined, undefined)
    expect(out.debitDisplay).toBe('\u2014')
    expect(out.creditDisplay).toBe('\u2014')
    expect(out.populated).toBe(false)
  })

  it('treats zero / negative as em-dash on the offending column (defensive)', () => {
    // Parser contract is that debit/credit are non-negative when
    // populated, but if the BE ever sends 0 or a negative the
    // formatter falls back gracefully to em-dash on that column
    // (rather than rendering "$0.00" or "$−5.00"). The other
    // column still renders if it carries positive data so the
    // row stays informative when only one side was malformed.
    expect(formatBookkeepingCell(0, 0).debitDisplay).toBe('\u2014')
    expect(formatBookkeepingCell(0, 0).creditDisplay).toBe('\u2014')
    expect(formatBookkeepingCell(0, 0).populated).toBe(false)
    const splitNegDebit = formatBookkeepingCell(-5, 5)
    expect(splitNegDebit.debitDisplay).toBe('\u2014')
    expect(splitNegDebit.creditDisplay).toBe('$5.00')
    expect(splitNegDebit.populated).toBe(true)
    const splitNegCredit = formatBookkeepingCell(5, -5)
    expect(splitNegCredit.debitDisplay).toBe('$5.00')
    expect(splitNegCredit.creditDisplay).toBe('\u2014')
    expect(splitNegCredit.populated).toBe(true)
    expect(formatBookkeepingCell(5.0, 0).creditDisplay).toBe('\u2014')
    expect(formatBookkeepingCell(0, 5.0).debitDisplay).toBe('\u2014')
  })

  it('formats thousands separators correctly', () => {
    const out = formatBookkeepingCell(1234.5, 67890.25)
    expect(out.debitDisplay).toBe('$1,234.50')
    expect(out.creditDisplay).toBe('$67,890.25')
  })
})

describe('computeBookkeepingTotals — Phase 52+ aggregate bookkeeping', () => {
  it('returns zero totals on an empty list', () => {
    const totals = computeBookkeepingTotals([])
    expect(totals.charges).toBe(0)
    expect(totals.payments).toBe(0)
    expect(totals.netDebtDelta).toBe(0)
    expect(totals.populatedRows).toBe(0)
  })

  it('returns zero totals when every row is legacy (both sides null)', () => {
    // Simulates a checking account: imported pre-Phase 52+, never
    // had debit/credit columns. Must NOT contribute to the
    // bookkeeping strip.
    const totals = computeBookkeepingTotals([
      { id: 1, debit: null, credit: null },
      { id: 2, debit: undefined, credit: undefined },
      { id: 3 },
    ])
    expect(totals.charges).toBe(0)
    expect(totals.payments).toBe(0)
    expect(totals.populatedRows).toBe(0)
  })

  it('sums charges and payments across populated rows', () => {
    const totals = computeBookkeepingTotals([
      { id: 1, debit: 10.68, credit: null },     // purchase
      { id: 2, debit: null, credit: 25.0 },       // payment
      { id: 3, debit: 4.99, credit: null },       // purchase
      { id: 4, debit: null, credit: null },       // FX-neutral / legacy
    ])
    expect(totals.charges).toBeCloseTo(15.67, 2)
    expect(totals.payments).toBe(25.0)
    expect(totals.netDebtDelta).toBeCloseTo(-9.33, 2) // charges - payments
    expect(totals.populatedRows).toBe(3)
  })

  it('treats net delta as positive when charges exceed payments (debt grew)', () => {
    const totals = computeBookkeepingTotals([
      { id: 1, debit: 100, credit: null },
      { id: 2, debit: null, credit: 20 },
    ])
    expect(totals.charges).toBe(100)
    expect(totals.payments).toBe(20)
    expect(totals.netDebtDelta).toBe(80)
    expect(totals.netDebtDelta > 0).toBe(true)
  })

  it('treats net delta as negative when payments exceed charges (debt shrank)', () => {
    const totals = computeBookkeepingTotals([
      { id: 1, debit: 20, credit: null },
      { id: 2, debit: null, credit: 100 },
    ])
    expect(totals.charges).toBe(20)
    expect(totals.payments).toBe(100)
    expect(totals.netDebtDelta).toBe(-80)
    expect(totals.netDebtDelta < 0).toBe(true)
  })

  it('handles a split-pair row (both sides populated in one row)', () => {
    // Edge case: a statement row that posts a fee AS A DEBIT and
    // an associated credit-card credit AS A CREDIT on the same
    // business day. Both sides contribute independently.
    const totals = computeBookkeepingTotals([
      { id: 1, debit: 2.5, credit: 50.0 },
    ])
    expect(totals.charges).toBe(2.5)
    expect(totals.payments).toBe(50.0)
    expect(totals.netDebtDelta).toBe(-47.5)
    expect(totals.populatedRows).toBe(1)
  })

  it('counts partly-typed rows (only debit OR only credit) as populated', () => {
    // Type-safety: even if the consumer passes a record that
    // exposes debit but not credit (or vice-versa), the helper
    // still treats them as populated for the purposes of the
    // bookkeeping strip. This mirrors the FE renderer's
    // `populated` cell-level check.
    const totals = computeBookkeepingTotals([
      { id: 1, debit: 5 },
      { id: 2, credit: 5 },
    ])
    expect(totals.populatedRows).toBe(2)
    expect(totals.charges).toBe(5)
    expect(totals.payments).toBe(5)
  })

  it('clamps negative debit / credit values to 0 (defensive against malformed BE rows)', () => {
    // Reviewer hardening: a future BE upgrade could ship a signed
    // negative debit / credit (parser contract today is
    // non-negative, but the BE has shipped signed values before).
    // Without the clamp a single negative row would silently
    // deflate charges / payments and produce a misleading
    // netDebtDelta — the per-cell formatter already shows em-dash
    // for negatives so the totals must agree with what the user
    // sees in the table.
    const totals = computeBookkeepingTotals([
      { id: 1, debit: 100, credit: 20 },     // baseline
      { id: 2, debit: -50, credit: 5 },       // malformed: negative debit clamps to 0
      { id: 3, debit: 10, credit: -99 },     // malformed: negative credit clamps to 0
    ])
    expect(totals.charges).toBe(110) // 100 + 0 + 10
    expect(totals.payments).toBe(25) // 20 + 5 + 0
    expect(totals.netDebtDelta).toBe(85) // 110 - 25
    expect(totals.populatedRows).toBe(3)
  })
})
