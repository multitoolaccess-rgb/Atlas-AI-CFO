/**
 * Multi-debt payoff strategy simulation — Avalanche vs Snowball.
 *
 * Pure-math library (no React, no DOM, no IO). Uses month-by-month
 * simulation with rollover payments when a debt is paid off.
 *
 * - **Avalanche**: Pay highest interest rate first (saves the most money).
 * - **Snowball**: Pay smallest balance first (fastest psychological wins).
 */

import type { DebtItem } from '@/lib/api'

export interface StrategyDebt {
  account_id: number
  account_name: string
  balance: number
  annualRate: number
  minimumPayment: number
}

export interface PayoffStep {
  /** Debt that was paid off in this phase. */
  account_id: number
  account_name: string
  /** Month number (cumulative from start) when this debt reached $0. */
  monthPaidOff: number
  /** Interest paid on this debt during its active period. */
  interestPaid: number
}

export interface StrategyResult {
  /** Total months to pay off ALL debts. null if never pays off. */
  totalMonths: number | null
  /** Total interest paid across all debts. */
  totalInterest: number
  /** Total amount paid (principal + interest). */
  totalPaid: number
  /** Order debts were paid off, with their payoff month and interest. */
  payoffOrder: PayoffStep[]
}

/** Internal type used during simulation — includes mutable remaining balance. */
interface ActiveDebt extends StrategyDebt {
  remaining: number
}

/** Maximum simulation horizon (30 years). */
const MAX_MONTHS = 360

/**
 * Filter debts to only those eligible for payoff simulation.
 * Requires positive balance, positive rate, and positive minimum payment.
 */
export function filterEligibleDebts(debts: DebtItem[]): StrategyDebt[] {
  return debts
    .filter((d) => d.balance > 0 && d.interest_rate != null && d.minimum_payment != null && d.minimum_payment > 0)
    .map((d) => ({
      account_id: d.account_id,
      account_name: d.account_name,
      balance: d.balance,
      annualRate: (d.interest_rate ?? 0) / 100,
      minimumPayment: d.minimum_payment ?? 0,
    }))
}

/**
 * Simulate multi-debt payoff using the given sort comparator.
 *
 * The algorithm works in phases:
 * 1. Sort active debts by the strategy's priority.
 * 2. Each debt pays its minimum; the TOP-PRIORITY debt gets all extra.
 * 3. Simulate month-by-month until the top debt is paid off.
 * 4. Roll over its minimum payment into the extra pool.
 * 5. Re-sort and repeat until all debts are paid off.
 *
 * @param debts - Eligible debts to simulate.
 * @param extraPayment - Additional monthly payment beyond minimums.
 * @param sortFn - Comparator that determines payoff priority.
 *   Avalanche: sort by rate DESC (highest first).
 *   Snowball: sort by balance ASC (smallest first).
 */
function simulatePayoff(
  debts: StrategyDebt[],
  extraPayment: number,
  sortFn: (a: ActiveDebt, b: ActiveDebt) => number,
): StrategyResult {
  if (debts.length === 0) {
    return { totalMonths: 0, totalInterest: 0, totalPaid: 0, payoffOrder: [] }
  }

  // Deep copy so we don't mutate the input
  let active: ActiveDebt[] = debts.map((d) => ({
    ...d,
    remaining: d.balance,
  }))

  let rollover = extraPayment
  let totalMonths = 0
  let totalInterest = 0
  const payoffOrder: PayoffStep[] = []
  // Track cumulative interest per debt across all phases
  const cumulativeInterest = new Map<number, number>()
  for (const d of active) cumulativeInterest.set(d.account_id, 0)

  while (active.length > 0 && totalMonths < MAX_MONTHS) {
    // Sort by strategy priority
    active.sort(sortFn)

    // Top debt gets extra payment
    const topDebt = active[0]

    // Simulate month-by-month until the top debt is paid off
    let monthsInPhase = 0

    while (topDebt.remaining > 0.01 && totalMonths + monthsInPhase < MAX_MONTHS) {
      monthsInPhase++

      // Process each active debt for this month
      for (const debt of active) {
        const monthlyRate = debt.annualRate / 12
        const interest = debt.remaining * monthlyRate
        cumulativeInterest.set(debt.account_id, (cumulativeInterest.get(debt.account_id) ?? 0) + interest)

        const isTop = debt === topDebt
        const payment = isTop
          ? debt.minimumPayment + rollover
          : debt.minimumPayment

        const principal = Math.max(0, payment - interest)
        debt.remaining = Math.max(0, debt.remaining - principal)
      }
    }

    totalMonths += monthsInPhase

    // Find all debts that are now paid off (remaining <= 0.01)
    const paidOff = active.filter((d) => d.remaining <= 0.01)
    for (const debt of paidOff) {
      rollover += debt.minimumPayment
      const interest = cumulativeInterest.get(debt.account_id) ?? 0
      totalInterest += interest
      payoffOrder.push({
        account_id: debt.account_id,
        account_name: debt.account_name,
        monthPaidOff: totalMonths,
        interestPaid: Math.round(interest * 100) / 100,
      })
    }

    active = active.filter((d) => d.remaining > 0.01)

    // Safety: if no debt was paid off in this phase, we're stuck
    if (paidOff.length === 0) {
      return { totalMonths: null, totalInterest: Math.round(totalInterest * 100) / 100, totalPaid: 0, payoffOrder }
    }
  }

  // Add interest from any debts still active at MAX_MONTHS cap
  for (const debt of active) {
    totalInterest += cumulativeInterest.get(debt.account_id) ?? 0
  }

  const totalPaid = debts.reduce((sum, d) => sum + d.balance, 0) + totalInterest

  return {
    totalMonths: totalMonths <= MAX_MONTHS ? totalMonths : null,
    totalInterest: Math.round(totalInterest * 100) / 100,
    totalPaid: Math.round(totalPaid * 100) / 100,
    payoffOrder,
  }
}

/**
 * Avalanche strategy: pay highest interest rate first.
 * Ties broken by lowest balance (pay off smaller debts first).
 */
export function simulateAvalanche(debts: StrategyDebt[], extraPayment: number = 0): StrategyResult {
  return simulatePayoff(debts, extraPayment, (a, b) => {
    // Highest rate first
    if (b.annualRate !== a.annualRate) return b.annualRate - a.annualRate
    // Tie-break: smallest balance first
    return a.remaining - b.remaining
  })
}

/**
 * Snowball strategy: pay smallest balance first.
 * Ties broken by highest interest rate (prioritize expensive debts).
 */
export function simulateSnowball(debts: StrategyDebt[], extraPayment: number = 0): StrategyResult {
  return simulatePayoff(debts, extraPayment, (a, b) => {
    // Smallest balance first
    if (a.remaining !== b.remaining) return a.remaining - b.remaining
    // Tie-break: highest rate first
    return b.annualRate - a.annualRate
  })
}
