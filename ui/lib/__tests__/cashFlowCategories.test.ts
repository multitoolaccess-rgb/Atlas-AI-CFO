import { describe, expect, it } from 'vitest'
import {
  classifyBreakdownBucket,
  isSpendingCashflowTransaction,
  matchesCashFlowCategory,
} from '../api'

describe('Cash Flow category contract', () => {
  it('maps categories to the same broad buckets as the backend', () => {
    expect(classifyBreakdownBucket('Groceries')).toBe('Essential')
    expect(classifyBreakdownBucket('Dining')).toBe('Flexible')
    expect(classifyBreakdownBucket('Credit Card Payments')).toBe('Debt')
    expect(classifyBreakdownBucket('Brokerage Buys')).toBe('Savings')
  })

  it('matches broad bucket drilldowns to real spending transactions', () => {
    expect(matchesCashFlowCategory({
      amount: -42,
      account_type: 'checking',
      description: 'Market',
      category_name: 'Groceries',
    }, 'Essential')).toBe(true)

    expect(matchesCashFlowCategory({
      amount: -100,
      account_type: 'checking',
      description: 'Online transfer',
      category_name: 'Groceries',
    }, 'Essential')).toBe(false)
  })

  it('keeps drilldowns useful when legacy rows omit account_type', () => {
    expect(matchesCashFlowCategory({
      amount: -42,
      description: 'Market',
      category_name: 'Groceries',
    }, 'Groceries')).toBe(true)
  })

  it('shares the spending effect contract with the dashboard', () => {
    expect(isSpendingCashflowTransaction({
      amount: -250,
      account_type: 'investment',
      description: 'BUY VTI',
    })).toBe(true)
    expect(isSpendingCashflowTransaction({
      amount: -250,
      account_type: 'savings',
      description: 'ATM cash',
    })).toBe(false)
  })
})
