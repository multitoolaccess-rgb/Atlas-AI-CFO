import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ default: { get, post } }))

import {
  archiveScenario,
  compareScenarios,
  generateScenario,
  listScenarios,
  readScenario,
  readScenarioError,
} from '@/lib/api_scenarios'

describe('Scenario Lab API client', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
  })

  it('lists goal-scoped scenarios with the archive filter', async () => {
    const envelope = { schema_version: 'atlas-scenario-list/v1', items: [], next_cursor: null }
    get.mockResolvedValue({ data: envelope })

    await expect(listScenarios(42, true)).resolves.toEqual(envelope)
    expect(get).toHaveBeenCalledWith('/api/v1/goals/42/scenarios', { params: { include_archived: true } })
  })

  it('preserves the bounded request body and idempotency header', async () => {
    const response = { data: { scenario_id: 'scenario' } }
    post.mockResolvedValue(response)
    const input = {
      monthly_contribution_delta: '250.00',
      contribution_start_date: '2026-09-01',
      one_time_outflow: { date: '2027-01-15', amount: '1000.00' },
    }

    await expect(generateScenario(42, input, 'idem-1')).resolves.toEqual(response.data)
    expect(post).toHaveBeenCalledWith('/api/v1/goals/42/scenarios', input, { headers: { 'Idempotency-Key': 'idem-1' } })
  })

  it('uses owner-scoped read, archive, and bounded comparison endpoints', async () => {
    get.mockResolvedValue({ data: { scenario_id: 'abc' } })
    post.mockResolvedValue({ data: { lifecycle_state: 'archived' } })

    await readScenario('abc')
    await archiveScenario('abc', 'archive-1')
    await compareScenarios(['one', 'two', 'three', 'ignored'])

    expect(get).toHaveBeenCalledWith('/api/v1/scenarios/abc')
    expect(post).toHaveBeenNthCalledWith(1, '/api/v1/scenarios/abc/archive', null, { headers: { 'Idempotency-Key': 'archive-1' } })
    expect(post).toHaveBeenNthCalledWith(2, '/api/v1/scenarios/compare', { scenario_ids: ['one', 'two', 'three'] })
  })

  it('returns a stable sanitized message for known and unknown server failures', () => {
    expect(readScenarioError({ isAxiosError: true, response: { data: { code: 'scenario_baseline_conflict', message: 'secret backend detail' } } })).toEqual({
      code: 'scenario_baseline_conflict',
      message: 'Scenario Lab could not complete that request. No client-side result was calculated.',
      recovery: 'Refresh the goal and try again against the current baseline.',
    })
    expect(readScenarioError({ response: { data: { code: 'provider_secret' } } })).toEqual({
      code: 'unknown',
      message: 'Scenario Lab could not complete that request. No client-side result was calculated.',
      recovery: 'Retry when the service is available. Atlas will not estimate a result locally.',
    })
  })
})
