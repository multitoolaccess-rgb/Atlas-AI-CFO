import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: mockGet }, default: { get: mockGet } }))

import { getDecisionHistory, readDecisionHistoryError } from '@/lib/api_phase4'

describe('api_phase4', () => {
  beforeEach(() => mockGet.mockReset())

  it('reads the typed, safe decision-history envelope from the goal endpoint', async () => {
    mockGet.mockResolvedValue({ data: { schema_version: 'atlas-decision-history-envelope/v1', history: [] } })
    await expect(getDecisionHistory(42)).resolves.toEqual({ schema_version: 'atlas-decision-history-envelope/v1', history: [] })
    expect(mockGet).toHaveBeenCalledWith('/api/v1/goals/42/decision-history')
  })

  it('maps only bounded decision-history error codes', () => {
    expect(readDecisionHistoryError({ isAxiosError: true, response: { data: { code: 'decision_history_unavailable', message: 'not rendered' } } })).toBe('unavailable')
    expect(readDecisionHistoryError({ isAxiosError: true, response: { data: { code: 'unexpected_internal_code' } } })).toBe('error')
  })
})
