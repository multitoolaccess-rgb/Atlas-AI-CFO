import { describe, expect, it } from 'vitest'
import { COMPATIBILITY_REDIRECTS, PROPOSED_NAVIGATION, SCOUT_PLACEMENT_CONTRACT, validateInformationArchitecture } from '@/lib/informationArchitecture'

describe('information architecture Step 1 contract', () => {
  it('defines the proposed grouped destinations without activating them', () => {
    expect(PROPOSED_NAVIGATION.map((group) => group.label)).toEqual(['Home', 'Money', 'Wealth', 'Intelligence', 'System'])
    expect(PROPOSED_NAVIGATION.flatMap((group) => group.destinations).every((destination) => !destination.activated)).toBe(true)
    expect(validateInformationArchitecture()).toEqual([])
  })

  it('maps every moved legacy route to a future destination without enabling redirects', () => {
    expect(COMPATIBILITY_REDIRECTS.map(({ from }) => from)).toEqual(['/income', '/expenses', '/activity', '/budgeting', '/debts', '/universe', '/recommendations', '/market-briefs', '/accounts'])
    expect(COMPATIBILITY_REDIRECTS.every(({ to }) => to.startsWith('/'))).toBe(true)
  })

  it('keeps Scout fallback accessible until its later header activation', () => {
    expect(SCOUT_PLACEMENT_CONTRACT.fallbackRoute).toBe('/assistant')
    expect(SCOUT_PLACEMENT_CONTRACT.activation).toContain('Step 4')
  })
})
