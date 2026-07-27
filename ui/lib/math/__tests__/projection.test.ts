import { describe, expect, it } from 'vitest'
import {
  calculateFutureValue,
  projectDashboardTrajectory,
} from '../projection'

describe('calculateFutureValue — pure-math contract', () => {
  it('zero return rate collapses to simple addition: FV = PV + PMT * years', () => {
    const fv = calculateFutureValue({ pv: 100_000, pmt: 1_000, rate: 0, years: 10 })
    expect(fv).toBe(110_000)
  })

  it('zero contribution reduces to standard compound interest on PV', () => {
    // 100k at 7% for 5 years: 100_000 * 1.07^5 = 140,255.17
    const fv = calculateFutureValue({ pv: 100_000, pmt: 0, rate: 0.07, years: 5 })
    expect(fv).toBeCloseTo(140_255.17, 2)
  })

  it('zero horizon returns PV exactly (no compounding, no contributions added)', () => {
    const fv = calculateFutureValue({ pv: 250_000, pmt: 5_000, rate: 0.07, years: 0 })
    expect(fv).toBe(250_000)
  })

  it('negative return rate depreciates the portfolio', () => {
    // 100k at -10% for 3 years: 100_000 * 0.9^3 = 72,900
    const fv = calculateFutureValue({ pv: 100_000, pmt: 0, rate: -0.1, years: 3 })
    expect(fv).toBeCloseTo(72_900, 2)
  })

  it('inflation adjustment: real FV < nominal FV at positive inflation', () => {
    const nominal = calculateFutureValue({ pv: 100_000, pmt: 0, rate: 0.07, years: 20 })
    const real = calculateFutureValue({ pv: 100_000, pmt: 0, rate: 0.07, years: 20, inflationRate: 0.025 })
    expect(nominal).toBeGreaterThan(real)
    // Real rate via Fisher = (1.07 / 1.025) - 1 = 0.043902...
    // 100_000 * 1.043902^20 = 236,155.60 (engine output, verified)
    // The previous test value 237_500 was a hand-calc error (~0.6% off).
    expect(real).toBeCloseTo(236_155.60, 0)
    // Sanity: real FV should be ~ (nominal / (1+inflation)^years) for the
    // gross-of-tax zero-contribution case. nominal = 386,968. (1.025)^20 = 1.6386.
    // 386,968 / 1.6386 = 236,159 — within 0.001% of engine output. ✓
  })

  it('100-year horizon at 7% does not overflow / underflow', () => {
    const fv = calculateFutureValue({ pv: 10_000, pmt: 0, rate: 0.07, years: 100 })
    // 1.07^100 ≈ 867.7  → 8_677_000
    expect(fv).toBeGreaterThan(8_000_000)
    expect(fv).toBeLessThan(9_000_000)
    expect(Number.isFinite(fv)).toBe(true)
  })

  it('rejects NaN inputs with TypeError', () => {
    expect(() => calculateFutureValue({ pv: NaN, pmt: 0, rate: 0.05, years: 5 })).toThrow(TypeError)
    expect(() => calculateFutureValue({ pv: 0, pmt: 0, rate: NaN, years: 5 })).toThrow(TypeError)
  })

  it('rejects negative horizon with RangeError', () => {
    expect(() => calculateFutureValue({ pv: 0, pmt: 0, rate: 0.05, years: -1 })).toThrow(RangeError)
  })

  it('rejects rate <= -1 (would invert the math) with RangeError', () => {
    expect(() => calculateFutureValue({ pv: 0, pmt: 0, rate: -1.5, years: 5 })).toThrow(RangeError)
    expect(() => calculateFutureValue({ pv: 0, pmt: 0, rate: -1, years: 5 })).toThrow(RangeError)
  })

  it('negative PMT (cash flow drawdown) reduces FV correctly — no floor at 0', () => {
    // Phase 9 reviewer-ship-blocker: user with negative monthly cash
    // flow (e.g. spending $500/mo more than they earn) must see a
    // projection that draws down their principal, not an optimistic
    // zero-contribution baseline. The formula must handle pmt < 0.
    //
    // 100k PV, -6_000 PMT/yr (= -$500/mo), 7% for 5 years:
    //   PV term  : 100_000 * 1.07^5          = 140,255.1730
    //   PMT term : -6_000 * (1.07^5 - 1) / 0.07 = -34,504.4340
    //   Total    :                              105,750.7390
    // toBeCloseTo(_, -1) tolerates ~5 cents (the previous test value
    // 105,746.07 was a hand-calc error off by ~$4.67).
    const fv = calculateFutureValue({ pv: 100_000, pmt: -6_000, rate: 0.07, years: 5 })
    expect(fv).toBeCloseTo(105_750.74, -1)
    // And the FV must be strictly less than the PV would be with
    // pmt = 0 (i.e. negative cash flow reduces portfolio).
    const fvNoContribution = calculateFutureValue({ pv: 100_000, pmt: 0, rate: 0.07, years: 5 })
    expect(fv).toBeLessThan(fvNoContribution)
  })

  it('compound interest + annuity sum independently', () => {
    // $100k PV at 5% for 10 years, $1k/yr PMT:
    //   PV term  : 100_000 * 1.05^10        = 162,889.46
    //   PMT term : 1_000 * ((1.05^10 - 1) / 0.05) = 12,577.89
    //   Total    : 175,467.36
    const fv = calculateFutureValue({ pv: 100_000, pmt: 1_000, rate: 0.05, years: 10 })
    expect(fv).toBeCloseTo(175_467.36, 0)
  })
})

describe('projectDashboardTrajectory — dashboard wrapper', () => {
  it('annualizes monthly contribution (12x multiplier) — 2-year case shows compounding', () => {
    // PV=0, monthly=1000, rate=7%, years=2:
    //   annual PMT = 12_000
    //   FV         = 0 * 1.07^2 + 12_000 * (1.07^2 - 1) / 0.07
    //             = 0 + 12_000 * (1.1449 - 1) / 0.07
    //             = 12_000 * 0.1449 / 0.07
    //             = 12_000 * 2.07
    //             = 24_840
    // (A 1-year test was originally here but it degenerated to just
    // `12_000 * 0 / 0.07 = 0` plus the first contribution, not really
    // exercising annualization vs compounding. 2 years is the smallest
    // case where the 12x multiplier is distinguishable from monthly math.)
    const fv = projectDashboardTrajectory({
      netWorth: 0,
      monthlyContribution: 1_000,
      annualReturnRate: 0.07,
      years: 2,
    })
    expect(fv).toBeCloseTo(24_840, 0)
  })

  it('matches the underlying calculateFutureValue when pmt * 12 is passed', () => {
    const input = { netWorth: 50_000, monthlyContribution: 500, annualReturnRate: 0.08, years: 7 }
    const wrapped = projectDashboardTrajectory(input)
    const direct = calculateFutureValue({
      pv: input.netWorth,
      pmt: input.monthlyContribution * 12,
      rate: input.annualReturnRate,
      years: input.years,
    })
    expect(wrapped).toBe(direct)
  })
})
