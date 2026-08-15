import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/lib/api', () => ({ default: { get, post } }))

import {
  getDerivedRecommendation,
  getDerivedRecommendationResource,
  parseDecisionETag,
  parseDecisionETagHeader,
  parseForecastETag,
  postDecisionJournal,
  readSanitizedError,
} from '@/lib/api_phase2'

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
      forecast_etag: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-v1',
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

  it('reads the authoritative decision ETag from the recommendation response header', async () => {
    const response = { schema_version: 'atlas-decision-journal-entry/v1', journal_entry_id: 'journal-id', recommendation_id: 'recommendation-id', action_taken: 'accept', decided_at: '2026-08-14T00:00:00Z', decision_etag: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-d1', links: [] }
    get.mockResolvedValue({
      data: { forecast_etag: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-v1', links: [] } as never,
      headers: { etag: '"aabbccdd-1111-4111-8111-aaaaaaaaaaaa-d1"' },
    })

    const resource = await getDerivedRecommendationResource('forecast-id')
    expect(resource.recommendation.forecast_etag).toBe('aabbccdd-1111-4111-8111-aaaaaaaaaaaa-v1')
    expect(resource.decisionEtag).toBe('aabbccdd-1111-4111-8111-aaaaaaaaaaaa-d1')
    expect(resource.decisionEtag).not.toBe(resource.recommendation.forecast_etag)
    expect(response.decision_etag).toBe(resource.decisionEtag)
  })

  it('rejects missing or malformed authoritative decision ETags', async () => {
    get.mockResolvedValue({ data: { forecast_etag: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-v1', links: [] } as never, headers: {} })
    await expect(getDerivedRecommendationResource('forecast-id')).rejects.toMatchObject({ code: 'decision_etag_unavailable' })

    get.mockResolvedValue({ data: { forecast_etag: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-v1', links: [] } as never, headers: { etag: '"aabbccdd-1111-4111-8111-aaaaaaaaaaaa-v1"' } })
    await expect(getDerivedRecommendationResource('forecast-id')).rejects.toMatchObject({ code: 'decision_etag_unavailable' })
    expect(parseDecisionETag('aabbccdd-1111-4111-8111-aaaaaaaaaaaa-v1')).toBeNull()
    expect(parseDecisionETagHeader('aabbccdd-1111-4111-8111-aaaaaaaaaaaa-d1')).toBeNull()
  })

  it('writes a valid decision ETag and never accepts a forecast ETag at the TypeScript boundary', async () => {
    const response = { schema_version: 'atlas-decision-journal-entry/v1', journal_entry_id: 'journal-id', recommendation_id: 'recommendation-id', action_taken: 'accept', decided_at: '2026-08-14T00:00:00Z', decision_etag: 'aabbccdd-1111-4111-aaaaaaaaaaaa-d1', links: [] }
    post.mockResolvedValue({ data: response })
    const decisionEtag = parseDecisionETag('aabbccdd-1111-4111-8111-aaaaaaaaaaaa-d1')
    const forecastEtag = parseForecastETag('aabbccdd-1111-4111-8111-aaaaaaaaaaaa-v1')
    if (!decisionEtag || !forecastEtag) throw new Error('fixture ETags must be valid')

    await expect(postDecisionJournal('recommendation-id', { action: 'accept', decision_etag: decisionEtag }, 'idem-123')).resolves.toEqual(response)
    expect(post).toHaveBeenCalledWith('/api/v1/recommendations/recommendation-id/decisions', { action: 'accept', decision_etag: decisionEtag }, { headers: { 'Idempotency-Key': 'idem-123', 'If-Match': '"aabbccdd-1111-4111-8111-aaaaaaaaaaaa-d1"' } })
    // @ts-expect-error ForecastETag must never be accepted as a DecisionETag.
    if (false) postDecisionJournal('recommendation-id', { action: 'accept', decision_etag: forecastEtag }, 'idem-forecast')
  })

  it('fails closed before POST for a malformed runtime decision ETag', async () => {
    const malformed = 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-v1' as never
    await expect(postDecisionJournal('recommendation-id', { action: 'accept', decision_etag: malformed }, 'idem-123')).rejects.toMatchObject({ code: 'decision_etag_unavailable' })
    expect(post).not.toHaveBeenCalled()
  })

  it('maps known failures to stable copy without exposing server details', () => {
    const sanitized = readSanitizedError({ isAxiosError: true, response: { data: { code: 'decision_version_conflict', message: 'database secret' } } })
    expect(sanitized.code).toBe('decision_version_conflict')
    expect(sanitized.message).not.toContain('database secret')
    expect(readSanitizedError({ response: { data: { code: 'provider_secret', message: 'do not expose' } } })).toEqual({ code: 'unknown', message: '' })
  })
})
