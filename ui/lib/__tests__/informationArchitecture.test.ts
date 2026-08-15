import { describe, expect, it } from 'vitest'
import { ACTIVE_COMPATIBILITY_REDIRECTS, COMPATIBILITY_REDIRECTS, PROPOSED_NAVIGATION, SCOUT_PLACEMENT_CONTRACT, validateInformationArchitecture } from '@/lib/informationArchitecture'

describe('information architecture activation contract', () => {
  it('activates Home, Money, and the complete Wealth wave', () => {
    expect(PROPOSED_NAVIGATION.map((group) => group.label)).toEqual(['Home', 'Money', 'Wealth', 'Intelligence', 'System'])
    expect(PROPOSED_NAVIGATION.flatMap((group) => group.destinations).filter((destination) => destination.activated).map((destination) => destination.id)).toEqual(['mission-control', 'cash-flow', 'plan', 'wealth', 'portfolio', 'goals', 'decisions', 'market-intelligence', 'scenario-lab'])
    expect(validateInformationArchitecture()).toEqual([])
  })

  it('maps every legacy route to a documented destination', () => {
    expect(COMPATIBILITY_REDIRECTS.map(({ from }) => from)).toEqual(['/income', '/expenses', '/activity', '/budgeting', '/debts', '/universe', '/recommendations', '/market-briefs', '/accounts'])
    expect(COMPATIBILITY_REDIRECTS.every(({ to }) => to.startsWith('/'))).toBe(true)
    expect(ACTIVE_COMPATIBILITY_REDIRECTS.map(({ from }) => from)).toEqual(['/income', '/expenses', '/activity', '/budgeting', '/debts', '/universe', '/recommendations', '/market-briefs'])
  })

  it('keeps Market Intelligence deep links aligned with the implemented tab state', () => {
    const market = PROPOSED_NAVIGATION.flatMap((group) => group.destinations).find((destination) => destination.id === 'market-intelligence')
    expect(market?.tabs?.map((tab) => tab.id)).toEqual(['portfolio', 'pulse', 'earnings', 'scanner', 'archive'])
    expect(market?.tabs?.find((tab) => tab.id === 'earnings')?.query).toEqual({ view: 'earnings' })
  })

  it('keeps Scout fallback accessible after header activation', () => {
    expect(SCOUT_PLACEMENT_CONTRACT.fallbackRoute).toBe('/assistant')
    expect(SCOUT_PLACEMENT_CONTRACT.activation).toContain('Step 2')
  })
})
