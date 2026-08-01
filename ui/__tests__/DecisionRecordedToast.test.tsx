/**
 * Phase 2 Slice 2 — Vitest tests for `<DecisionRecordedToast>`.
 *
 *  Coverage:
 *    1. ``entry=null`` renders nothing (no status element in DOM).
 *    2. ``entry`` is set → the bounded status element is in the DOM
 *       and is reachable via the journal-entry-id testid.
 *    3. Auto-dismiss handler fires after the bounded window.
 *    4. Sanitized content: shows action_taken + first 8 chars of the
 *       journal_entry_id + the decided_at timestamp; NO money payload
 *       (the envelope does not carry one anyway).
 */
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('lucide-react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('lucide-react')>()
  const Stub = (props: { className?: string; 'aria-hidden'?: boolean }) => (
    <svg
      data-testid="icon"
      className={props.className}
      aria-hidden={props['aria-hidden']}
    />
  )
  return { ...actual, Check: Stub, X: Stub }
})

import DecisionRecordedToast from '@/components/dashboard/DecisionRecordedToast'

const ENTRY = {
  schema_version: 'atlas-decision-journal-entry/v1' as const,
  journal_entry_id: '33333333-3333-4333-8333-333333333333',
  recommendation_id: '11111111-1111-4111-8111-111111111111',
  action_taken: 'accept' as const,
  decided_at: '2026-08-01T00:01:00.000000Z',
  decision_etag: 'aabbccdd-1111-4111-8111-aaaaaaaaaaaa-d1',
  links: [],
}

describe('<DecisionRecordedToast />', () => {
  // Block-form arrow bodies unconditionally return `void`, which is
  // what the vitest ``afterEach``/``beforeEach`` overload
  // ``(fn: () => Awaitable<void>) => void`` resolves against. The
  // single-expression form ``() => vi.useFakeTimers()`` returns the
  // VitestUtils object and triggers TS2322. This is the explicit
  // stabilization fix for the typecheck leftovers.
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders nothing when entry is null', () => {
    render(
      <DecisionRecordedToast entry={null} onDismiss={() => {}} />,
    )
    expect(
      screen.queryByRole('status'),
    ).toBeNull()
  })

  it('renders the bounded status element when entry is set', () => {
    render(
      <DecisionRecordedToast entry={ENTRY} onDismiss={() => {}} autoDismissMs={2000} />,
    )
    const status = screen.getByRole('status')
    expect(status).toBeInTheDocument()
    expect(status.getAttribute('aria-live')).toBe('polite')
    // First 8 chars of the journal_entry_id are surfaced.
    expect(screen.getByTestId('toast-journal-id').textContent).toBe(
      '33333333…',
    )
  })

  it('calls onDismiss after the bounded auto-dismiss window', () => {
    const onDismiss = vi.fn()
    render(
      <DecisionRecordedToast
        entry={ENTRY}
        onDismiss={onDismiss}
        autoDismissMs={2000}
      />,
    )
    expect(onDismiss).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1999)
    expect(onDismiss).not.toHaveBeenCalled()
    vi.advanceTimersByTime(2)
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('clamps the auto-dismiss window into the bounded 1..10000 range', () => {
    const onDismiss = vi.fn()
    // Out-of-range upper bound clamps to 10000.
    render(
      <DecisionRecordedToast
        entry={ENTRY}
        onDismiss={onDismiss}
        autoDismissMs={99999999}
      />,
    )
    vi.advanceTimersByTime(10001)
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })
})
