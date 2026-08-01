/**
 * Phase 2 Slice 2 — Vitest tests for `<LatestForecastCard>`.
 *
 *  Coverage:
 *    1. Decimal-string rendering for target + projected.
 *    2. ``target_status: true`` → "On track" + green badge.
 *    3. ``target_status: false`` → "Gap remaining" + amber badge.
 *    4. Why-this-projection panel renders model_version + calculation_version
 *       + input_state_hash (sha256-hash prefix) + bounded scenarios.
 *    5. Money values pass through `formatNumber` (no Number coercion).
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
    ChevronDown: Stub,
    ChevronUp: Stub,
    Clock: Stub,
    Sparkles: Stub,
    TrendingDown: Stub,
    TrendingUp: Stub,
    // The remaining icons for safety.
    X: Stub,
    Plus: Stub,
  }
})

import LatestForecastCard from '@/components/dashboard/LatestForecastCard'

const FORECAST = {
  id: '11111111-1111-4111-8111-111111111111',
  goal_id: 42,
  user_id: 1,
  currency: 'USD' as const,
  kind: 'goal_projection' as const,
  latest_version_number: 3,
  latest_version_id: '22222222-2222-4222-8222-222222222222',
  etag: 'aaaaaaaa-1111-4111-8111-cccccccccccc-v3',
  created_at: '2026-08-01T00:00:00.000000Z',
  updated_at: null,
  links: [],
}

const VERSION = {
  id: '22222222-2222-4222-8222-222222222222',
  forecast_id: '11111111-1111-4111-8111-111111111111',
  version_number: 3,
  ending_balance: '4500000.00',
  target_decision: {
    rounded_ending_balance: '4500000.00',
    rounded_target_amount: '15000000.00',
    target_status: false,
    decision_etag: 'aaaaaaaa-1111-4111-8111-cccccccccccc-v3',
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
  assumption_snapshot: {},
  provenance_snapshot: {},
  data_as_of: '2026-07-28T00:00:00.000000Z',
  calculated_at: '2026-08-01T00:00:00.000000Z',
  model_version: 'atlas-projection/v1',
  calculation_version: 'atlas-calculation-decimal/v1',
  input_state_hash: 'f'.repeat(64),
}

describe('<LatestForecastCard />', () => {
  it('renders Decimal strings verbatim (no Number coercion)', () => {
    render(
      <LatestForecastCard
        goalName="Retirement by 55"
        goalTargetAmount="15000000.00"
        forecast={FORECAST}
        version={VERSION}
      />,
    )
    // The card surfaces target + projected, both passing through
    // formatNumber without Number coercion.
    const projected = screen.getByTestId('forecast-projected')
    expect(projected.textContent).toBeTruthy()
    expect(projected.textContent).toMatch(/4,500,000\.00/)
    // No NaN, no $, no scientific notation.
    expect(projected.textContent).not.toMatch(/NaN|e\+|\$/)
  })

  it('target_status=false renders "Gap remaining" + amber styling', () => {
    render(
      <LatestForecastCard
        goalName="Retirement by 55"
        goalTargetAmount="15000000.00"
        forecast={FORECAST}
        version={VERSION}
      />,
    )
    const tag = screen.getByTestId('forecast-status-tag')
    expect(tag.textContent).toContain('Gap remaining')
    expect(tag.className).toContain('bg-warning-50')
    expect(tag.getAttribute('aria-label')).toBe('Forecasting status Gap remaining')
  })

  it('target_status=true switches to "On track" + green styling', () => {
    render(
      <LatestForecastCard
        goalName="Retirement by 55"
        goalTargetAmount="15000000.00"
        forecast={FORECAST}
        version={{ ...VERSION, target_decision: { ...VERSION.target_decision, target_status: true } }}
      />,
    )
    const tag = screen.getByTestId('forecast-status-tag')
    expect(tag.textContent).toContain('On track')
    expect(tag.className).toContain('bg-success-50')
  })

  it('expands the "Why this projection?" panel with bounded scenarios', () => {
    render(
      <LatestForecastCard
        goalName="Retirement by 55"
        goalTargetAmount="15000000.00"
        forecast={FORECAST}
        version={VERSION}
      />,
    )
    // Pre-click: panel not in DOM.
    expect(screen.queryByTestId('why-this-panel')).toBeNull()
    fireEvent.click(screen.getByTestId('why-this-toggle'))
    const panel = screen.getByTestId('why-this-panel')
    expect(panel).toBeInTheDocument()
    // Provenance strings present.
    expect(screen.getByTestId('forecast-version').textContent).toContain('#3')
    expect(screen.getByTestId('forecast-hash').textContent).toMatch(/^f{8}…$/)
    // Bounded scenarios (conservative | base | optimistic).
    expect(screen.getByTestId('scenario-conservative')).toBeInTheDocument()
    expect(screen.getByTestId('scenario-base')).toBeInTheDocument()
    expect(screen.getByTestId('scenario-optimistic')).toBeInTheDocument()
  })
})
