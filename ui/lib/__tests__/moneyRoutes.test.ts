import { describe, expect, it } from 'vitest'
import { getLegacyMoneyRedirect, getMoneyView } from '@/lib/moneyRoutes'

describe('Money route compatibility', () => {
  it.each([
    ['/income', '/cash-flow', 'income'],
    ['/expenses', '/cash-flow', 'spending'],
    ['/activity', '/cash-flow', 'transactions'],
    ['/budgeting', '/plan', 'budget'],
  ])('maps %s to its one authoritative destination', (from, pathname, view) => {
    expect(getLegacyMoneyRedirect(from)).toEqual({ pathname, view })
  })

  it('preserves meaningful existing query state while adding the destination tab', () => {
    const params = new URLSearchParams('range=YTD&period=2026-08&search=rent')
    params.set('view', getLegacyMoneyRedirect('/budgeting')!.view)
    expect(params.toString()).toBe('range=YTD&period=2026-08&search=rent&view=budget')
  })

  it('uses a safe default for unknown or absent tab state', () => {
    expect(getMoneyView('cash-flow', null)).toBe('overview')
    expect(getMoneyView('cash-flow', 'unknown')).toBe('overview')
    expect(getMoneyView('plan', 'unknown')).toBe('budget')
  })
})
