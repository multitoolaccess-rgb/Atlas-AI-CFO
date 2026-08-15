import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import ReadinessSection from '../ReadinessSection'
import type { ReadinessResponse } from '@/lib/api'

const { getReadiness } = vi.hoisted(() => ({ getReadiness: vi.fn() }))
vi.mock('@/lib/api', () => ({
  rulesService: { getReadiness },
}))

afterEach(() => {
  vi.clearAllMocks()
})

const snapshot: ReadinessResponse = {
  schema_version: 'atlas-readiness/v1',
  overall_state: 'ready_with_blocked_optional_capabilities',
  checked_at: '2026-08-15T12:00:00Z',
  checks: [
    { component: 'runtime', state: 'ready', reason_code: 'runtime_ready', recovery_action: 'No action required.', last_checked: '2026-08-15T12:00:00Z', dependencies: { rules_service: true }, version: 'abc1234' },
    { component: 'financial_authority', state: 'blocked', reason_code: 'currency_evidence_missing', recovery_action: 'Resolve explicit USD evidence.', last_checked: '2026-08-15T12:00:00Z', dependencies: { account_currency_evidence: false } },
    { component: 'scenario_lab', state: 'disabled', reason_code: 'scenario_lab_disabled', recovery_action: 'Keep Scenario Lab disabled.', last_checked: '2026-08-15T12:00:00Z', dependencies: { server_flag: false } },
  ],
  feature_flags: { atlas_scenario_lab_enabled: false },
  credentials: { jwt_secret_configured: true, finnhub_api_key_present: false },
  prohibited_capabilities: { email: 'disabled', scheduler: 'disabled', llm: 'disabled', execution: 'disabled', trading: 'disabled', money_movement: 'disabled' },
}

describe('ReadinessSection', () => {
  beforeEach(() => {
    getReadiness.mockReset()
  })

  it('shows a truthful loading state', () => {
    getReadiness.mockReturnValue(new Promise(() => {}))
    render(<ReadinessSection />)
    expect(screen.getByRole('status')).toHaveTextContent(/checking local readiness/i)
  })

  it('renders server-owned ready, blocked, and disabled states without controls', async () => {
    getReadiness.mockResolvedValue(snapshot)
    render(<ReadinessSection />)
    expect(await screen.findByTestId('readiness-summary')).toBeInTheDocument()
    expect(screen.getByTestId('readiness-financial_authority')).toHaveTextContent(/blocked/i)
    expect(screen.getByTestId('readiness-scenario_lab')).toHaveTextContent(/disabled/i)
    expect(screen.getByRole('link', { name: /open help/i })).toHaveAttribute('href', '/help')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(getReadiness).toHaveBeenCalledTimes(1)
  })

  it('shows sanitized recovery when the readiness API fails', async () => {
    getReadiness.mockRejectedValue(new Error('JWT_SECRET=do-not-render'))
    render(<ReadinessSection />)
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByTestId('readiness-section')).not.toHaveTextContent('JWT_SECRET')
  })

  it('does not expose or call a feature-flag mutation path', async () => {
    getReadiness.mockResolvedValue(snapshot)
    render(<ReadinessSection />)
    await waitFor(() => expect(screen.getByTestId('readiness-boundaries')).toBeInTheDocument())
    expect(getReadiness).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('link', { name: /open help/i }))
    expect(getReadiness).toHaveBeenCalledTimes(1)
  })
})
