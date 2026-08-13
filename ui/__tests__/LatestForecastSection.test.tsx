/**
 * Phase 2 Slice 2 — Vitest tests for ``<LatestForecastSection />``.
 *
 *  Matrix item 13 coverage: per-goal isolation. Each goal's fetch
 *  chain (forecast → recommendation) is dispatched through
 *  ``Promise.all`` and races are isolated.
 *
 *  Authoritative anchors:
 *    - ``ui/lib/api_phase2.ts`` exports
 *        ``getLatestForecastForGoal(goalId: number)``
 *        ``getDerivedRecommendation(forecastId: string)``
 *      and ``getDerivedRecommendation`` returns the wire object
 *      directly (the page component never wraps it in an envelope).
 *    - ``ui/components/dashboard/LatestForecastSection.tsx`` exports
 *      the component as a **default** export and uses
 *      ``data-testid="goal-slice-${goal.id}"``,
 *      ``data-testid="latest-forecast-section"``, and
 *      ``data-testid="latest-forecast-section-error"``.
 *    - Empty ``goals`` list returns ``null`` (no DOM).
 *    - Goal ``id`` is numeric (typed as ``number``).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

// ``vi.hoisted`` so the mock factory closes over the handles despite
// vitest's hoisting of ``vi.mock`` above module-level declarations.
const {
  mockGetLatestForecastForGoal,
  mockGetDerivedRecommendation,
  mockPostDecisionJournal,
} = vi.hoisted(() => ({
  mockGetLatestForecastForGoal: vi.fn(),
  mockGetDerivedRecommendation: vi.fn(),
  mockPostDecisionJournal: vi.fn(),
}))

vi.mock('@/lib/api_phase2', () => ({
  getLatestForecastForGoal: mockGetLatestForecastForGoal,
  getDerivedRecommendation: mockGetDerivedRecommendation,
  postDecisionJournal: mockPostDecisionJournal,
  readSanitizedError: (err: unknown) => {
    const e = err as {
      isAxiosError?: boolean
      response?: { data?: { code?: unknown; message?: unknown } }
    }
    const data = e?.response?.data
    const validCodes = new Set([
      'forecast_read_api_unavailable',
      'forecast_not_found',
      'recommendation_not_found',
      'decision_version_conflict',
      'forecast_validation_error',
    ])
    const code =
      e?.isAxiosError && typeof data?.code === 'string' && validCodes.has(data.code)
        ? data.code
        : 'unknown'
    const message =
      code !== 'unknown' && typeof data?.message === 'string'
        ? data.message.slice(0, 280)
        : ''
    return { code, message }
  },
  mintIdempotencyKey: () => '44444444-4444-4444-8444-444444444444',
}))

import LatestForecastSection from '@/components/dashboard/LatestForecastSection'

// Numeric IDs — match ``Goal.id: number`` in the real component.
const goalA = { id: 1, name: 'Retirement by 55', target_amount: '15000000.00' }
const goalB = { id: 2, name: 'House down payment', target_amount: '80000.00' }
const goalC = { id: 3, name: 'Emergency fund', target_amount: '30000.00' }

// Bare-minimum ``ForecastWire`` satisfied by ``LatestForecastCard``.
function makeForecast(goalId: number) {
  return {
    id: `forecast-uuid-goal-${goalId}`,
    goal_id: goalId,
    user_id: 1,
    currency: 'USD' as const,
    kind: 'goal_projection' as const,
    latest_version_number: 1,
    latest_version_id: `version-uuid-goal-${goalId}`,
    etag: `etag-goal-${goalId}-v1`,
    created_at: '2026-08-01T00:00:00.000000Z',
    updated_at: null,
    links: [],
  }
}

function makeVersion(goalId: number) {
  return {
    id: `version-uuid-goal-${goalId}`,
    forecast_id: `forecast-uuid-goal-${goalId}`,
    version_number: 1,
    ending_balance: '14500000.00',
    target_decision: {
      rounded_ending_balance: '14500000.00',
      rounded_target_amount: '15000000.00',
      target_status: false,
      decision_etag: `etag-goal-${goalId}-v1`,
    },
    drivers: { data_age_days: 4, max_data_age_days: 14 },
    scenarios: [
      {
        name: 'conservative' as const,
        annual_return_rate: '0.0400',
        ending_balance: '12800000.00',
      },
      {
        name: 'base' as const,
        annual_return_rate: '0.0600',
        ending_balance: '14500000.00',
      },
      {
        name: 'optimistic' as const,
        annual_return_rate: '0.0900',
        ending_balance: '17800000.00',
      },
    ],
    assumption_snapshot: {},
    provenance_snapshot: {},
    data_as_of: '2026-07-28T00:00:00.000000Z',
    calculated_at: '2026-08-01T00:00:00.000000Z',
    model_version: 'atlas-projection/v1',
    calculation_version: 'atlas-calculation-decimal/v1',
    input_state_hash: 'a'.repeat(64),
  }
}

// ``getDerivedRecommendation`` returns the wire directly — no envelope.
function makeRecommendationWire(goalId: number) {
  return {
    schema_version: 'atlas-derived-recommendation/v1' as const,
    recommendation_kind: 'hold' as const,
    action_verb: 'Hold',
    why_now: 'Your projection is on track at the current cadence.',
    linked_goal_id: goalId,
    forecast_id: `forecast-uuid-goal-${goalId}`,
    forecast_etag: `etag-goal-${goalId}-v1`,
    evidence_references: {
      forecast_id: `forecast-uuid-goal-${goalId}`,
      model_version: 'atlas-projection/v1',
      calculation_version: 'atlas-calculation-decimal/v1',
      input_state_hash: 'a'.repeat(64),
      data_as_of: '2026-07-28T00:00:00.000000Z',
    },
    expected_impact_range: {
      min_delta_decimal: '0.00',
      max_delta_decimal: '0.00',
    },
    risks: [],
    confidence: 'high' as const,
    assumptions_reference: 'b'.repeat(64),
    expiration: '2026-08-02T00:00:00.000000Z',
    issuer: 'atlas-deterministic-rules/v1' as const,
    links: [],
  }
}

// Map a forecastId (e.g. ``forecast-uuid-goal-2``) to its numeric goal id.
function goalIdFromForecastId(forecastId: string): number {
  const m = forecastId.match(/goal-(\d+)/)
  return m ? Number(m[1]) : 0
}

const readyEnvelope = (goalId: number) => ({
  state: 'ready' as const,
  goal_id: goalId,
  forecast: makeForecast(goalId),
  version: makeVersion(goalId),
})

const readGateOff = {
  isAxiosError: true,
  response: {
    status: 503,
    data: {
      code: 'forecast_read_api_unavailable',
      message: 'Forecast reads are disabled.',
    },
  },
}

const notFound = {
  isAxiosError: true,
  response: {
    status: 404,
    data: { code: 'forecast_not_found', message: 'Forecast not found.' },
  },
}

const conflict409 = {
  isAxiosError: true,
  response: {
    status: 409,
    data: { code: 'decision_version_conflict', message: 'etag conflict' },
  },
}

beforeEach(() => {
  mockGetLatestForecastForGoal.mockReset()
  mockGetDerivedRecommendation.mockReset()
  mockPostDecisionJournal.mockReset()
})

// =======================================================================
// Tests — per-goal isolation matrix (matrix item 13)
// =======================================================================

describe('<LatestForecastSection /> — per-goal isolation (matrix item 13)', () => {
  it('independent dispatch: each goal triggers a separate forecast + recommendation call', async () => {
    mockGetLatestForecastForGoal.mockImplementation(
      async (goalId: number) => readyEnvelope(goalId),
    )
    mockGetDerivedRecommendation.mockImplementation(
      async (forecastId: string) => makeRecommendationWire(goalIdFromForecastId(forecastId)),
    )

    render(<LatestForecastSection goals={[goalA, goalB, goalC]} />)

    await waitFor(() => {
      expect(screen.getByTestId('goal-slice-1')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByTestId('goal-slice-2')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByTestId('goal-slice-3')).toBeInTheDocument()
    })

    // Independent dispatch — each goal triggered exactly one
    // forecast fetch and one recommendation fetch.
    expect(mockGetLatestForecastForGoal).toHaveBeenCalledTimes(3)
    expect(mockGetLatestForecastForGoal).toHaveBeenCalledWith(1)
    expect(mockGetLatestForecastForGoal).toHaveBeenCalledWith(2)
    expect(mockGetLatestForecastForGoal).toHaveBeenCalledWith(3)
    expect(mockGetDerivedRecommendation).toHaveBeenCalledTimes(3)
  })

  it('per-goal 503 surfaces the sanitized section banner AND isolates siblings', async () => {
    mockGetLatestForecastForGoal.mockImplementation(async (goalId: number) => {
      if (goalId === 2) throw readGateOff
      return readyEnvelope(goalId)
    })
    mockGetDerivedRecommendation.mockImplementation(
      async (forecastId: string) => makeRecommendationWire(goalIdFromForecastId(forecastId)),
    )

    render(<LatestForecastSection goals={[goalA, goalB, goalC]} />)

    // Slice containers mount unconditionally from initial render
    // (before any fetch resolves), so we cannot rely on
    // ``goal-slice-N`` presence as a sentinel for Promise.all
    // completion. The ACTUAL deterministic sentinel is the
    // section-level error banner, which only appears after Goal 2's
    // rejected promise settles through the catch block and calls
    // ``setSectionError``. Use ``findByTestId`` (RTL async-with-
    // retry) so we deterministically wait for the React commit
    // that mounts the banner — no microtask-trust. The
    // ``timeout: 3000`` is a small bump from the RTL default 1000
    // to account for React 18 automatic batching + jsdom render-
    // commit latency on the local runner. NOT an "excessive
    // timeout" workaround (we are still in the 1000..3000ms
    // range).
    const banner = await screen.findByTestId(
      'latest-forecast-section-error',
      {},
      { timeout: 3000 },
    )
    expect(banner).toBeInTheDocument()

    // Sibling slices still rendered despite goal 2's 503
    // (per-goal isolation matrix contract).
    expect(
      within(screen.getByTestId('goal-slice-1')).getByTestId(
        'forecast-projected',
      ),
    ).toBeInTheDocument()
    expect(
      within(screen.getByTestId('goal-slice-3')).getByTestId(
        'forecast-projected',
      ),
    ).toBeInTheDocument()
    // Goal 2 collapsed to per-goal ``no_forecast`` — its specific
    // ``forecast-projected`` card is absent (no forecast to render)
    // even though the slice container is mounted.
    expect(
      within(screen.getByTestId('goal-slice-2')).queryByTestId(
        'forecast-projected',
      ),
    ).toBeNull()

    // Exactly ONE banner despite two ready siblings.
    expect(
      screen.getAllByTestId('latest-forecast-section-error'),
    ).toHaveLength(1)
  })

  it('per-goal cross-user 404 collapses to no_forecast WITHOUT section escalation', async () => {
    mockGetLatestForecastForGoal.mockImplementation(async (goalId: number) => {
      if (goalId === 1) throw notFound
      return readyEnvelope(goalId)
    })
    mockGetDerivedRecommendation.mockImplementation(
      async (forecastId: string) => makeRecommendationWire(goalIdFromForecastId(forecastId)),
    )

    render(<LatestForecastSection goals={[goalA, goalB]} />)

    await waitFor(() => {
      expect(screen.getByTestId('goal-slice-1')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByTestId('goal-slice-2')).toBeInTheDocument()
    })

    // 404 collapses to per-goal no_forecast silently — no section banner.
    expect(
      screen.queryByTestId('latest-forecast-section-error'),
    ).not.toBeInTheDocument()
  })

  it('per-goal 409 idempotency conflict surfaces a sanitized section warning', async () => {
    mockGetLatestForecastForGoal.mockImplementation(async (goalId: number) => {
      if (goalId === 3) throw conflict409
      return readyEnvelope(goalId)
    })
    mockGetDerivedRecommendation.mockImplementation(
      async (forecastId: string) => makeRecommendationWire(goalIdFromForecastId(forecastId)),
    )

    render(<LatestForecastSection goals={[goalA, goalB, goalC]} />)

    await waitFor(() => {
      expect(screen.getByTestId('goal-slice-1')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByTestId('goal-slice-2')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByTestId('goal-slice-3')).toBeInTheDocument()
    })

    const banner = await screen.findByTestId('latest-forecast-section-error')
    expect(banner).toHaveTextContent('etag conflict')
  })

  it('empty goals list returns null — no DOM, zero fetches', async () => {
    render(<LatestForecastSection goals={[]} />)
    await waitFor(() => {
      expect(
        screen.queryByTestId('latest-forecast-section'),
      ).not.toBeInTheDocument()
    })
    expect(mockGetLatestForecastForGoal).not.toHaveBeenCalled()
    expect(mockGetDerivedRecommendation).not.toHaveBeenCalled()
  })

  it('retries an ambiguous decision response with the same idempotency key', async () => {
    mockGetLatestForecastForGoal.mockResolvedValue(readyEnvelope(1))
    mockGetDerivedRecommendation.mockResolvedValue(makeRecommendationWire(1))
    let resolveRetry: ((value: unknown) => void) | undefined
    mockPostDecisionJournal
      .mockRejectedValueOnce(new Error('transport timeout'))
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveRetry = resolve
          }),
      )

    render(<LatestForecastSection goals={[goalA]} />)
    await screen.findByTestId('recommendation-explained-card-forecast-uuid-goal-1')

    fireEvent.click(screen.getByTestId('rec-accept'))
    await screen.findByTestId('decision-error')
    expect(mockPostDecisionJournal).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByTestId('decision-retry'))
    await waitFor(() => {
      expect(mockPostDecisionJournal).toHaveBeenCalledTimes(2)
    })
    expect(mockPostDecisionJournal.mock.calls[1]?.[0]).toBe(
      mockPostDecisionJournal.mock.calls[0]?.[0],
    )
    expect(mockPostDecisionJournal.mock.calls[1]?.[1]).toEqual(
      mockPostDecisionJournal.mock.calls[0]?.[1],
    )
    expect(mockPostDecisionJournal.mock.calls[1]?.[2]).toBe(
      mockPostDecisionJournal.mock.calls[0]?.[2],
    )

    resolveRetry?.({
      schema_version: 'atlas-decision-journal-entry/v1',
      journal_entry_id: '33333333-3333-4333-8333-333333333333',
      recommendation_id: 'forecast-uuid-goal-1',
      action_taken: 'accept',
      decided_at: '2026-08-01T00:01:00.000000Z',
      decision_etag: 'etag-goal-1-v1-d1',
      links: [],
    })
    await screen.findByTestId('recorded-journal-id')
  })

  it('suppresses a rapid double-click while the same decision is in flight', async () => {
    mockGetLatestForecastForGoal.mockResolvedValue(readyEnvelope(1))
    mockGetDerivedRecommendation.mockResolvedValue(makeRecommendationWire(1))
    mockPostDecisionJournal.mockImplementation(
      () => new Promise(() => undefined),
    )

    render(<LatestForecastSection goals={[goalA]} />)
    await screen.findByTestId('recommendation-explained-card-forecast-uuid-goal-1')

    fireEvent.click(screen.getByTestId('rec-accept'))
    fireEvent.click(screen.getByTestId('rec-accept'))
    await waitFor(() => {
      expect(mockPostDecisionJournal).toHaveBeenCalledTimes(1)
    })
    expect(screen.getByTestId('rec-accept')).toBeDisabled()
  })

  it('loading state: forecast card absent until first fetch resolves per goal', async () => {
    // Capture resolver for goal 2 so the test can release it later.
    let resolveFc2: ((v: ReturnType<typeof readyEnvelope>) => void) | undefined
    mockGetLatestForecastForGoal.mockImplementation(
      (goalId: number) =>
        new Promise((resolve) => {
          if (goalId === 1) {
            resolve(readyEnvelope(goalId))
          } else {
            // Goal 2 stays pending until the test releases it.
            resolveFc2 = resolve as (v: ReturnType<typeof readyEnvelope>) => void
          }
        }),
    )
    mockGetDerivedRecommendation.mockImplementation(
      async (forecastId: string) => makeRecommendationWire(goalIdFromForecastId(forecastId)),
    )

    render(<LatestForecastSection goals={[goalA, goalB]} />)

    // Goal 1's slice container is mounted from initial render and
    // its forecast card surfaces once the resolved promise lands.
    await waitFor(() => {
      const goal1Slice = screen.getByTestId('goal-slice-1')
      expect(
        within(goal1Slice).getByTestId('forecast-projected'),
      ).toBeInTheDocument()
    })

    // Goal 2's slice container IS in DOM from initial render, BUT
    // its forecast card is absent because the fetch is still
    // pending. This is the loading-state assertion under test.
    const goal2SliceBefore = screen.getByTestId('goal-slice-2')
    expect(
      within(goal2SliceBefore).queryByTestId('forecast-projected'),
    ).toBeNull()

    // Release goal 2 — its forecast card surfaces; deterministic
    // sync assertion once the resolved promise has triggered the
    // state update + render.
    resolveFc2?.(readyEnvelope(2))
    await waitFor(() => {
      expect(
        within(screen.getByTestId('goal-slice-2')).getByTestId(
          'forecast-projected',
        ),
      ).toBeInTheDocument()
    })
  })
})
