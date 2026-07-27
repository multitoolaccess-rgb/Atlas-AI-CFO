/**
 * Pure-math amortization library for debt payoff projections.
 *
 * Framework-free (no React, no DOM, no IO) so tests run in a single tick.
 * All functions are referentially transparent — same inputs always yield
 * the same numeric output.
 */

export interface AmortizationInput {
  /** Current balance (positive = amount owed). */
  balance: number
  /** Annual interest rate as a decimal (0.065 = 6.5%). */
  annualRate: number
  /** Monthly payment amount. */
  monthlyPayment: number
  /** Number of months to project. Defaults to 120 (10 years). */
  months?: number
}

export interface AmortizationMonth {
  /** Month number (1-indexed). */
  month: number
  /** Remaining balance at end of month. */
  balance: number
  /** Interest portion of this month's payment. */
  interestPaid: number
  /** Principal portion of this month's payment. */
  principalPaid: number
  /** Cumulative interest paid to date. */
  totalInterest: number
  /** Cumulative principal paid to date. */
  totalPrincipal: number
}

export interface PayoffResult {
  /** Months until balance reaches zero. null if never pays off. */
  payoffMonths: number | null
  /** Total interest paid over the life of the loan. */
  totalInterest: number
  /** Total amount paid (principal + interest). */
  totalPaid: number
  /** Monthly amortization schedule. */
  schedule: AmortizationMonth[]
}

/**
 * Calculate the month-by-month amortization schedule for a debt.
 *
 * If the monthly payment doesn't cover the interest (negative amortization),
 * the schedule will show increasing balances and `payoffMonths` will be null.
 */
export function calculateAmortization(input: AmortizationInput): PayoffResult {
  const { balance, annualRate, monthlyPayment } = input
  const months = input.months ?? 120

  if (balance <= 0 || monthlyPayment <= 0) {
    return { payoffMonths: 0, totalInterest: 0, totalPaid: 0, schedule: [] }
  }

  const monthlyRate = annualRate / 12
  const schedule: AmortizationMonth[] = []
  let remaining = balance
  let cumulativeInterest = 0
  let cumulativePrincipal = 0
  let payoffMonths: number | null = null

  for (let m = 1; m <= months; m++) {
    const interestPaid = remaining * monthlyRate
    let principalPaid = monthlyPayment - interestPaid

    // If payment doesn't cover interest, debt grows
    if (principalPaid <= 0) {
      remaining += interestPaid - monthlyPayment
      cumulativeInterest += monthlyPayment
      schedule.push({
        month: m,
        balance: Math.round(remaining * 100) / 100,
        interestPaid: Math.round(interestPaid * 100) / 100,
        principalPaid: Math.round((monthlyPayment - interestPaid) * 100) / 100,
        totalInterest: Math.round(cumulativeInterest * 100) / 100,
        totalPrincipal: Math.round(cumulativePrincipal * 100) / 100,
      })
      continue
    }

    // Cap principal at remaining balance
    if (principalPaid > remaining) {
      principalPaid = remaining
    }

    remaining -= principalPaid
    cumulativeInterest += interestPaid
    cumulativePrincipal += principalPaid

    schedule.push({
      month: m,
      balance: Math.round(remaining * 100) / 100,
      interestPaid: Math.round(interestPaid * 100) / 100,
      principalPaid: Math.round(principalPaid * 100) / 100,
      totalInterest: Math.round(cumulativeInterest * 100) / 100,
      totalPrincipal: Math.round(cumulativePrincipal * 100) / 100,
    })

    if (remaining <= 0.01 && payoffMonths === null) {
      payoffMonths = m
      break
    }
  }

  return {
    payoffMonths,
    totalInterest: Math.round(cumulativeInterest * 100) / 100,
    totalPaid: Math.round((cumulativeInterest + cumulativePrincipal) * 100) / 100,
    schedule,
  }
}

/**
 * Calculate the minimum payment needed to pay off a debt in a given number
 * of months. Returns 0 if the balance is 0 or negative.
 */
export function calculateMinimumPaymentForTerm(
  balance: number,
  annualRate: number,
  months: number,
): number {
  if (balance <= 0 || months <= 0) return 0
  const monthlyRate = annualRate / 12
  if (monthlyRate === 0) return Math.round((balance / months) * 100) / 100

  const payment =
    (balance * monthlyRate * (1 + monthlyRate) ** months) /
    ((1 + monthlyRate) ** months - 1)
  return Math.round(payment * 100) / 100
}

/**
 * Calculate blended APR across multiple debts, weighted by balance.
 */
export function calculateBlendedAPR(
  debts: Array<{ balance: number; annualRate: number }>,
): number {
  const totalBalance = debts.reduce((sum, d) => sum + d.balance, 0)
  if (totalBalance <= 0) return 0

  const weightedSum = debts.reduce(
    (sum, d) => sum + d.balance * d.annualRate,
    0,
  )
  return Math.round((weightedSum / totalBalance) * 10000) / 10000
}
