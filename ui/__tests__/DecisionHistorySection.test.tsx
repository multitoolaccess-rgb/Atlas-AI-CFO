import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getDecisionHistory } = vi.hoisted(() => ({ getDecisionHistory: vi.fn() }))
vi.mock('@/lib/api_phase4', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api_phase4')>()),
  getDecisionHistory,
  readDecisionHistoryError: (error: { response?: { data?: { code?: string } } }) =>
    error.response?.data?.code === 'decision_history_unavailable' ? 'unavailable' : 'error',
}))

import DecisionHistorySection from '@/components/dashboard/DecisionHistorySection'

const goals = [{ id: 42, name: 'Retirement by 55' }]

describe('DecisionHistorySection', () => {
  beforeEach(() => getDecisionHistory.mockReset())

  it('renders chronological, privacy-safe history with disclosure and lifecycle labels', async () => {
    getDecisionHistory.mockResolvedValue({
      schema_version: 'atlas-decision-history-envelope/v1',
      history: [
        { history_id: 'secret-id', recommendation_id: 'secret-rec', decision_id: 'secret-decision', decision_action: 'accept', alternatives: ['do_nothing', 'defer'], rationale: 'A contribution now keeps the plan on course.', supersedes_history_id: null, recorded_at: '2026-08-01T10:00:00Z', audit: null, outcome_lifecycles: ['not_yet_measurable'] },
        { history_id: 'secret-id-2', recommendation_id: 'secret-rec-2', decision_id: 'secret-decision-2', decision_action: 'defer', alternatives: ['accept'], rationale: 'Waiting for the next income review.', supersedes_history_id: 'secret-id', recorded_at: '2026-08-02T10:00:00Z', audit: null, outcome_lifecycles: ['pending', 'measured'] },
        { history_id: 'secret-id-3', recommendation_id: 'secret-rec-3', decision_id: 'secret-decision-3', decision_action: 'reject', alternatives: ['do_nothing'], rationale: 'Pending correction is awaiting measurement.', supersedes_history_id: null, recorded_at: '2026-08-03T10:00:00Z', audit: null, outcome_lifecycles: ['measured', 'pending'] },
      ],
    })

    render(<DecisionHistorySection goals={goals} />)

    expect(await screen.findByText('Decision history')).toBeInTheDocument()
    const items = screen.getByRole('list', { name: /retirement by 55 decision history/i }).querySelectorAll(':scope > li')
    expect(items[0]).toHaveTextContent('Accepted')
    expect(items[0]).toHaveTextContent('Not yet measurable')
    expect(items[1]).toHaveTextContent('Deferred')
    expect(items[1]).toHaveTextContent('Measured')
    expect(items[1]).toHaveTextContent('Corrects an earlier decision')
    expect(items[2]).toHaveTextContent('Pending measurement')
    expect(items[2]).not.toHaveTextContent('Measured')
    expect(screen.queryByText('A contribution now keeps the plan on course.')).not.toBeVisible()
    const disclosure = screen.getAllByText('View rationale and alternatives')[0]
    disclosure.focus()
    expect(disclosure).toHaveFocus()
    fireEvent.click(disclosure)
    expect(screen.getByText('A contribution now keeps the plan on course.')).toBeVisible()
    expect(screen.getAllByText('Alternatives considered')[0]).toBeVisible()
    expect(screen.getAllByText('Keep the current plan')[0]).toBeVisible()
    expect(screen.getByText(/Recorded acceptance is approval only/)).toBeInTheDocument()
    expect(screen.queryByText(/secret-id|secret-rec|secret-decision/i)).not.toBeInTheDocument()
  })

  it('renders loading and empty states', async () => {
    let resolve: (value: unknown) => void = () => {}
    getDecisionHistory.mockReturnValue(new Promise((done) => { resolve = done }))
    render(<DecisionHistorySection goals={goals} />)
    expect(screen.getByText('Loading decision history…')).toBeInTheDocument()
    resolve({ schema_version: 'atlas-decision-history-envelope/v1', history: [] })
    await waitFor(() => expect(screen.getByText('No decisions have been recorded for this goal yet.')).toBeInTheDocument())
  })

  it('offers an accessible retry that reloads a recoverable history error', async () => {
    const unavailable = Object.assign(new Error('request failed'), {
      response: { data: { code: 'decision_history_unavailable' } },
    })
    getDecisionHistory
      .mockRejectedValueOnce(unavailable)
      .mockResolvedValueOnce({ schema_version: 'atlas-decision-history-envelope/v1', history: [] })
    render(<DecisionHistorySection goals={goals} />)
    const retry = await screen.findByRole('button', { name: 'Retry decision history' })
    fireEvent.click(retry)
    await waitFor(() => expect(screen.getByText('No decisions have been recorded for this goal yet.')).toBeInTheDocument())
    expect(getDecisionHistory).toHaveBeenCalledTimes(2)
  })
})
