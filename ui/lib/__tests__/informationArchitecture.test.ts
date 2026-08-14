import { describe, expect, it } from 'vitest'
import { COMPATIBILITY_REDIRECTS, PROPOSED_NAVIGATION, SCOUT_PLACEMENT_CONTRACT, validateInformationArchitecture } from '@/lib/informationArchitecture'

describe('information architecture activation contract', () => {
  it('activates only the Step 2 home and Money destinations', () => {
    expect(PROPOSED_NAVIGATION.map((group) => group.label)).toEqual(['Home', 'Money', 'Wealth', 'Intelligence', 'System'])
    expect(PROPOSED_NAVIGATION.flatMap((group) => group.destinations).filter((destination) => destination.activated).map((destination) => destination.id)).toEqual(['mission-control', 'cash-flow', 'plan'])
    expect(validateInformationArchitecture()).toEqual([])
  })

  it('maps every legacy route to a documented destination', () => {
    expect(COMPATIBILITY_REDIRECTS.map(({ from }) => from)).toEqual(['/income', '/expenses', '/activity', '/budgeting', '/debts', '/universe', '/recommendations', '/market-briefs', '/accounts'])
    expect(COMPATIBILITY_REDIRECTS.every(({ to }) => to.startsWith('/'))).toBe(true)
  })

  it('keeps Scout fallback accessible after header activation', () => {
    expect(SCOUT_PLACEMENT_CONTRACT.fallbackRoute).toBe('/assistant')
    expect(SCOUT_PLACEMENT_CONTRACT.activation).toContain('Step 2')
  })
})
