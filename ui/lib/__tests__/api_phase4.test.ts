import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/lib/api', () => ({ default: { get, post } }))

import {
  getDecisionHistory,
  getDecisionHistoryForGoals,
  readDecisionHistoryError,
  recordDecisionHistory,
} from '@/lib/api_phase4'

describe('authoritative Decision History API client', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
  })

  it('loads owner-scoped history for each goal and preserves server IDs/lifecycles', async () => {
    get.mockResolvedValue({
      data: {
        schema_version: 'atlas-decision-history-envelope/v1',
        history: [{
          history_id: 'history-42',
          recommendation_id: 'recommendation-42',
          decision_id: 'journal-42',
          decision_action: 'accept',
          alternatives: ['do_nothing', 'accept'],
          rationale: 'Review the current evidence.',
          supersedes_history_id: null,
          recorded_at: '2026-08-14T00:00:00Z',
          audit: null,
          outcome_lifecycles: ['pending', 'measured'],
        }],
      },
    })

    const result = await getDecisionHistoryForGoals([42])
    expect(result.historyByGoal[42]?.[0]?.history_id).toBe('history-42')
    expect(result.historyByGoal[42]?.[0]?.decision_id).toBe('journal-42')
    expect(result.historyByGoal[42]?.[0]?.outcome_lifecycles).toEqual(['pending', 'measured'])
    expect(result.unavailableGoalIds).toEqual([])
    expect(get).toHaveBeenCalledWith('/api/v1/goals/42/decision-history')
  })

  it('records history with the journal ID and a stable idempotency key', async () => {
    const response = {
      schema_version: 'atlas-decision-history-envelope/v1',
      history_id: 'history-42',
      decision_action: 'accept',
      recorded_at: '2026-08-14T00:00:00Z',
      replayed: false,
    }
    post.mockResolvedValue({ data: response })
    const body = {
      recommendation_id: 'recommendation-42',
      decision_journal_entry_id: 'journal-42',
      alternatives: ['do_nothing', 'accept'] as const,
      rationale: 'Review the current evidence.',
    }

    await expect(recordDecisionHistory(42, body, 'history-journal-42')).resolves.toEqual(response)
    expect(post).toHaveBeenCalledWith(
      '/api/v1/goals/42/decision-history',
      body,
      { headers: { 'Idempotency-Key': 'history-journal-42' } },
    )
  })

  it('keeps unavailable and conflict history states sanitized', () => {
    expect(readDecisionHistoryError({ isAxiosError: true, response: { data: { code: 'decision_history_unavailable', message: 'secret' } } })).toBe('unavailable')
    expect(readDecisionHistoryError({ isAxiosError: true, response: { data: { code: 'decision_history_conflict', message: 'secret' } } })).toBe('conflict')
    expect(readDecisionHistoryError({ response: { data: { code: 'private_backend_detail' } } })).toBe('error')
  })

  it('does not expose another goal history when its read fails', async () => {
    get.mockRejectedValue(new Error('not available'))
    const result = await getDecisionHistoryForGoals([7])
    expect(result.historyByGoal[7]).toEqual([])
    expect(result.unavailableGoalIds).toEqual([7])
  })

  it('retains the direct typed read client for individual goal refreshes', async () => {
    const envelope = { schema_version: 'atlas-decision-history-envelope/v1', history: [] }
    get.mockResolvedValue({ data: envelope })
    await expect(getDecisionHistory(42)).resolves.toEqual(envelope)
  })
})
