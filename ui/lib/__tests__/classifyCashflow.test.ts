/**
 * Unit tests for classifyCashflow() — covers all 13 account types per spec.
 *
 * Each test block validates:
 *  - effect (granular FinancialEffect)
 *  - role (high-level CashflowRole)
 *  - incomeEffect / expenseEffect / transferEffect (numerical effects)
 */

import { describe, it, expect } from 'vitest'
import { classifyCashflow, type CashflowClassification } from '../api'

// Helper to create a transaction input for classifyCashflow
function txn(amount: number, account_type: string, description: string) {
  return classifyCashflow({ amount, account_type, description })
}

// Helper: assert effect + role in one call
function expectEffect(
  result: CashflowClassification,
  effect: string,
  role: string,
) {
  expect(result.effect).toBe(effect)
  expect(result.role).toBe(role)
}

// Helper: assert numerical effects
function expectNumerical(
  result: CashflowClassification,
  income: number,
  expense: number,
  transfer: number,
) {
  expect(result.incomeEffect).toBe(income)
  expect(result.expenseEffect).toBe(expense)
  expect(result.transferEffect).toBe(transfer)
}

// ============================================================================
// CHECKING
// ============================================================================
describe('checking', () => {
  it('payroll deposit → income', () => {
    const r = txn(5000, 'checking', 'ACME PAYROLL DIRECT DEPOSIT')
    expectEffect(r, 'income', 'earn')
    expectNumerical(r, 5000, 0, 0)
  })

  it('salary deposit → income', () => {
    const r = txn(3500, 'checking', 'SALARY DEPOSIT')
    expectEffect(r, 'income', 'earn')
    expectNumerical(r, 3500, 0, 0)
  })

  it('interest earned → interest (income)', () => {
    const r = txn(2.50, 'checking', 'INTEREST PAID')
    expectEffect(r, 'interest', 'earn')
    expectNumerical(r, 2.50, 0, 0)
  })

  it('bank fee → fee', () => {
    const r = txn(-12, 'checking', 'MONTHLY SERVICE FEE')
    expectEffect(r, 'fee', 'spend')
    expectNumerical(r, 0, 12, 0)
  })

  it('internal transfer → transfer', () => {
    const r = txn(1000, 'checking', 'ONLINE TRANSFER FROM SAVINGS')
    expectEffect(r, 'transfer', 'transfer')
    expectNumerical(r, 0, 0, 1000)
  })

  it('refund → expense_reversal', () => {
    const r = txn(25, 'checking', 'REFUND FROM AMAZON')
    expectEffect(r, 'expense_reversal', 'earn')
    expectNumerical(r, 0, -25, 0)
  })

  it('generic negative → expense', () => {
    const r = txn(-45.99, 'checking', 'UBER EATS')
    expectEffect(r, 'expense', 'spend')
    expectNumerical(r, 0, 45.99, 0)
  })

  it('generic positive → income fallback', () => {
    const r = txn(100, 'checking', 'VENMO FROM FRIEND')
    expectEffect(r, 'income', 'earn')
    expectNumerical(r, 100, 0, 0)
  })

  it('bill pay → expense (money leaving checking)', () => {
    const r = txn(-500, 'checking', 'BILL PAY TO CHASE CARD')
    expectEffect(r, 'expense', 'spend')
    expectNumerical(r, 0, 500, 0)
  })

  it('ACH debit mortgage payment → expense', () => {
    const r = txn(-250, 'checking', 'ACH DEBIT MORTGAGE PMT')
    expectEffect(r, 'expense', 'spend')
    expectNumerical(r, 0, 250, 0)
  })
})

// ============================================================================
// SAVINGS
// ============================================================================
describe('savings', () => {
  it('interest earned → interest (income)', () => {
    const r = txn(15.00, 'savings', 'INTEREST EARNED')
    expectEffect(r, 'interest', 'earn')
    expectNumerical(r, 15, 0, 0)
  })

  it('transfer → transfer', () => {
    const r = txn(-500, 'savings', 'ONLINE TRANSFER TO CHECKING')
    expectEffect(r, 'transfer', 'transfer')
    expectNumerical(r, 0, 0, 500)
  })

  it('fee → fee', () => {
    const r = txn(-5, 'savings', 'MONTHLY MAINTENANCE FEE')
    expectEffect(r, 'fee', 'spend')
    expectNumerical(r, 0, 5, 0)
  })

  it('merchant-like debit → needs_review', () => {
    const r = txn(-100, 'savings', 'AMAZON PURCHASE')
    expectEffect(r, 'needs_review', 'transfer')
    expect(r.needsReview).toBe(true)
    expect(r.reviewReason).toBeTruthy()
  })

  it('positive deposit → transfer (not income)', () => {
    const r = txn(500, 'savings', 'DEPOSIT FROM CHECKING')
    expectEffect(r, 'transfer', 'transfer')
    expectNumerical(r, 0, 0, 500)
  })
})

// ============================================================================
// CREDIT CARD
// ============================================================================
describe('credit_card', () => {
  it('online payment → transfer (not income!)', () => {
    const r = txn(-450, 'credit_card', 'ONLINE PAYMENT, THANK YOU')
    expectEffect(r, 'transfer', 'transfer')
    expectNumerical(r, 0, 0, 450)
  })

  it('autopay → transfer', () => {
    const r = txn(-1200, 'credit_card', 'AUTOPAY PAYMENT')
    expectEffect(r, 'transfer', 'transfer')
    expectNumerical(r, 0, 0, 1200)
  })

  it('refund → expense_reversal', () => {
    const r = txn(-25, 'credit_card', 'REFUND FROM TARGET')
    expectEffect(r, 'expense_reversal', 'earn')
    expectNumerical(r, 0, -25, 0)
  })

  it('cashback → expense_reversal', () => {
    const r = txn(-10, 'credit_card', 'CASHBACK REWARD')
    expectEffect(r, 'expense_reversal', 'earn')
    expectNumerical(r, 0, -10, 0)
  })

  it('late fee → fee', () => {
    const r = txn(39, 'credit_card', 'LATE FEE')
    expectEffect(r, 'fee', 'spend')
    expectNumerical(r, 0, 39, 0)
  })

  it('interest charge → fee (expense)', () => {
    const r = txn(22.50, 'credit_card', 'INTEREST CHARGE')
    expectEffect(r, 'fee', 'spend')
    expectNumerical(r, 0, 22.50, 0)
  })

  it('merchant purchase → expense', () => {
    const r = txn(-65.99, 'credit_card', 'BURRITOS CALIFORNIA')
    expectEffect(r, 'expense', 'spend')
    expectNumerical(r, 0, 65.99, 0)
  })

  it('positive charge → expense (banks may report positive)', () => {
    const r = txn(65.99, 'credit_card', 'BURRITOS CALIFORNIA')
    expectEffect(r, 'expense', 'spend')
    expectNumerical(r, 0, 65.99, 0)
  })
})

// ============================================================================
// DEBIT CARD
// ============================================================================
describe('debit_card', () => {
  it('merchant purchase → expense', () => {
    const r = txn(-42.50, 'debit_card', 'STARBUCKS')
    expectEffect(r, 'expense', 'spend')
    expectNumerical(r, 0, 42.50, 0)
  })

  it('refund → expense_reversal', () => {
    const r = txn(42.50, 'debit_card', 'REFUND STARBUCKS')
    expectEffect(r, 'expense_reversal', 'earn')
    expectNumerical(r, 0, -42.50, 0)
  })

  it('deposit/income → income', () => {
    const r = txn(2000, 'debit_card', 'DIRECT DEPOSIT PAYROLL')
    expectEffect(r, 'income', 'earn')
    expectNumerical(r, 2000, 0, 0)
  })

  it('transfer → transfer', () => {
    const r = txn(-500, 'debit_card', 'ONLINE TRANSFER TO SAVINGS')
    expectEffect(r, 'transfer', 'transfer')
    expectNumerical(r, 0, 0, 500)
  })

  it('fee → fee', () => {
    const r = txn(-3, 'debit_card', 'ATM FEE')
    expectEffect(r, 'fee', 'spend')
    expectNumerical(r, 0, 3, 0)
  })

  it('overdraft fee → fee', () => {
    const r = txn(-35, 'debit_card', 'OVERDRAFT FEE')
    expectEffect(r, 'fee', 'spend')
    expectNumerical(r, 0, 35, 0)
  })

  it('ATM withdrawal → expense (no cash ledger)', () => {
    const r = txn(-100, 'debit_card', 'ATM WITHDRAWAL')
    expectEffect(r, 'expense', 'spend')
    expectNumerical(r, 0, 100, 0)
  })
})

// ============================================================================
// INVESTMENT
// ============================================================================
describe('investment', () => {
  it('buy → investment_buy', () => {
    const r = txn(-10000, 'investment', 'YOU BOUGHT VTI')
    expectEffect(r, 'investment_buy', 'invest')
    expectNumerical(r, 0, 0, 10000)
  })

  it('sell → investment_sell', () => {
    const r = txn(15000, 'investment', 'YOU SOLD AAPL')
    expectEffect(r, 'investment_sell', 'invest')
    expectNumerical(r, 0, 0, 15000)
  })

  it('dividend → income', () => {
    const r = txn(250, 'investment', 'DIVIDEND VTI')
    expectEffect(r, 'income', 'earn')
    expectNumerical(r, 250, 0, 0)
  })

  it('fee → fee', () => {
    const r = txn(-9.99, 'investment', 'TRANSACTION FEE')
    expectEffect(r, 'fee', 'spend')
    expectNumerical(r, 0, 9.99, 0)
  })

  it('funding transfer → transfer', () => {
    const r = txn(5000, 'investment', 'FUNDS RECEIVED')
    expectEffect(r, 'transfer', 'transfer')
    expectNumerical(r, 0, 0, 5000)
  })

  it('interest earned → income', () => {
    const r = txn(75, 'investment', 'INTEREST PAID')
    expectEffect(r, 'income', 'earn')
    expectNumerical(r, 75, 0, 0)
  })
})

// ============================================================================
// LOAN
// ============================================================================
describe('loan', () => {
  it('principal payment → principal_payment', () => {
    const r = txn(-350, 'loan', 'PRINCIPAL PAYMENT')
    expectEffect(r, 'principal_payment', 'debt')
    expectNumerical(r, 0, 0, 350)
  })

  it('interest/fee → fee', () => {
    const r = txn(-50, 'loan', 'INTEREST PAID')
    expectEffect(r, 'fee', 'spend')
    expectNumerical(r, 0, 50, 0)
  })

  it('payment → transfer', () => {
    const r = txn(-400, 'loan', 'ONLINE PAYMENT')
    expectEffect(r, 'transfer', 'transfer')
    expectNumerical(r, 0, 0, 400)
  })

  it('disbursement → transfer', () => {
    const r = txn(10000, 'loan', 'LOAN DISBURSEMENT')
    expectEffect(r, 'transfer', 'transfer')
    expectNumerical(r, 0, 0, 10000)
  })
})

// ============================================================================
// MORTGAGE
// ============================================================================
describe('mortgage', () => {
  it('escrow → transfer', () => {
    const r = txn(-200, 'mortgage', 'ESCROW PAYMENT')
    expectEffect(r, 'transfer', 'save')
    expectNumerical(r, 0, 0, 200)
  })

  it('principal → principal_payment', () => {
    const r = txn(-500, 'mortgage', 'PRINCIPAL PAYMENT')
    expectEffect(r, 'principal_payment', 'debt')
    expectNumerical(r, 0, 0, 500)
  })

  it('interest → fee', () => {
    const r = txn(-300, 'mortgage', 'INTEREST PAID')
    expectEffect(r, 'fee', 'spend')
    expectNumerical(r, 0, 300, 0)
  })

  it('property tax → escrow/transfer', () => {
    const r = txn(-150, 'mortgage', 'PROPERTY TAX')
    expectEffect(r, 'transfer', 'save')
    expectNumerical(r, 0, 0, 150)
  })
})

// ============================================================================
// 401(k)
// ============================================================================
describe('401k', () => {
  it('contribution → contribution', () => {
    const r = txn(1000, '401k', 'EMPLOYEE CONTRIBUTION')
    expectEffect(r, 'contribution', 'save')
    expectNumerical(r, 0, 0, 1000)
  })

  it('employer match → contribution', () => {
    const r = txn(500, '401k', 'EMPLOYER MATCH')
    expectEffect(r, 'contribution', 'save')
    expectNumerical(r, 0, 0, 500)
  })

  it('rollover → transfer', () => {
    const r = txn(50000, '401k', 'ROLLOVER FROM PREVIOUS EMPLOYER')
    expectEffect(r, 'transfer', 'transfer')
    expectNumerical(r, 0, 0, 50000)
  })

  it('trade buy → investment_buy', () => {
    const r = txn(-5000, '401k', 'BUY VANGUARD 500')
    expectEffect(r, 'investment_buy', 'invest')
    expectNumerical(r, 0, 0, 5000)
  })

  it('dividend → income', () => {
    const r = txn(75, '401k', 'DIVIDEND REINVEST')
    expectEffect(r, 'income', 'earn')
    expectNumerical(r, 75, 0, 0)
  })

  it('trade sell → investment_sell', () => {
    const r = txn(8000, '401k', 'SELL VANGUARD 500')
    expectEffect(r, 'investment_sell', 'invest')
    expectNumerical(r, 0, 0, 8000)
  })

  it('fee → fee', () => {
    const r = txn(-25, '401k', 'ADMINISTRATIVE FEE')
    expectEffect(r, 'fee', 'spend')
    expectNumerical(r, 0, 25, 0)
  })
})

// ============================================================================
// IRA
// ============================================================================
describe('ira', () => {
  it('contribution → contribution', () => {
    const r = txn(6500, 'ira', 'IRA CONTRIBUTION')
    expectEffect(r, 'contribution', 'save')
    expectNumerical(r, 0, 0, 6500)
  })

  it('rollover → transfer', () => {
    const r = txn(100000, 'ira', 'ROLLOVER IRA')
    expectEffect(r, 'transfer', 'transfer')
    expectNumerical(r, 0, 0, 100000)
  })

  it('withdrawal/distribution → withdrawal', () => {
    const r = txn(10000, 'ira', 'IRA DISTRIBUTION')
    expectEffect(r, 'withdrawal', 'transfer')
    expectNumerical(r, 0, 0, 10000)
  })

  it('trade → investment_buy', () => {
    const r = txn(-3000, 'ira', 'BUY SCHD')
    expectEffect(r, 'investment_buy', 'invest')
    expectNumerical(r, 0, 0, 3000)
  })

  it('dividend → income', () => {
    const r = txn(120, 'ira', 'DIVIDEND PAID')
    expectEffect(r, 'income', 'earn')
    expectNumerical(r, 120, 0, 0)
  })

  it('trade sell → investment_sell', () => {
    const r = txn(7000, 'ira', 'SELL SCHD')
    expectEffect(r, 'investment_sell', 'invest')
    expectNumerical(r, 0, 0, 7000)
  })

  it('fee → fee', () => {
    const r = txn(-15, 'ira', 'CUSTODIAL FEE')
    expectEffect(r, 'fee', 'spend')
    expectNumerical(r, 0, 15, 0)
  })
})

// ============================================================================
// HSA
// ============================================================================
describe('hsa', () => {
  it('contribution → contribution', () => {
    const r = txn(300, 'hsa', 'HSA CONTRIBUTION')
    expectEffect(r, 'contribution', 'save')
    expectNumerical(r, 0, 0, 300)
  })

  it('employer contribution → contribution', () => {
    const r = txn(150, 'hsa', 'EMPLOYER CONTRIBUTION')
    expectEffect(r, 'contribution', 'save')
    expectNumerical(r, 0, 0, 150)
  })

  it('medical payment → expense', () => {
    const r = txn(-75, 'hsa', 'CVS PHARMACY')
    expectEffect(r, 'expense', 'spend')
    expectNumerical(r, 0, 75, 0)
  })

  it('investment buy → investment_buy', () => {
    const r = txn(-1000, 'hsa', 'BUY VTI')
    expectEffect(r, 'investment_buy', 'invest')
    expectNumerical(r, 0, 0, 1000)
  })

  it('interest → income', () => {
    const r = txn(5, 'hsa', 'INTEREST EARNED')
    expectEffect(r, 'income', 'earn')
    expectNumerical(r, 5, 0, 0)
  })

  it('trade sell → investment_sell', () => {
    const r = txn(2000, 'hsa', 'SELL VTI')
    expectEffect(r, 'investment_sell', 'invest')
    expectNumerical(r, 0, 0, 2000)
  })

  it('fee → fee', () => {
    const r = txn(-3, 'hsa', 'MONTHLY MAINTENANCE FEE')
    expectEffect(r, 'fee', 'spend')
    expectNumerical(r, 0, 3, 0)
  })
})

// ============================================================================
// 529
// ============================================================================
describe('529', () => {
  it('contribution → contribution', () => {
    const r = txn(1000, '529', '529 CONTRIBUTION')
    expectEffect(r, 'contribution', 'save')
    expectNumerical(r, 0, 0, 1000)
  })

  it('qualified withdrawal → withdrawal', () => {
    const r = txn(5000, '529', '529 WITHDRAWAL')
    expectEffect(r, 'withdrawal', 'transfer')
    expectNumerical(r, 0, 0, 5000)
  })

  it('investment → investment_buy', () => {
    const r = txn(-2000, '529', 'BUY AGE-BASED PORTFOLIO')
    expectEffect(r, 'investment_buy', 'invest')
    expectNumerical(r, 0, 0, 2000)
  })

  it('fee → fee', () => {
    const r = txn(-10, '529', 'ANNUAL FEE')
    expectEffect(r, 'fee', 'spend')
    expectNumerical(r, 0, 10, 0)
  })

  it('trade sell → investment_sell', () => {
    const r = txn(4000, '529', 'SELL AGE-BASED PORTFOLIO')
    expectEffect(r, 'investment_sell', 'invest')
    expectNumerical(r, 0, 0, 4000)
  })
})

// ============================================================================
// CRYPTO
// ============================================================================
describe('crypto', () => {
  it('buy → investment_buy', () => {
    const r = txn(-5000, 'crypto', 'BUY BTC')
    expectEffect(r, 'investment_buy', 'invest')
    expectNumerical(r, 0, 0, 5000)
  })

  it('sell → investment_sell', () => {
    const r = txn(8000, 'crypto', 'SELL ETH')
    expectEffect(r, 'investment_sell', 'invest')
    expectNumerical(r, 0, 0, 8000)
  })

  it('staking reward → income', () => {
    const r = txn(50, 'crypto', 'STAKING REWARD')
    expectEffect(r, 'income', 'earn')
    expectNumerical(r, 50, 0, 0)
  })

  it('airdrop → income', () => {
    const r = txn(100, 'crypto', 'AIRDROP CLAIM')
    expectEffect(r, 'income', 'earn')
    expectNumerical(r, 100, 0, 0)
  })

  it('network fee → fee', () => {
    const r = txn(-2.50, 'crypto', 'NETWORK FEE')
    expectEffect(r, 'fee', 'spend')
    expectNumerical(r, 0, 2.50, 0)
  })

  it('wallet transfer → transfer', () => {
    const r = txn(1000, 'crypto', 'TRANSFER FROM WALLET')
    expectEffect(r, 'transfer', 'transfer')
    expectNumerical(r, 0, 0, 1000)
  })
})

// ============================================================================
// OTHER
// ============================================================================
describe('other', () => {
  it('unknown type → needs_review', () => {
    const r = txn(500, 'other', 'SOME TRANSACTION')
    expectEffect(r, 'needs_review', 'transfer')
    expect(r.needsReview).toBe(true)
    expect(r.reviewReason).toBeTruthy()
  })
})

// ============================================================================
// FALLBACK / UNRECOGNIZED
// ============================================================================
describe('unrecognized account type', () => {
  it('empty string → needs_review', () => {
    const r = txn(100, '', 'TEST')
    expectEffect(r, 'needs_review', 'transfer')
    expect(r.needsReview).toBe(true)
  })

  it('null → needs_review', () => {
    const r = classifyCashflow({ amount: 100, account_type: null, description: 'TEST' })
    expectEffect(r, 'needs_review', 'transfer')
    expect(r.needsReview).toBe(true)
  })

  it('undefined → needs_review', () => {
    const r = classifyCashflow({ amount: 100, account_type: undefined, description: 'TEST' })
    expectEffect(r, 'needs_review', 'transfer')
    expect(r.needsReview).toBe(true)
  })
})

// ============================================================================
// BACKWARD COMPATIBILITY — bucket field
// ============================================================================
describe('backward compat — bucket field', () => {
  it('income effect → bucket income', () => {
    const r = txn(5000, 'checking', 'PAYROLL')
    expect(r.bucket).toBe('income')
  })

  it('expense effect → bucket expense', () => {
    const r = txn(-65, 'credit_card', 'BURRITOS')
    expect(r.bucket).toBe('expense')
  })

  it('transfer effect → bucket transfer', () => {
    const r = txn(-450, 'credit_card', 'ONLINE PAYMENT, THANK YOU')
    expect(r.bucket).toBe('transfer')
  })

  it('expense_reversal → bucket reversal', () => {
    const r = txn(-25, 'credit_card', 'REFUND AMAZON')
    expect(r.bucket).toBe('reversal')
  })
})

// ============================================================================
// WORD-BOUNDARY SAFETY (no false matches)
// ============================================================================
describe('word-boundary safety', () => {
  it('"REPAYMENT" is not a payment', () => {
    const r = txn(-500, 'credit_card', 'REPAYMENT PLAN')
    expectEffect(r, 'expense', 'spend') // falls through to default expense, NOT transfer
  })

  it('"NONREFUNDABLE" is not a refund', () => {
    const r = txn(-100, 'credit_card', 'NONREFUNDABLE DEPOSIT')
    expectEffect(r, 'expense', 'spend') // falls through to default expense
  })

  it('"PREPAYMENT" is not a payment on credit_card', () => {
    const r = txn(-50, 'credit_card', 'PREPAYMENT FOR SERVICES')
    expectEffect(r, 'expense', 'spend') // NOT transfer
  })
})
