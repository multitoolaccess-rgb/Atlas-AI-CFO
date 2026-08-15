import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSearchParams } from 'next/navigation'

const { listGoals, getLatestForecastForGoal, getDerivedRecommendationResource, postDecisionJournal, readSanitizedError, getDecisionHistoryForGoals, recordDecisionHistory } = vi.hoisted(() => ({
  listGoals: vi.fn(),
  getLatestForecastForGoal: vi.fn(),
  getDerivedRecommendationResource: vi.fn(),
  postDecisionJournal: vi.fn(),
  readSanitizedError: vi.fn(),
  getDecisionHistoryForGoals: vi.fn(),
  recordDecisionHistory: vi.fn(),
}))

vi.mock('@/components/layout/PageLayout', () => ({ default: ({ children }: { children: unknown }) => <>{children}</> }))
vi.mock('@/components/ui/AtlasFilterContext', () => ({ AtlasFilterProvider: ({ children }: { children: unknown }) => <>{children}</> }))
vi.mock('@/components/dashboard/DecisionHistorySection', () => ({ default: ({ snapshot }: { snapshot?: { historyByGoal: Record<number, unknown[]> } }) => <div data-testid="decision-history-stub" data-history-count={snapshot?.historyByGoal[42]?.length ?? 0} /> }))
vi.mock('@/lib/api', () => ({ rulesService: { listGoals } }))
vi.mock('@/lib/api_phase2', () => ({
  getLatestForecastForGoal,
  getDerivedRecommendationResource,
  postDecisionJournal,
  mintIdempotencyKey: () => 'idem-test',
  readSanitizedError,
}))
vi.mock('@/lib/api_phase4', () => ({ getDecisionHistoryForGoals, recordDecisionHistory }))

import { cacheInvalidate } from '@/lib/cache'
import DecisionsPage from '@/app/decisions/page'

const decisionEtag = 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-d1'
const recommendation = {
  schema_version: 'atlas-derived-recommendation/v1',
  recommendation_kind: 'increase_contribution',
  action_verb: 'Increase contribution',
  why_now: 'Current evidence supports a review of the monthly contribution.',
  linked_goal_id: 42,
  forecast_id: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa',
  forecast_etag: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-v1',
  evidence_references: { forecast_id: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa', model_version: 'model', calculation_version: 'calc', input_state_hash: 'a'.repeat(64), data_as_of: '2026-08-14T00:00:00Z' },
  expected_impact_range: { min_delta_decimal: '100.00', max_delta_decimal: '250.00' },
  risks: ['reversibility_required'],
  confidence: 'medium',
  assumptions_reference: 'b'.repeat(64),
  expiration: '2026-09-14T00:00:00Z',
  issuer: 'atlas-deterministic-rules/v1',
  links: [{ rel: 'decide', href: '/api/v1/recommendations/recommendation-42/decisions' }],
}

const emptyHistory = { historyByGoal: { 42: [] }, unavailableGoalIds: [] }
const recordedHistory = {
  historyByGoal: {
    42: [{
      history_id: 'history-42',
      recommendation_id: 'recommendation-42',
      decision_id: 'journal-42',
      decision_action: 'accept',
      alternatives: ['do_nothing', 'accept'],
      rationale: recommendation.why_now,
      supersedes_history_id: null,
      recorded_at: '2026-08-14T00:00:00Z',
      audit: null,
      outcome_lifecycles: ['pending'],
    }],
  },
  unavailableGoalIds: [],
}

beforeEach(() => {
  cacheInvalidate('decisions:')
  cacheInvalidate('decision-history:')
  vi.mocked(useSearchParams).mockReturnValue(new URLSearchParams() as never)
  listGoals.mockReset().mockResolvedValue([{ id: 42, name: 'Retirement' }])
  getLatestForecastForGoal.mockReset().mockResolvedValue({ state: 'ready', goal_id: 42, forecast: { id: recommendation.forecast_id }, version: {} })
  getDerivedRecommendationResource.mockReset().mockResolvedValue({ recommendation, decisionEtag })
  postDecisionJournal.mockReset().mockResolvedValue({ journal_entry_id: 'journal-42', recommendation_id: 'recommendation-42', action_taken: 'accept', decision_etag: 'journal-etag', decided_at: '2026-08-14T00:00:00Z', links: [] })
  getDecisionHistoryForGoals.mockReset().mockResolvedValue(emptyHistory)
  recordDecisionHistory.mockReset().mockResolvedValue({ history_id: 'history-42', decision_action: 'accept', recorded_at: '2026-08-14T00:00:00Z', replayed: false })
  readSanitizedError.mockReset().mockReturnValue({ code: 'unknown', message: 'The decision could not be recorded. The recommendation remains unchanged.' })
})

describe('Decisions destination', () => {
  it('uses the authoritative decision ETag and persists the journal into server-backed history', async () => {
    render(<DecisionsPage />)
    expect(await screen.findByText('Increase contribution')).toBeInTheDocument()
    expect(getDerivedRecommendationResource).toHaveBeenCalledWith(recommendation.forecast_id)
    fireEvent.click(screen.getByRole('button', { name: /accept for review/i }))
    await waitFor(() => expect(postDecisionJournal).toHaveBeenCalledWith('recommendation-42', { action: 'accept', decision_etag: decisionEtag }, 'idem-test'))
    await waitFor(() => expect(recordDecisionHistory).toHaveBeenCalledWith(42, {
      recommendation_id: 'recommendation-42',
      decision_journal_entry_id: 'journal-42',
      alternatives: ['do_nothing', 'accept'],
      rationale: recommendation.why_now,
    }, 'history-journal-42'))
    expect(screen.getByText('Recorded: accept')).toBeInTheDocument()
  })

  it('loads persisted history on remount and does not reconstruct it from local state', async () => {
    getDecisionHistoryForGoals.mockResolvedValue(recordedHistory)
    vi.mocked(useSearchParams).mockReturnValue(new URLSearchParams('view=journal') as never)
    render(<DecisionsPage />)
    expect(await screen.findByTestId('decision-history-stub')).toHaveAttribute('data-history-count', '1')
    expect(screen.getByText('Approval is not execution')).toBeInTheDocument()
  })

  it('fails safely when authoritative history is unavailable', async () => {
    getDecisionHistoryForGoals.mockResolvedValue({ historyByGoal: { 42: [] }, unavailableGoalIds: [42] })
    render(<DecisionsPage />)
    expect(await screen.findByText(/decision history is unavailable/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /accept for review/i })).not.toBeInTheDocument()
    expect(recordDecisionHistory).not.toHaveBeenCalled()
  })

  it('keeps stale decision conflicts visible and sanitized', async () => {
    postDecisionJournal.mockRejectedValue(new Error('database secret'))
    readSanitizedError.mockReturnValue({ code: 'decision_version_conflict', message: 'The recommendation changed before the decision was recorded. Review it again.' })
    render(<DecisionsPage />)
    expect(await screen.findByText('Increase contribution')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /accept for review/i }))
    expect(await screen.findByText(/recommendation changed before/i)).toBeInTheDocument()
    expect(screen.queryByText(/database secret|a{64}/i)).not.toBeInTheDocument()
    expect(recordDecisionHistory).not.toHaveBeenCalled()
  })

  it('keeps journal/history linkage idempotent when the history write replays', async () => {
    recordDecisionHistory.mockResolvedValue({ history_id: 'history-42', decision_action: 'accept', recorded_at: '2026-08-14T00:00:00Z', replayed: true })
    render(<DecisionsPage />)
    expect(await screen.findByText('Increase contribution')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /accept for review/i }))
    await waitFor(() => expect(recordDecisionHistory).toHaveBeenCalledTimes(1))
    expect(recordDecisionHistory.mock.calls[0]?.[2]).toBe('history-journal-42')
  })
})
