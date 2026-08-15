import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/lib/api', () => ({ default: { get, post } }))

import { getDerivedRecommendation, postDecisionJournal, readSanitizedError } from '@/lib/api_phase2'

describe('authoritative Decisions API client', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
  })

  it('reads the server-derived recommendation contract', async () => {
    const envelope = {
      schema_version: 'atlas-derived-recommendation/v1',
      recommendation_kind: 'hold',
      action_verb: 'Hold',
      why_now: 'Evidence remains current.',
      linked_goal_id: 42,
      forecast_id: 'forecast-id',
      forecast_etag: 'forecast-etag-v1',
      evidence_references: { forecast_id: 'forecast-id', model_version: 'model', calculation_version: 'calc', input_state_hash: 'hash', data_as_of: '2026-08-14T00:00:00Z' },
      expected_impact_range: { min_delta_decimal: '0', max_delta_decimal: '0' },
      risks: [],
      confidence: 'high',
      assumptions_reference: 'assumption-hash',
      expiration: '2026-08-15T00:00:00Z',
      issuer: 'atlas-deterministic-rules/v1',
      links: [{ rel: 'decide', href: '/api/v1/recommendations/recommendation-id/decisions' }],
    }
    get.mockResolvedValue({ data: envelope })

    await expect(getDerivedRecommendation('forecast-id')).resolves.toEqual(envelope)
    expect(get).toHaveBeenCalledWith('/api/v1/forecasts/forecast-id/recommendation')
  })

  it('writes one idempotent append-only decision journal request', async () => {
    const response = { schema_version: 'atlas-decision-journal-entry/v1', journal_entry_id: 'journal-id', recommendation_id: 'recommendation-id', action_taken: 'accept', decided_at: '2026-08-14T00:00:00Z', decision_etag: 'journal-etag', links: [] }
    post.mockResolvedValue({ data: response })

    await expect(postDecisionJournal('recommendation-id', { action: 'accept', decision_etag: 'forecast-etag-v1' }, 'idem-123')).resolves.toEqual(response)
    expect(post).toHaveBeenCalledWith('/api/v1/recommendations/recommendation-id/decisions', { action: 'accept', decision_etag: 'forecast-etag-v1' }, { headers: { 'Idempotency-Key': 'idem-123' } })
  })

  it('maps known failures to stable copy without exposing server details', () => {
    const sanitized = readSanitizedError({ isAxiosError: true, response: { data: { code: 'decision_version_conflict', message: 'database secret' } } })
    expect(sanitized.code).toBe('decision_version_conflict')
    expect(sanitized.message).not.toContain('database secret')
    expect(readSanitizedError({ response: { data: { code: 'provider_secret', message: 'do not expose' } } })).toEqual({ code: 'unknown', message: '' })
  })
})
