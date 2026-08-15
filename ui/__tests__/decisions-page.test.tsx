import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { listGoals, getLatestForecastForGoal, getDerivedRecommendation, postDecisionJournal, readSanitizedError } = vi.hoisted(() => ({
  listGoals: vi.fn(),
  getLatestForecastForGoal: vi.fn(),
  getDerivedRecommendation: vi.fn(),
  postDecisionJournal: vi.fn(),
  readSanitizedError: vi.fn(),
}))

vi.mock('@/components/layout/PageLayout', () => ({ default: ({ children }: { children: unknown }) => <>{children}</> }))
vi.mock('@/components/ui/AtlasFilterContext', () => ({ AtlasFilterProvider: ({ children }: { children: unknown }) => <>{children}</> }))
vi.mock('@/components/dashboard/DecisionHistorySection', () => ({ default: () => <div data-testid="decision-history-stub" /> }))
vi.mock('@/lib/api', () => ({ rulesService: { listGoals } }))
vi.mock('@/lib/api_phase2', () => ({
  getLatestForecastForGoal,
  getDerivedRecommendation,
  postDecisionJournal,
  mintIdempotencyKey: () => 'idem-test',
  readSanitizedError,
}))

import { cacheInvalidate } from '@/lib/cache'
import DecisionsPage from '@/app/decisions/page'

const recommendation = {
  schema_version: 'atlas-derived-recommendation/v1',
  recommendation_kind: 'increase_contribution',
  action_verb: 'Increase contribution',
  why_now: 'Current evidence supports a review of the monthly contribution.',
  linked_goal_id: 42,
  forecast_id: 'forecast-42',
  forecast_etag: 'forecast-etag-v1',
  evidence_references: { forecast_id: 'forecast-42', model_version: 'model', calculation_version: 'calc', input_state_hash: 'hash', data_as_of: '2026-08-14T00:00:00Z' },
  expected_impact_range: { min_delta_decimal: '100.00', max_delta_decimal: '250.00' },
  risks: ['reversibility_required'],
  confidence: 'medium',
  assumptions_reference: 'assumption-hash',
  expiration: '2026-09-14T00:00:00Z',
  issuer: 'atlas-deterministic-rules/v1',
  links: [{ rel: 'decide', href: '/api/v1/recommendations/recommendation-42/decisions' }],
}

beforeEach(() => {
  cacheInvalidate('decisions:')
  listGoals.mockReset().mockResolvedValue([{ id: 42, name: 'Retirement' }])
  getLatestForecastForGoal.mockReset().mockResolvedValue({ state: 'ready', goal_id: 42, forecast: { id: 'forecast-42' }, version: {} })
  getDerivedRecommendation.mockReset().mockResolvedValue(recommendation)
  postDecisionJournal.mockReset().mockResolvedValue({ action_taken: 'accept' })
  readSanitizedError.mockReset().mockReturnValue({ code: 'unknown', message: 'The decision could not be recorded. The recommendation remains unchanged.' })
})

describe('Decisions destination', () => {
  it('loads a goal-scoped derived recommendation and records an append-only action', async () => {
    render(<DecisionsPage />)
    expect(await screen.findByText('Increase contribution')).toBeInTheDocument()
    expect(getLatestForecastForGoal).toHaveBeenCalledWith(42)
    expect(getDerivedRecommendation).toHaveBeenCalledWith('forecast-42')
    fireEvent.click(screen.getByRole('button', { name: /accept for review/i }))
    await waitFor(() => expect(postDecisionJournal).toHaveBeenCalledWith('recommendation-42', { action: 'accept', decision_etag: 'forecast-etag-v1' }, 'idem-test'))
    expect(screen.getByText('Recorded: accept')).toBeInTheDocument()
  })

  it('renders a truthful unavailable state when the server-owned read gate is off', async () => {
    getLatestForecastForGoal.mockRejectedValue(new Error('disabled'))
    render(<DecisionsPage />)
    expect(await screen.findByText('Recommendations unavailable')).toBeInTheDocument()
    expect(screen.getByText(/did not make a current forecast/i)).toBeInTheDocument()
  })

  it('keeps journal write failures sanitized and does not render backend details', async () => {
    postDecisionJournal.mockRejectedValue(new Error('database secret'))
    readSanitizedError.mockReturnValue({ code: 'decision_version_conflict', message: 'The recommendation changed before the decision was recorded. Review it again.' })
    render(<DecisionsPage />)
    expect(await screen.findByText('Increase contribution')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /accept for review/i }))
    expect(await screen.findByText(/recommendation changed before/i)).toBeInTheDocument()
    expect(screen.queryByText(/database secret/i)).not.toBeInTheDocument()
  })
})
