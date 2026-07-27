/**
 * Tests for ui/lib/amortization.ts — pure-math debt payoff projections.
 *
 * All tests are referentially transparent (no IO, no mocks, no DOM).
 */

import { describe, it, expect } from 'vitest'
import {
  calculateAmortization,
  calculateMinimumPaymentForTerm,
  calculateBlendedAPR,
} from '@/lib/amortization'

describe('calculateAmortization', () => {
  it('returns empty schedule for zero balance', () => {
    const result = calculateAmortization({
      balance: 0,
      annualRate: 0.05,
      monthlyPayment: 100,
    })
    expect(result.payoffMonths).toBe(0)
    expect(result.schedule).toEqual([])
    expect(result.totalInterest).toBe(0)
  })

  it('returns empty schedule for zero payment', () => {
    const result = calculateAmortization({
      balance: 1000,
      annualRate: 0.05,
      monthlyPayment: 0,
    })
    expect(result.payoffMonths).toBe(0)
    expect(result.schedule).toEqual([])
  })

  it('pays off a simple loan correctly', () => {
    // $10,000 at 6% APR, $500/mo payment
    const result = calculateAmortization({
      balance: 10000,
      annualRate: 0.06,
      monthlyPayment: 500,
      months: 60,
    })

    expect(result.payoffMonths).not.toBeNull()
    expect(result.payoffMonths!).toBeLessThanOrEqual(24) // Should pay off in ~22 months
    expect(result.totalInterest).toBeGreaterThan(0)
    expect(result.totalPaid).toBeGreaterThan(10000) // Paid more than principal
    expect(result.schedule.length).toBeGreaterThan(0)
    expect(result.schedule[result.schedule.length - 1].balance).toBeLessThanOrEqual(0.01)
  })

  it('schedule has correct structure', () => {
    const result = calculateAmortization({
      balance: 5000,
      annualRate: 0.12,
      monthlyPayment: 500,
      months: 24,
    })

    const first = result.schedule[0]
    expect(first.month).toBe(1)
    expect(typeof first.balance).toBe('number')
    expect(typeof first.interestPaid).toBe('number')
    expect(typeof first.principalPaid).toBe('number')
    expect(typeof first.totalInterest).toBe('number')
    expect(typeof first.totalPrincipal).toBe('number')

    // First month interest: 5000 * (0.12/12) = 50
    expect(first.interestPaid).toBe(50)
    // First month principal: 500 - 50 = 450
    expect(first.principalPaid).toBe(450)
    // Remaining: 5000 - 450 = 4550
    expect(first.balance).toBe(4550)
  })

  it('balance decreases monotonically for standard loans', () => {
    const result = calculateAmortization({
      balance: 20000,
      annualRate: 0.08,
      monthlyPayment: 1000,
      months: 60,
    })

    for (let i = 1; i < result.schedule.length; i++) {
      expect(result.schedule[i].balance).toBeLessThanOrEqual(
        result.schedule[i - 1].balance,
      )
    }
  })

  it('handles negative amortization (payment < interest)', () => {
    // $100,000 at 24% APR, $100/mo payment — doesn't cover interest
    const result = calculateAmortization({
      balance: 100000,
      annualRate: 0.24,
      monthlyPayment: 100,
      months: 12,
    })

    expect(result.payoffMonths).toBeNull()
    // Balance should be increasing
    expect(result.schedule.length).toBe(12)
    expect(result.schedule[0].balance).toBeGreaterThan(100000)
  })

  it('cumulative totals increase over time', () => {
    const result = calculateAmortization({
      balance: 10000,
      annualRate: 0.06,
      monthlyPayment: 500,
      months: 60,
    })

    for (let i = 1; i < result.schedule.length; i++) {
      expect(result.schedule[i].totalInterest).toBeGreaterThanOrEqual(
        result.schedule[i - 1].totalInterest,
      )
      expect(result.schedule[i].totalPrincipal).toBeGreaterThanOrEqual(
        result.schedule[i - 1].totalPrincipal,
      )
    }
  })

  it('uses default 120 months when not specified', () => {
    const result = calculateAmortization({
      balance: 500,
      annualRate: 0.0,
      monthlyPayment: 100,
    })
    // At 0% interest, $500 / $100 = 5 months
    expect(result.payoffMonths).toBe(5)
    expect(result.totalInterest).toBe(0)
  })

  it('handles zero interest rate', () => {
    const result = calculateAmortization({
      balance: 1200,
      annualRate: 0,
      monthlyPayment: 100,
      months: 24,
    })

    expect(result.payoffMonths).toBe(12)
    expect(result.totalInterest).toBe(0)
    expect(result.totalPaid).toBe(1200)
  })
})

describe('calculateMinimumPaymentForTerm', () => {
  it('returns 0 for zero balance', () => {
    expect(calculateMinimumPaymentForTerm(0, 0.05, 12)).toBe(0)
  })

  it('returns 0 for negative balance', () => {
    expect(calculateMinimumPaymentForTerm(-100, 0.05, 12)).toBe(0)
  })

  it('returns 0 for zero months', () => {
    expect(calculateMinimumPaymentForTerm(1000, 0.05, 0)).toBe(0)
  })

  it('calculates simple division for zero rate', () => {
    const result = calculateMinimumPaymentForTerm(1200, 0, 12)
    expect(result).toBe(100)
  })

  it('calculates correct payment for non-zero rate', () => {
    // Standard mortgage-style calculation
    const result = calculateMinimumPaymentForTerm(200000, 0.06, 360)
    // Should be around $1,199/mo for a 30-year $200k at 6%
    expect(result).toBeGreaterThan(1100)
    expect(result).toBeLessThan(1300)
  })

  it('higher rate means higher payment for same balance/term', () => {
    const low = calculateMinimumPaymentForTerm(10000, 0.03, 60)
    const high = calculateMinimumPaymentForTerm(10000, 0.12, 60)
    expect(high).toBeGreaterThan(low)
  })

  it('shorter term means higher payment for same balance/rate', () => {
    const short = calculateMinimumPaymentForTerm(10000, 0.06, 12)
    const long = calculateMinimumPaymentForTerm(10000, 0.06, 60)
    expect(short).toBeGreaterThan(long)
  })
})

describe('calculateBlendedAPR', () => {
  it('returns 0 for empty debts', () => {
    expect(calculateBlendedAPR([])).toBe(0)
  })

  it('returns 0 for zero total balance', () => {
    expect(calculateBlendedAPR([{ balance: 0, annualRate: 0.05 }])).toBe(0)
  })

  it('returns single rate for single debt', () => {
    const result = calculateBlendedAPR([{ balance: 5000, annualRate: 0.15 }])
    expect(result).toBe(0.15)
  })

  it('weights by balance correctly', () => {
    // $3k at 20% + $7k at 10% = blended (600+700)/10000 = 13%
    const result = calculateBlendedAPR([
      { balance: 3000, annualRate: 0.20 },
      { balance: 7000, annualRate: 0.10 },
    ])
    expect(result).toBe(0.13)
  })

  it('is symmetric (order does not matter)', () => {
    const a = calculateBlendedAPR([
      { balance: 1000, annualRate: 0.20 },
      { balance: 2000, annualRate: 0.10 },
    ])
    const b = calculateBlendedAPR([
      { balance: 2000, annualRate: 0.10 },
      { balance: 1000, annualRate: 0.20 },
    ])
    expect(a).toBe(b)
  })

  it('handles multiple debts', () => {
    const result = calculateBlendedAPR([
      { balance: 1000, annualRate: 0.25 },
      { balance: 2000, annualRate: 0.15 },
      { balance: 3000, annualRate: 0.05 },
    ])
    // (1000*0.25 + 2000*0.15 + 3000*0.05) / 6000 = (250+300+150)/6000 = 0.1167
    expect(result).toBeCloseTo(0.1167, 3)
  })
})
