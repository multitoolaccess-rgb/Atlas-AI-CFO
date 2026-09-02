import { describe, expect, it, vi } from 'vitest'
import { investmentPersistence } from './investmentPersistence'

describe('investmentPersistence', () => {
  it('exposes the server-owned recommendation read contract', async () => {
    const get = vi.spyOn((investmentPersistence as never), 'getRecommendation')
    expect(typeof investmentPersistence.listRecommendations).toBe('function')
    expect(typeof investmentPersistence.getEvidence).toBe('function')
    expect(typeof investmentPersistence.recordDecision).toBe('function')
    get.mockRestore()
  })
})
