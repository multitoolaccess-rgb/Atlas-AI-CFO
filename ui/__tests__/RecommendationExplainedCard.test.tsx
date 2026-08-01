/**
 * Phase 2 Slice 2 — Vitest tests for `<RecommendationExplainedCard>`.
 *
 *  Coverage:
 *    1. Action verb renders verbatim (e.g. "Increase").
 *    2. Accept/Reject/Defer buttons fire the correct action token + carry
 *       the bare ``decision_etag`` from the rec payload.
 *    3. aria-label uses the bounded ``<verb> recommendation`` form — NO
 *       "Approve" stringification (mirrors the plan §5 decision).
 *    4. Expected impact renders Decimal-string min/max through
 *       ``formatNumber`` (no Number coercion).
 *    5. When ``recordedEntry`` is provided, the card flips to a
 *       non-interactive "Recorded" state with the journal entry id.
 *    6. While ``busy`` is true, the three buttons are disabled.
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('lucide-react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('lucide-react')>()
  const Stub = (props: { className?: string; 'aria-hidden'?: boolean }) => (
    <svg
      data-testid="icon"
      className={props.className}
      aria-hidden={props['aria-hidden']}
    />
  )
  return {
    ...actual,
    Check: Stub,
    ChevronDown: Stub,
    ChevronUp: Stub,
    Clock: Stub,
    Loader2: Stub,
    Shield: Stub,
    Sparkles: Stub,
    X: Stub,
  }
})

import RecommendationExplainedCard from '@/components/dashboard/RecommendationExplainedCard'

const RECOMMENDATION = {
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
    input_state_hash: 'b'.repeat(64),
    data_as_of: '2026-07-28T00:00:00.000000Z',
  },
  expected_impact_range: {
    min_delta_decimal: '12000.00',
    max_delta_decimal: '32000.00',
  },
  risks: ['liquidity_reduction' as const],
  confidence: 'medium' as const,
  assumptions_reference: 'c'.repeat(64),
  expiration: '2026-08-02T00:00:00.000000Z',
  issuer: 'atlas-deterministic-rules/v1' as const,
  links: [],
}

describe('<RecommendationExplainedCard />', () => {
  it('renders action verb + why_now + impact range (Decimal string)', () => {
    render(
      <RecommendationExplainedCard
        recommendation={RECOMMENDATION}
        sourceVersionNumber={3}
        sourceCalculatedAt={RECOMMENDATION.expiration}
        sourceDataAgeDays={4}
        onDecide={() => {}}
      />,
    )
    expect(screen.getByTestId('action-verb').textContent).toBe('Increase')
    expect(screen.getByTestId('why-now').textContent).toContain(
      '10.5M short',
    )
    const impact = screen.getByTestId('impact-range')
    expect(impact.textContent).toMatch(/12,000\.00/)
    expect(impact.textContent).toMatch(/32,000\.00/)
    // No Number coercion.
    expect(impact.textContent).not.toMatch(/NaN|e\+|\$/)
  })

  it('Accept button fires the ``accept`` action + carries decision_etag', () => {
    const onDecide = vi.fn()
    render(
      <RecommendationExplainedCard
        recommendation={RECOMMENDATION}
        sourceVersionNumber={3}
        sourceCalculatedAt={RECOMMENDATION.expiration}
        sourceDataAgeDays={4}
        onDecide={onDecide}
      />,
    )
    fireEvent.click(screen.getByTestId('rec-accept'))
    expect(onDecide).toHaveBeenCalledTimes(1)
    expect(onDecide).toHaveBeenCalledWith('accept', RECOMMENDATION)
  })

  it('Reject + Defer buttons fire their bounded tokens', () => {
    const onDecide = vi.fn()
    render(
      <RecommendationExplainedCard
        recommendation={RECOMMENDATION}
        sourceVersionNumber={3}
        sourceCalculatedAt={RECOMMENDATION.expiration}
        sourceDataAgeDays={4}
        onDecide={onDecide}
      />,
    )
    fireEvent.click(screen.getByTestId('rec-reject'))
    fireEvent.click(screen.getByTestId('rec-defer'))
    expect(onDecide).toHaveBeenNthCalledWith(1, 'reject', RECOMMENDATION)
    expect(onDecide).toHaveBeenNthCalledWith(2, 'defer', RECOMMENDATION)
  })

  it('aria-label uses bounded "<verb> recommendation" form (NO "Approve" string)', () => {
    render(
      <RecommendationExplainedCard
        recommendation={RECOMMENDATION}
        sourceVersionNumber={3}
        sourceCalculatedAt={RECOMMENDATION.expiration}
        sourceDataAgeDays={4}
        onDecide={() => {}}
      />,
    )
    expect(screen.getByTestId('rec-accept').getAttribute('aria-label')).toBe('Accept recommendation')
    expect(screen.getByTestId('rec-reject').getAttribute('aria-label')).toBe('Reject recommendation')
    expect(screen.getByTestId('rec-defer').getAttribute('aria-label')).toBe('Defer recommendation')
    // The literal "Approve" string MUST NOT appear in any user-visible
    // aria-label or button label (plan §5 disambiguation).
    expect(screen.getByTestId('rec-accept').getAttribute('aria-label')).not.toMatch(/approve/i)
    expect(screen.getByTestId('rec-reject').getAttribute('aria-label')).not.toMatch(/approve/i)
    expect(screen.getByTestId('rec-defer').getAttribute('aria-label')).not.toMatch(/approve/i)
    expect(screen.getByTestId('rec-accept').textContent).not.toMatch(/approve/i)
  })

  it('flips to "Recorded" non-interactive state when ``recordedEntry`` is set', () => {
    const recordedEntry = {
      schema_version: 'atlas-decision-journal-entry/v1' as const,
      journal_entry_id: '33333333-3333-4333-8333-333333333333',
      recommendation_id: RECOMMENDATION.forecast_id,
      action_taken: 'accept' as const,
      decided_at: '2026-08-01T00:01:00.000000Z',
      decision_etag: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-d1',
      links: [],
    }
    render(
      <RecommendationExplainedCard
        recommendation={RECOMMENDATION}
        sourceVersionNumber={3}
        sourceCalculatedAt={RECOMMENDATION.expiration}
        sourceDataAgeDays={4}
        onDecide={() => {}}
        recordedEntry={recordedEntry}
      />,
    )
    // Accept/Reject/Defer buttons no longer present.
    expect(screen.queryByTestId('rec-accept')).toBeNull()
    expect(screen.queryByTestId('rec-reject')).toBeNull()
    expect(screen.queryByTestId('rec-defer')).toBeNull()
    // Recorded.
    expect(screen.getByTestId('recorded-journal-id').textContent).toBe(
      '33333333-3333-4333-8333-333333333333',
    )
    expect(screen.getByTestId('recorded-decided-at').textContent).toContain('2026-08-01')
  })

  it('disables all action buttons while ``busy`` is true', () => {
    render(
      <RecommendationExplainedCard
        recommendation={RECOMMENDATION}
        sourceVersionNumber={3}
        sourceCalculatedAt={RECOMMENDATION.expiration}
        sourceDataAgeDays={4}
        onDecide={() => {}}
        busy={true}
      />,
    )
    expect(screen.getByTestId('rec-accept')).toBeDisabled()
    expect(screen.getByTestId('rec-reject')).toBeDisabled()
    expect(screen.getByTestId('rec-defer')).toBeDisabled()
  })

  it('renders Confidence tag with the bounded enum string', () => {
    render(
      <RecommendationExplainedCard
        recommendation={RECOMMENDATION}
        sourceVersionNumber={3}
        sourceCalculatedAt={RECOMMENDATION.expiration}
        sourceDataAgeDays={4}
        onDecide={() => {}}
      />,
    )
    const conf = screen.getByTestId('confidence-tag')
    expect(conf.textContent).toMatch(/Medium confidence/i)
  })

  it('renders bounded risk labels (liquidity_reduction → "Liquidity reduction")', () => {
    render(
      <RecommendationExplainedCard
        recommendation={RECOMMENDATION}
        sourceVersionNumber={3}
        sourceCalculatedAt={RECOMMENDATION.expiration}
        sourceDataAgeDays={4}
        onDecide={() => {}}
      />,
    )
    expect(screen.getByTestId('risk-liquidity_reduction').textContent).toContain(
      'Liquidity reduction',
    )
  })
})
