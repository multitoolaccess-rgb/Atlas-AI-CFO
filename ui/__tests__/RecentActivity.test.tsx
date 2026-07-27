/**
 * Vitest unit test for `ui/components/dashboard/RecentActivity.tsx`.
 *
 * Phase 54+ — covers the conditional Amount-column-hiding behaviour
 * introduced in plan item 4: rows where DUAL-column bookkeeping is
 * populated (`debit` OR `credit` > 0) render an em-dash in the Amount
 * cell (because `Debit − Credit` already conveys the signed delta);
 * legacy single-column imports keep the signed Amount visible. The
 * invariant lives in three places and we pin all of them:
 *
 *   1. ``formatBookkeepingCell`` returns ``populated: true`` exactly
 *      when at least one side is a positive number.
 *   2. RecentActivity passes ``bookkeepingPopulated`` as the gate.
 *   3. RecentActivity swaps the cell content to ``'\u2014'`` when
 *      populated, dropping the eyebrow-bait "+$X.XX" / "−$X.XX"
 *      formatting so the dual-column row reads as "already shown
 *      in the columns to the left".
 *
 * The amount-em-dash on dual-column rows is the canonical Phase 54+
 * UX: prevent the user from the mental tax of adding the two
 * columns themselves when the bank-statement canonical view is right
 * there in front of them.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

// Mock `lucide-react` Clock so jsdom doesn't blow up on the lucide
// dev-mode barrel (it does some window-intersection things on import
// that jsdom can't satisfy). The important property is: recent
// activity still renders without crashing so the test can assert
// cell content. We stub the icon component to render a span with the
// testid we want for the assertion selector.
vi.mock('lucide-react', () => ({
  Clock: (props: { className?: string; 'aria-hidden'?: boolean }) => (
    <span
      data-testid="recent-activity-clock-icon"
      className={props.className}
      aria-hidden={props['aria-hidden']}
    />
  ),
}))

import RecentActivity from '@/components/dashboard/RecentActivity'
import type { Transaction } from '@/lib/api'

// Minimal fixtures — the Transaction type lives in ui/lib/api.ts;
// every field is plucked by RecentActivity via the canonical keys.
const makeTxn = (overrides: Partial<Transaction>): Transaction => ({
  id: 1,
  description: 'Citi refund',
  amount: -12.34,
  debit: null,
  credit: null,
  transaction_date: '2026-07-01T00:00:00Z',
  merchant_name: 'Citi',
  is_pending: false,
  account_id: 42,
  account_name: 'Citi Card',
  account_type: 'credit_card',
  category_id: null,
  category_name: null,
  ...overrides,
})

describe('RecentActivity — Amount column gating (Phase 54+ item 4)', () => {
  it('renders em-dash in Amount cell when bookkeepingPopulated is true', () => {
    // Phase 52+ dual-column row: refill → amount=positive credit,
    // amount signed is -12.34 (bank-statement convention).
    const dualColumnRow = makeTxn({
      id: 100,
      amount: -12.34,
      debit: 0, // Phase 54+: amount > 0 means credit fills; the negative
      credit: 12.34, // amount < 0 here is just because the parent
    })
    // NOTE — the bookkeeping helper validates "exactly one side > 0";
    // a row with `debit=12.34, credit=null` is the canonical positive
    // case (a charge posted). For a -8.00 amount (refund), the bank
    // canonical form is `credit=8.00, debit=null`. Switch the
    // override to make the helper happy AND test the right branch:
    const canonicalRefundRow = makeTxn({
      id: 100,
      amount: -8.0,
      debit: null,
      credit: 8.0,
      description: 'Refund',
    })
    render(<RecentActivity transactions={[canonicalRefundRow]} />)
    // bookkeepingPopulated is true → Amount cell == em-dash.
    const amountCell = screen.getByTestId(
      'recent-activity-row-100-amount',
    )
    expect(amountCell.textContent).toBe('\u2014')
    // The credit cell should still render the value (helper's job).
    expect(screen.getByTestId('recent-activity-row-100-credit')).toHaveTextContent(
      '$8.00',
    )
    // Suppress unused warning for the (intentionally malformed) first fixture.
    void dualColumnRow
  })

  it('renders the signed amount for legacy single-column rows', () => {
    const legacyRow = makeTxn({
      id: 200,
      amount: 1743.22,
      debit: null,
      credit: null,
      description: 'Direct deposit',
      merchant_name: 'Chase',
    })
    render(<RecentActivity transactions={[legacyRow]} />)
    const amountCell = screen.getByTestId(
      'recent-activity-row-200-amount',
    )
    // Sign convention: amount > 0 → green, prefix `+`.
    expect(amountCell.textContent).toMatch(/\+?\$1,743\.22/)
    // Tone class landed on the cell (sanity check that the className
    // branch picked the legacy-positive path, not the populated-grey
    // branch).
    expect(amountCell.className).toContain('text-success-600')
  })

  it('renders em-dash on a negative-amount debit row (canonical charge)', () => {
    // Phase 52+ canonical: a posted charge shows as amount<0 +
    // debit>0 + credit=NULL. bookkeepingPopulated should still gate
    // the Amount cell.
    const chargeRow = makeTxn({
      id: 300,
      amount: -25.0,
      debit: 25.0,
      credit: null,
      description: 'BURRITOS',
    })
    render(<RecentActivity transactions={[chargeRow]} />)
    const amountCell = screen.getByTestId(
      'recent-activity-row-300-amount',
    )
    expect(amountCell.textContent).toBe('\u2014')
    // And the debit cell stays visible.
    expect(screen.getByTestId('recent-activity-row-300-debit')).toHaveTextContent(
      '$25.00',
    )
  })

  it('zero-amount legacy row keeps the signed Amount visible (boundary case)', () => {
    // Phase 52+ invariant: ``formatBookkeepingCell`` requires the side
    // to be ``> 0`` to count as populated. A row with `amount=0.0`
    // AND `debit=0.0, credit=0.0` (or both NULL) is NOT bookkeeping-
    // populated — its signed Amount = 0.00 should still render through
    // the Amount cell so the user sees the literal zero, not an em-
    // dash that would falsely imply "see Debit/Credit columns".
    const zeroRow = makeTxn({
      id: 500,
      amount: 0.0,
      debit: 0.0,
      credit: 0.0,
      description: 'FX-neutral inter-account transfer',
    })
    render(<RecentActivity transactions={[zeroRow]} />)
    const amountCell = screen.getByTestId('recent-activity-row-500-amount')
    // bookkeepingPopulated is FALSE → fall through to the legacy
    // branch. ``formatAmount(0)`` returns ``positive: false`` so the
    // prefix is the en-dash (U+2212), producing ``'\u2212$0.00'``.
    // Tightened assertion: anchor the EXACT legacy rendered form so a
    // regression where the gate starts firing on amount=0 (e.g. a
    // helper refactor that changes "strictly positive" to "non-null")
    // would FAIL this test rather than silently match ``$0.00`` via
    // a substring.
    expect(amountCell.textContent).toBe('\u2212$0.00')
    // Tone className must carry the legacy `text-error` branch (the
    // ``positive === false`` path), NOT the bookkeepingPopulated
    // ``text-tertiary font-normal`` tone. If the gate wrongly fires
    // for zero-amount rows, the className test fails.
    expect(amountCell.className).toContain('text-error')
    expect(amountCell.className).not.toContain('text-tertiary')
  })

  it('mixed batch: each row independently gates its Amount cell', () => {
    // One dual-column + one legacy in the same render — the
    // bookkeeping helper is per-row, not table-wide.
    render(
      <RecentActivity
        transactions={[
          makeTxn({
            id: 401,
            amount: -15.0,
            debit: 15.0,
            credit: null,
            description: 'PayPal charge',
          }),
          makeTxn({
            id: 402,
            amount: 900.0,
            debit: null,
            credit: null,
            description: 'ACH transfer',
            merchant_name: 'Bank',
          }),
        ]}
      />,
    )
    // Row 401 (dual-column) → em-dash.
    expect(
      screen.getByTestId('recent-activity-row-401-amount').textContent,
    ).toBe('\u2014')
    // Row 402 (legacy) → the signed value.
    expect(
      screen.getByTestId('recent-activity-row-402-amount').textContent,
    ).toMatch(/\$900\.00/)
  })
})
