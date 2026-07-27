/**
 * Pure-math projection engine for the CashFlix dashboard.
 *
 * Single source of truth for "how much will my portfolio be worth in N years?"
 * math. Deliberately framework-free (no React, no DOM, no IO) so the
 * `__tests__/projection.test.ts` suite runs in a single tick and the
 * `FinancialPlans` dashboard section can call it inline during render.
 *
 *   FV = PV * (1 + r)^n + PMT * (((1 + r)^n - 1) / r)
 *
 *   When r === 0 the formula collapses to:  FV = PV + PMT * n
 *
 *   When `inflationRate` is non-zero we use the Fisher-equation real rate:
 *     realRate = (1 + rate) / (1 + inflationRate) - 1
 *   so the returned value is *purchasing power today*, not nominal dollars.
 *
 * Inputs are validated and rejected with a TypeError if NaN / negative
 * horizon / rate outside (-1, 2). The function is referentially transparent
 * — same inputs always yield the same numeric output.
 */

export interface ProjectionInput {
  /** Present value — current net worth. May be 0 or negative (debt). */
  pv: number
  /** Periodic contribution (e.g. monthly savings). Can be 0. */
  pmt: number
  /** Annual nominal return rate as a decimal (0.07 = 7%). Range: (-1, 2). */
  rate: number
  /** Investment horizon in years. Must be >= 0. */
  years: number
  /** Annual inflation rate as a decimal. Default 0 (nominal). */
  inflationRate?: number
}

const RATE_MIN_EXCLUSIVE = -1
const RATE_MAX_INCLUSIVE = 2
const MAX_HORIZON_YEARS = 200

export function calculateFutureValue(input: ProjectionInput): number {
  const { pv, pmt, rate, years } = input
  const inflationRate = input.inflationRate ?? 0

  if (!Number.isFinite(pv) || !Number.isFinite(pmt)) {
    throw new TypeError(`calculateFutureValue: pv and pmt must be finite (got pv=${pv}, pmt=${pmt})`)
  }
  if (!Number.isFinite(rate) || !Number.isFinite(inflationRate)) {
    throw new TypeError(
      `calculateFutureValue: rate and inflationRate must be finite (got rate=${rate}, inflationRate=${inflationRate})`,
    )
  }
  if (rate <= RATE_MIN_EXCLUSIVE || rate > RATE_MAX_INCLUSIVE) {
    throw new RangeError(
      `calculateFutureValue: rate must be in (${RATE_MIN_EXCLUSIVE}, ${RATE_MAX_INCLUSIVE}] (got ${rate})`,
    )
  }
  if (inflationRate < -0.5 || inflationRate > 1) {
    throw new RangeError(
      `calculateFutureValue: inflationRate must be in [-0.5, 1] (got ${inflationRate})`,
    )
  }
  if (!Number.isFinite(years) || years < 0) {
    throw new RangeError(`calculateFutureValue: years must be >= 0 (got ${years})`)
  }
  if (years > MAX_HORIZON_YEARS) {
    throw new RangeError(
      `calculateFutureValue: years must be <= ${MAX_HORIZON_YEARS} (got ${years})`,
    )
  }

  // Fisher-equation real rate — collapses to `rate` when inflationRate === 0.
  const realRate =
    inflationRate === 0 ? rate : (1 + rate) / (1 + inflationRate) - 1

  if (years === 0) return pv

  if (realRate === 0) {
    // Degenerate case: no growth, just principal + sum of contributions.
    return pv + pmt * years
  }

  const growthFactor = (1 + realRate) ** years
  const fvPrincipal = pv * growthFactor
  // PMT term: standard annuity future-value. When pmt === 0, the whole
  // term collapses to 0 and the formula reduces to compound interest on PV.
  const fvContributions = pmt === 0 ? 0 : pmt * ((growthFactor - 1) / realRate)

  return fvPrincipal + fvContributions
}

/**
 * Convenience wrapper for the CashFlix dashboard: the spec'd inputs are
 * current net worth, monthly contribution, annual return rate, and years.
 * The caller passes `monthlyContribution` (not annual); we annualize.
 */
export interface DashboardProjectionInput {
  netWorth: number
  monthlyContribution: number
  annualReturnRate: number
  years: number
  annualInflationRate?: number
}

export function projectDashboardTrajectory(input: DashboardProjectionInput): number {
  return calculateFutureValue({
    pv: input.netWorth,
    pmt: input.monthlyContribution * 12,
    rate: input.annualReturnRate,
    years: input.years,
    inflationRate: input.annualInflationRate,
  })
}
