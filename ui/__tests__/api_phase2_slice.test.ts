/**
 * Phase 2 Slice 2 — API client tests for `ui/lib/api_phase2.ts`.
 *
 * Per `PHASE2_VERTICAL_SLICE_PLAN.md` §7 "API client tests":
 *   - Each new method: happy path returns typed object.
 *   - 503 surfaces ``ReadApiDisabledEnvelope.code`` to caller.
 *   - 409 surfaces ``DecisionConflictEnvelope.code``.
 *   - NO money value is ever typed as ``number`` in TS — runtime
 *     assertion via JSON.parse round-trip plus a `typeof === 'string'`
 *     invariant on every typed money field.
 *
 *  Strategy:
 *    - Mock the underlying axios instance so we exercise OUR typed
 *      wrappers, not axios internals. Existing tests already use the
 *      ``vi.mock('@/lib/api', () => ({ api: { get, post } }))`` shape
 *      (see `ui/__tests__/goals.test.tsx`).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

// ``vi.mock`` is hoisted ABOVE module-level ``const`` declarations so
// referencing the mock handles directly inside the factory would
// throw ``Cannot access 'mockGet' before initialization``. Use
// ``vi.hoisted`` to surface the handles to the hoisted scope
// independent of source-text order.
const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}))
vi.mock('@/lib/api', () => ({
  api: { get: mockGet, post: mockPost },
  default: { get: mockGet, post: mockPost },
}))

import {
  getLatestForecastForGoal,
  getDerivedRecommendation,
  postDecisionJournal,
  readSanitizedError,
  mintIdempotencyKey,
} from '@/lib/api_phase2'

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
})

// ---- Fixtures -----------------------------------------------------------

const FORECAST_WIRE = {
  id: '11111111-1111-4111-8111-111111111111',
  goal_id: 42,
  user_id: 1,
  currency: 'USD',
  kind: 'goal_projection',
  latest_version_number: 3,
  latest_version_id: '22222222-2222-4222-8222-222222222222',
  etag: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-v3',
  created_at: '2026-08-01T00:00:00.000000Z',
  updated_at: null,
  links: [
    {
      rel: 'self' as const,
      href: '/api/v1/forecasts/11111111-1111-4111-8111-111111111111',
    },
  ],
}

const VERSION_WIRE = {
  id: '22222222-2222-4222-8222-222222222222',
  forecast_id: '11111111-1111-4111-8111-111111111111',
  version_number: 3,
  ending_balance: '4500000.00', // canonical Decimal STRING, not number.
  target_decision: {
    rounded_ending_balance: '4500000.00',
    rounded_target_amount: '15000000.00',
    target_status: false,
    decision_etag: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-v3',
  },
  drivers: { data_age_days: 4, max_data_age_days: 14 },
  scenarios: [
    {
      name: 'conservative' as const,
      annual_return_rate: '0.0400',
      ending_balance: '3200000.00',
    },
    {
      name: 'base' as const,
      annual_return_rate: '0.0600',
      ending_balance: '4500000.00',
    },
    {
      name: 'optimistic' as const,
      annual_return_rate: '0.0900',
      ending_balance: '6800000.00',
    },
  ],
  assumption_snapshot: {
    decision_window: 'q3-2026',
    contribution_amount: '1500.00',
  },
  provenance_snapshot: { source_aggregation: 'finlynq-state/v1' },
  data_as_of: '2026-07-28T00:00:00.000000Z',
  calculated_at: '2026-08-01T00:00:00.000000Z',
  model_version: 'atlas-projection/v1',
  calculation_version: 'atlas-calculation-decimal/v1',
  input_state_hash: 'a'.repeat(64),
}

const RECOMMENDATION_WIRE = {
  schema_version: 'atlas-derived-recommendation/v1' as const,
  recommendation_kind: 'increase_contribution' as const,
  action_verb: 'Increase',
  why_now:
    'Your projection falls 10.5M short at the current contribution cadence.',
  linked_goal_id: 42,
  forecast_id: '11111111-1111-4111-8111-111111111111',
  forecast_etag: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-v3',
  evidence_references: {
    forecast_id: '11111111-1111-4111-8111-111111111111',
    model_version: 'atlas-projection/v1',
    calculation_version: 'atlas-calculation-decimal/v1',
    input_state_hash: 'a'.repeat(64),
    data_as_of: '2026-07-28T00:00:00.000000Z',
  },
  expected_impact_range: {
    min_delta_decimal: '12000.00',
    max_delta_decimal: '32000.00',
  },
  risks: ['liquidity_reduction' as const],
  confidence: 'medium' as const,
  assumptions_reference: 'b'.repeat(64),
  expiration: '2026-08-02T00:00:00.000000Z',
  issuer: 'atlas-deterministic-rules/v1' as const,
  links: [
    {
      rel: 'self' as const,
      href: '/api/v1/forecasts/11111111-1111-4111-8111-111111111111/recommendation',
    },
  ],
}

const JOURNAL_WIRE = {
  schema_version: 'atlas-decision-journal-entry/v1' as const,
  journal_entry_id: '33333333-3333-4333-8333-333333333333',
  recommendation_id: '11111111-1111-4111-8111-111111111111',
  action_taken: 'accept' as const,
  decided_at: '2026-08-01T00:01:00.000000Z',
  decision_etag: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-d1',
  links: [
    {
      rel: 'self' as const,
      href: '/api/v1/decisions/33333333-3333-4333-8333-333333333333',
    },
  ],
}

// ---- AxiosError factory (matches the slice's `isAxiosError` shape) -----

function axiosError(
  status: number,
  data: { code: string; message?: string; current_etag?: string },
): Error & { isAxiosError: boolean; response: { status: number; data: unknown } } {
  const err = Object.assign(new Error('Request failed'), {
    isAxiosError: true,
    response: { status, data },
  })
  return err as Error & {
    isAxiosError: boolean
    response: { status: number; data: unknown }
  }
}

// ---- getLatestForecastForGoal ------------------------------------------

describe('api_phase2 — getLatestForecastForGoal', () => {
  it('happy path returns ready envelope with typed forecast + version', async () => {
    mockGet
      .mockResolvedValueOnce({ data: { forecasts: [FORECAST_WIRE] } })
      .mockResolvedValueOnce({ data: VERSION_WIRE })

    const result = await getLatestForecastForGoal(42)
    expect(result.state).toBe('ready')
    if (result.state !== 'ready') return
    expect(result.goal_id).toBe(42)
    expect(result.forecast.id).toBe(FORECAST_WIRE.id)
    expect(result.version.ending_balance).toBe('4500000.00')
    expect(typeof result.version.ending_balance).toBe('string')

    expect(mockGet).toHaveBeenCalledTimes(2)
    expect(mockGet.mock.calls[0]?.[0]).toBe('/api/v1/forecasts')
    expect(mockGet.mock.calls[0]?.[1]).toEqual({
      params: { goal_id: 42, limit: 4 },
    })
    expect(mockGet.mock.calls[1]?.[0]).toBe(
      `/api/v1/forecasts/${FORECAST_WIRE.id}/versions/${FORECAST_WIRE.latest_version_number}`,
    )
  })

  it('returns {state: "no_forecast"} for empty list', async () => {
    mockGet.mockResolvedValueOnce({ data: { forecasts: [] } })
    const result = await getLatestForecastForGoal(42)
    expect(result.state).toBe('no_forecast')
    if (result.state !== 'no_forecast') return
    expect(result.goal_id).toBe(42)
    expect(mockGet).toHaveBeenCalledTimes(1)
  })

  it('propagates 503 sanitized code via AxiosError', async () => {
    mockGet.mockRejectedValueOnce(
      axiosError(503, {
        code: 'forecast_read_api_unavailable',
        message: 'Forecast read API is currently disabled.',
      }),
    )
    const err = await getLatestForecastForGoal(42).catch((e) => e)
    expect(readSanitizedError(err).code).toBe(
      'forecast_read_api_unavailable',
    )
  })

  it('propagates 404 missing/cross-user via forecast_not_found', async () => {
    mockGet.mockRejectedValueOnce(
      axiosError(404, {
        code: 'forecast_not_found',
        message: 'Forecast not found.',
      }),
    )
    const err = await getLatestForecastForGoal(42).catch((e) => e)
    expect(readSanitizedError(err).code).toBe('forecast_not_found')
  })
})

// ---- getDerivedRecommendation -------------------------------------------

describe('api_phase2 — getDerivedRecommendation', () => {
  it('happy path returns typed DeterministicRecommendationWire', async () => {
    mockGet.mockResolvedValueOnce({ data: RECOMMENDATION_WIRE })
    const result = await getDerivedRecommendation(FORECAST_WIRE.id)
    expect(result.schema_version).toBe('atlas-derived-recommendation/v1')
    expect(result.action_verb).toBe('Increase')
    expect(result.confidence).toBe('medium')
    expect(typeof result.expected_impact_range.min_delta_decimal).toBe('string')
    expect(typeof result.expected_impact_range.max_delta_decimal).toBe('string')
    expect(mockGet).toHaveBeenCalledWith(
      `/api/v1/forecasts/${FORECAST_WIRE.id}/recommendation`,
    )
  })

  it('propagates 404 recommendation_not_found', async () => {
    mockGet.mockRejectedValueOnce(
      axiosError(404, {
        code: 'recommendation_not_found',
        message: 'Recommendation not found.',
      }),
    )
    const err = await getDerivedRecommendation(FORECAST_WIRE.id).catch(
      (e) => e,
    )
    expect(readSanitizedError(err).code).toBe('recommendation_not_found')
  })
})

// ---- postDecisionJournal -----------------------------------------------

describe('api_phase2 — postDecisionJournal', () => {
  it('happy path writes one row, returns DecisionJournalEntryWire', async () => {
    mockPost.mockResolvedValueOnce({ data: JOURNAL_WIRE })
    const body = {
      action: 'accept' as const,
      decision_etag: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-d1',
    }
    const idemKey = mintIdempotencyKey()
    const result = await postDecisionJournal(
      RECOMMENDATION_WIRE.forecast_id,
      body,
      idemKey,
    )
    expect(result.schema_version).toBe('atlas-decision-journal-entry/v1')
    expect(result.journal_entry_id).toBe(JOURNAL_WIRE.journal_entry_id)
    expect(result.action_taken).toBe('accept')
    // The journal envelope carries NO money payload (plan §5).
    expect('ending_balance' in result).toBe(false)

    expect(mockPost).toHaveBeenCalledWith(
      `/api/v1/recommendations/${RECOMMENDATION_WIRE.forecast_id}/decisions`,
      body,
      expect.objectContaining({
        headers: expect.objectContaining({
          'Idempotency-Key': idemKey,
        }),
      }),
    )
  })

  it('replay (same idemKey + same payload) returns EXACT same row', async () => {
    mockPost
      .mockResolvedValueOnce({ data: JOURNAL_WIRE })
      .mockResolvedValueOnce({ data: JOURNAL_WIRE })
    const body = {
      action: 'accept' as const,
      decision_etag: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-d1',
    }
    const idemKey = mintIdempotencyKey()
    const a = await postDecisionJournal(
      RECOMMENDATION_WIRE.forecast_id,
      body,
      idemKey,
    )
    const b = await postDecisionJournal(
      RECOMMENDATION_WIRE.forecast_id,
      body,
      idemKey,
    )
    expect(a.journal_entry_id).toBe(b.journal_entry_id)
    expect(a.decided_at).toBe(b.decided_at) // SAME row, NOT a new row
  })

  it('409 conflict envelope surfaces decision_version_conflict', async () => {
    mockPost.mockRejectedValueOnce(
      axiosError(409, {
        code: 'decision_version_conflict',
        message: 'Decision etag conflict.',
        current_etag: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-d1',
      }),
    )
    const body = {
      action: 'accept' as const,
      decision_etag: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-d1',
    }
    const err = await postDecisionJournal(
      RECOMMENDATION_WIRE.forecast_id,
      body,
      mintIdempotencyKey(),
    ).catch((e) => e)
    expect(readSanitizedError(err).code).toBe('decision_version_conflict')
  })

  it('422 validation envelope surfaces forecast_validation_error', async () => {
    mockPost.mockRejectedValueOnce(
      axiosError(422, {
        code: 'forecast_validation_error',
        message: 'Validation failed',
      }),
    )
    const body = {
      action: 'accept' as const,
      decision_etag: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-d1',
    }
    const err = await postDecisionJournal(
      RECOMMENDATION_WIRE.forecast_id,
      body,
      mintIdempotencyKey(),
    ).catch((e) => e)
    expect(readSanitizedError(err).code).toBe('forecast_validation_error')
  })
})

// ---- Decimal-string end-to-end contract ---------------------------------

describe('api_phase2 — money values are canonical Decimal strings', () => {
  it('every money field is a string end-to-end; JSON.parse roundtrip preserves form', async () => {
    mockGet
      .mockResolvedValueOnce({ data: { forecasts: [FORECAST_WIRE] } })
      .mockResolvedValueOnce({ data: VERSION_WIRE })
    const result = await getLatestForecastForGoal(42)
    if (result.state !== 'ready') throw new Error('expected ready')
    // Every money field is `string`.
    expect(typeof result.version.ending_balance).toBe('string')
    expect(typeof result.version.target_decision.rounded_ending_balance).toBe('string')
    expect(typeof result.version.target_decision.rounded_target_amount).toBe('string')
    for (const s of result.version.scenarios) {
      expect(typeof s.ending_balance).toBe('string')
      expect(typeof s.annual_return_rate).toBe('string')
    }
    // JSON.parse(stringify(x)) round-trip preserves the canonical form.
    const roundtrip = JSON.parse(JSON.stringify(result))
    expect(roundtrip.version.ending_balance).toBe('4500000.00')
    expect(roundtrip.version.scenarios[0].ending_balance).toBe('3200000.00')
  })
})

// ---- Idempotency-Key shape contract ------------------------------------

describe('api_phase2 — mintIdempotencyKey shape', () => {
  it('produces a 1..255-char ASCII visible Idempotency-Key', () => {
    for (let i = 0; i < 100; i++) {
      const k = mintIdempotencyKey()
      expect(k.length).toBeGreaterThanOrEqual(1)
      expect(k.length).toBeLessThanOrEqual(255)
      // bounded: visible ASCII (U+0021..U+007E).
      expect(/^[\x21-\x7E]+$/.test(k)).toBe(true)
    }
  })
})

// ---- readSanitizedError hardening --------------------------------------

describe('api_phase2 — readSanitizedError', () => {
  it('non-axios error → unknown', () => {
    const env = readSanitizedError(new Error('boom'))
    expect(env.code).toBe('unknown')
  })

  it('axios with arbitrary body → unknown (no leaks)', () => {
    const err = Object.assign(new Error('boom'), {
      isAxiosError: true,
      response: {
        status: 500,
        data: { detailed_internal_state: 'should not leak' },
      },
    })
    expect(readSanitizedError(err).code).toBe('unknown')
  })

  it('axios 503 with read-disabled envelope → read-disabled code', () => {
    const err = axiosError(503, {
      code: 'forecast_read_api_unavailable',
      message: 'off',
    })
    expect(readSanitizedError(err).code).toBe(
      'forecast_read_api_unavailable',
    )
  })
})
