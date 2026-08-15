import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useRouter, useSearchParams } from 'next/navigation'

const { listGoals, listScenarios, generateScenario, readScenario, archiveScenario, compareScenarios, readScenarioError } = vi.hoisted(() => ({
  listGoals: vi.fn(),
  listScenarios: vi.fn(),
  generateScenario: vi.fn(),
  readScenario: vi.fn(),
  archiveScenario: vi.fn(),
  compareScenarios: vi.fn(),
  readScenarioError: vi.fn(),
}))

vi.mock('@/components/layout/PageLayout', () => ({ default: ({ children }: { children: unknown }) => <>{children}</> }))
vi.mock('@/components/ui/AtlasFilterContext', () => ({ AtlasFilterProvider: ({ children }: { children: unknown }) => <>{children}</> }))
vi.mock('@/lib/api', () => ({ rulesService: { listGoals } }))
vi.mock('@/lib/api_scenarios', () => ({ listScenarios, generateScenario, readScenario, archiveScenario, compareScenarios, readScenarioError }))

import { cacheInvalidate } from '@/lib/cache'
import ScenarioLabPage from '@/app/scenario-lab/page'

const scenario = {
  scenario_id: '11111111-1111-4111-8111-111111111111', goal_id: 42, version_number: 1,
  baseline_forecast_id: '22222222-2222-4222-8222-222222222222', baseline_version_number: 1,
  currency: 'USD', lifecycle_state: 'active' as const, created_at: '2026-08-14T00:00:00Z',
  ending_net_worth: '120000.00' as any, difference_from_baseline: '1000.00' as any, target_reached: true,
}

const comparison = {
  schema_version: 'atlas-scenario-comparison/v1' as const,
  baseline_forecast_id: scenario.baseline_forecast_id,
  baseline_version_number: 1,
  baseline_input_state_hash: 'a'.repeat(64), currency: 'USD',
  ending_net_worth: '120000.00' as any, difference_from_baseline: '1000.00' as any,
  target_amount: '150000.00' as any, target_gap: '30000.00' as any, target_reached: true,
  contribution_difference: '3000.00' as any, one_time_liquidity_consumed: '0.00' as any,
  deterministic_bands: Object.fromEntries(['conservative', 'base', 'optimistic'].map((band) => [band, {
    baseline_ending_net_worth: '119000.00', scenario_ending_net_worth: '120000.00', difference_from_baseline: '1000.00',
    baseline_target_reached: false, scenario_target_reached: true, baseline_target_gap: '31000.00', scenario_target_gap: '30000.00', target_amount: '150000.00',
  }])) as any,
  timing_impact: { contribution_start_date: null, contribution_stop_date: null, one_time_outflow_date: null, one_time_outflow_boundary_index: null },
  assumptions: { annual_return_rates: { conservative: '0.02', base: '0.04', optimistic: '0.06' }, annual_inflation_rate: '0.02', contribution_timing: 'end_of_month', period: 'monthly', rounding_rule: 'ROUND_HALF_EVEN', probability: false },
  source_freshness: { data_as_of: '2026-08-14', data_age_days: 0, max_data_age_days: 30 },
  warnings: ['Deterministic scenario bands are not probabilities or guarantees.'], limitations: ['USD-only synthetic fixture.'],
}

const envelope = {
  schema_version: 'atlas-scenario-envelope/v1' as const, scenario_id: scenario.scenario_id, version_id: '33333333-3333-4333-8333-333333333333', version_number: 1, goal_id: 42,
  baseline_forecast_id: scenario.baseline_forecast_id, baseline_version_number: 1, baseline_input_state_hash: 'a'.repeat(64), scenario_input_hash: 'b'.repeat(64), model_version: 'model-v1', calculation_version: 'calc-v1', currency: 'USD', lifecycle_state: 'active' as const, created_at: scenario.created_at,
  input: { schema_version: 'atlas-scenario-lab/v1' as const, baseline_forecast_id: scenario.baseline_forecast_id, baseline_version_number: 1, baseline_input_state_hash: 'a'.repeat(64), scenario: { monthly_contribution_delta: '250.00' } },
  result: { schema_version: 'atlas-scenario-lab/v1' as const, model_version: 'model-v1', calculation_version: 'calc-v1', currency: 'USD', scenario_input_hash: 'b'.repeat(64), canonical_inputs: { monthly_contribution_delta: '250.00' }, deterministic_bands: {} as any, source_freshness: comparison.source_freshness, assumptions: comparison.assumptions },
  comparison, recommendation_reference: null, etag: 'etag-1',
}

let query = new URLSearchParams()
const replace = vi.fn()

beforeEach(() => {
  cacheInvalidate('scenario-lab:')
  query = new URLSearchParams()
  replace.mockReset(); replace.mockImplementation((next: string) => { query = new URLSearchParams(next.replace(/^\?/, '')) })
  vi.mocked(useSearchParams).mockImplementation(() => query as any)
  vi.mocked(useRouter).mockImplementation(() => ({ replace, push: vi.fn(), prefetch: vi.fn() }) as any)
  listGoals.mockReset().mockResolvedValue([{ id: 42, name: 'Retirement' }])
  listScenarios.mockReset().mockResolvedValue({ schema_version: 'atlas-scenario-list/v1', items: [scenario], next_cursor: null })
  generateScenario.mockReset().mockResolvedValue(envelope)
  readScenario.mockReset().mockResolvedValue(envelope)
  archiveScenario.mockReset().mockResolvedValue({ schema_version: 'atlas-scenario-archive/v1', scenario_id: scenario.scenario_id, lifecycle_state: 'archived', archived_at: '2026-08-14T00:00:00Z' })
  compareScenarios.mockReset().mockResolvedValue({ schema_version: 'atlas-scenario-comparison-set/v1', baseline_forecast_id: scenario.baseline_forecast_id, baseline_version_number: 1, scenarios: [{ scenario_id: scenario.scenario_id, version_number: 1, comparison }] })
  readScenarioError.mockReset().mockImplementation(() => ({ code: 'unknown', message: 'Scenario Lab could not complete that request. No client-side result was calculated.', recovery: 'Retry when the service is available.' }))
})

describe('Scenario Lab destination', () => {
  it('sends bounded Decimal input with one stable idempotency key and renders server values', async () => {
    render(<ScenarioLabPage />)
    expect(await screen.findByText('Build one bounded change')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Monthly contribution change'), { target: { value: '250.00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generate scenario' }))
    await waitFor(() => expect(generateScenario).toHaveBeenCalledWith(42, { monthly_contribution_delta: '250.00' }, expect.any(String)))
    expect(await screen.findByText('What this change means against the baseline')).toBeInTheDocument()
    expect(screen.getByText(/browser does not calculate projections/i)).toBeInTheDocument()
    const key = generateScenario.mock.calls[0][2]
    fireEvent.click(screen.getByRole('button', { name: 'Generate scenario' }))
    await waitFor(() => expect(generateScenario).toHaveBeenCalledTimes(2))
    expect(generateScenario.mock.calls[1][2]).not.toBe(key)
  })

  it('reuses the same idempotency key for a retry of the same failed intent', async () => {
    generateScenario.mockRejectedValueOnce(new Error('transient')).mockResolvedValueOnce(envelope)
    render(<ScenarioLabPage />)
    await screen.findByText('Build one bounded change')
    fireEvent.change(screen.getByLabelText('Monthly contribution change'), { target: { value: '250.00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generate scenario' }))
    await waitFor(() => expect(generateScenario).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('button', { name: 'Generate scenario' }))
    await waitFor(() => expect(generateScenario).toHaveBeenCalledTimes(2))
    expect(generateScenario.mock.calls[1][2]).toBe(generateScenario.mock.calls[0][2])
  })

  it('requires explicit comparison selection and supports archive without raw JSON', async () => {
    const view = render(<ScenarioLabPage />)
    await screen.findByText('Build one bounded change')
    fireEvent.click(screen.getByText('Archive')); view.rerender(<ScenarioLabPage />)
    expect(await screen.findByRole('heading', { name: 'Immutable scenario history' })).toBeInTheDocument()
    fireEvent.click(within(screen.getByRole('list', { name: 'Saved scenarios' })).getAllByRole('button')[0])
    fireEvent.click(screen.getByRole('button', { name: /Archive scenario/i }))
    await waitFor(() => expect(archiveScenario).toHaveBeenCalledWith(scenario.scenario_id, expect.any(String)))

    fireEvent.click(screen.getByText('Comparisons')); view.rerender(<ScenarioLabPage />)
    expect(await screen.findByRole('heading', { name: 'Compare saved scenarios' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Compare selected scenarios' })).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Compare selected scenarios' }))
    await waitFor(() => expect(compareScenarios).toHaveBeenCalledWith([scenario.scenario_id]))
    expect(screen.getByRole('table', { name: /selected Scenario Lab comparison/i })).toBeInTheDocument()
    expect(screen.queryByText(/"ending_net_worth"/)).not.toBeInTheDocument()
  })

  it('shows a sanitized unavailable state and does not fabricate a local scenario', async () => {
    listScenarios.mockRejectedValue(new Error('service disabled'))
    render(<ScenarioLabPage />)
    expect(await screen.findByText('Scenario Lab could not complete that request. No client-side result was calculated.')).toBeInTheDocument()
    expect(screen.getByText(/retry when the service is available/i)).toBeInTheDocument()
  })
})
