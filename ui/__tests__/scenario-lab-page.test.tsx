import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useRouter, useSearchParams } from 'next/navigation'

const { listGoals, listScenarios, generateScenario, archiveScenario, compareScenarios, readScenarioError } = vi.hoisted(() => ({
  listGoals: vi.fn(),
  listScenarios: vi.fn(),
  generateScenario: vi.fn(),
  archiveScenario: vi.fn(),
  compareScenarios: vi.fn(),
  readScenarioError: vi.fn(),
}))

vi.mock('@/components/layout/PageLayout', () => ({ default: ({ children }: { children: unknown }) => <>{children}</> }))
vi.mock('@/components/ui/AtlasFilterContext', () => ({ AtlasFilterProvider: ({ children }: { children: unknown }) => <>{children}</> }))
vi.mock('@/lib/api', () => ({ rulesService: { listGoals } }))
vi.mock('@/lib/api_scenarios', () => ({ listScenarios, generateScenario, archiveScenario, compareScenarios, readScenarioError }))

import { cacheInvalidate } from '@/lib/cache'
import ScenarioLabPage from '@/app/scenario-lab/page'

const scenario = {
  scenario_id: 'scenario-1',
  goal_id: 42,
  version_number: 1,
  baseline_forecast_id: 'baseline-1',
  baseline_version_number: 1,
  currency: 'USD',
  lifecycle_state: 'active' as const,
  created_at: '2026-08-14T00:00:00Z',
  ending_net_worth: '120000.00',
  difference_from_baseline: '1000.00',
  target_reached: true,
}

const envelope = {
  schema_version: 'atlas-scenario-envelope/v1',
  scenario_id: 'scenario-1',
  version_id: 'version-1',
  version_number: 1,
  goal_id: 42,
  baseline_forecast_id: 'baseline-1',
  baseline_version_number: 1,
  baseline_input_state_hash: 'baseline-hash',
  scenario_input_hash: 'scenario-hash',
  model_version: 'model-v1',
  calculation_version: 'calc-v1',
  currency: 'USD',
  lifecycle_state: 'active' as const,
  created_at: '2026-08-14T00:00:00Z',
  input: { monthly_contribution_delta: '250.00' },
  result: {},
  comparison: { ending_net_worth: '120000.00', difference_from_baseline: '1000.00' },
  recommendation_reference: null,
  etag: 'etag-1',
}

let query = new URLSearchParams()
const replace = vi.fn()

beforeEach(() => {
  cacheInvalidate('scenario-lab:')
  query = new URLSearchParams()
  replace.mockReset()
  replace.mockImplementation((next: string) => { query = new URLSearchParams(next.replace(/^\?/, '')) })
  vi.mocked(useSearchParams).mockImplementation(() => query as any)
  vi.mocked(useRouter).mockImplementation(() => ({ replace, push: vi.fn(), prefetch: vi.fn() }) as any)
  listGoals.mockReset().mockResolvedValue([{ id: 42, name: 'Retirement' }])
  listScenarios.mockReset().mockResolvedValue({ schema_version: 'atlas-scenario-list/v1', items: [scenario], next_cursor: null })
  generateScenario.mockReset().mockResolvedValue(envelope)
  archiveScenario.mockReset().mockResolvedValue({ scenario_id: 'scenario-1', lifecycle_state: 'archived', archived_at: '2026-08-14T00:00:00Z' })
  compareScenarios.mockReset().mockResolvedValue({ schema_version: 'atlas-scenario-comparison-set/v1', baseline_forecast_id: 'baseline-1', baseline_version_number: 1, scenarios: [{ scenario_id: 'scenario-1', version_number: 1, comparison: envelope.comparison }] })
  readScenarioError.mockReset().mockReturnValue({ code: 'unknown', message: 'Scenario Lab is unavailable or the requested scenario could not be loaded. No client-side result was calculated.' })
})

describe('Scenario Lab destination', () => {
  it('is goal-scoped and sends bounded Decimal input to the authoritative server', async () => {
    render(<ScenarioLabPage />)
    expect(await screen.findByText('Create a bounded scenario')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Monthly contribution change'), { target: { value: '250.00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generate scenario' }))
    await waitFor(() => expect(generateScenario).toHaveBeenCalledWith(42, { monthly_contribution_delta: '250.00' }, expect.any(String)))
    expect(await screen.findByText('Authoritative server result')).toBeInTheDocument()
    expect(screen.getByText(/browser performed no financial calculation/i)).toBeInTheDocument()
  })

  it('supports archive and bounded comparison views without client-side results', async () => {
    const view = render(<ScenarioLabPage />)
    await screen.findByText('Create a bounded scenario')
    fireEvent.click(screen.getByText('Archive'))
    view.rerender(<ScenarioLabPage />)
    expect(await screen.findByRole('heading', { name: 'Scenario archive' })).toBeInTheDocument()
    const archiveList = screen.getByRole('list', { name: 'Saved scenarios' })
    fireEvent.click(within(archiveList).getByRole('button'))
    fireEvent.click(screen.getByRole('button', { name: /archive selected scenario/i }))
    await waitFor(() => expect(archiveScenario).toHaveBeenCalledWith('scenario-1', expect.any(String)))

    fireEvent.click(screen.getByText('Comparisons'))
    view.rerender(<ScenarioLabPage />)
    fireEvent.click(screen.getByRole('button', { name: 'Compare saved scenarios' }))
    await waitFor(() => expect(compareScenarios).toHaveBeenCalledWith(['scenario-1']))
    expect(screen.getByText(/ending_net_worth/)).toBeInTheDocument()
  })

  it('shows the server-unavailable state and does not fabricate a local scenario', async () => {
    listScenarios.mockRejectedValue(new Error('service disabled'))
    render(<ScenarioLabPage />)
    expect(await screen.findByText('Scenario history unavailable')).toBeInTheDocument()
    expect(screen.getByText(/no local scenario result is shown/i)).toBeInTheDocument()
  })
})
