/**
 * ErrorBanner component — variant → Tailwind className contract.
 *
 * Pins the visual contract that protects against the regression the
 * user just hit on /overview: a recoverable downstream error was
 * rendering with the default `variant="danger"` (RED) styling,
 * which made a "Retry and it works" situation look catastrophic.
 * Both halves of the contract are locked here so a future change
 * to either default (silent swap to amber by default) or to the
 * `variant="warning"` styling (rename of `border-warning-200`,
 * etc.) is caught immediately by `bash scripts/test.sh`.
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import ErrorBanner from '@/components/ui/ErrorBanner'

describe('ErrorBanner — variant → className contract', () => {
  it('renders the default danger variant in red when no variant prop is passed', () => {
    render(<ErrorBanner title="Boom:" message="Something broke." />)
    const banner = screen.getByRole('alert')
    // Default must remain RED — destructive-action banners
    // (import upload failures, form save errors) deliberately
    // use this. The user-facing fix is for the app to PASS
    // variant="warning" on page-level data-load banners, NOT
    // to flip the default.
    expect(banner.className).toContain('border-danger-200')
    expect(banner.className).toContain('bg-danger-50')
    expect(banner.className).toContain('text-danger-700')
    expect(banner.className).not.toContain('border-warning-200')
  })

  it('renders the warning variant in amber when variant="warning"', () => {
    render(
      <ErrorBanner
        title="WARN:"
        message="Downstream is flaky."
        variant="warning"
      />,
    )
    const banner = screen.getByRole('alert')
    expect(banner.className).toContain('border-warning-200')
    expect(banner.className).toContain('bg-warning-50')
    expect(banner.className).toContain('text-warning-700')
    expect(banner.className).not.toContain('border-danger-200')
  })

  it('renders the title and message verbatim (no truncation or escape)', () => {
    render(
      <ErrorBanner
        title="Couldn't load dashboard:"
        message="Downstream service is unavailable. Your session is fine — please try again in a moment."
      />,
    )
    expect(screen.getByText(/^Couldn't load dashboard:$/)).toBeInTheDocument()
    expect(
      screen.getByText(/Downstream service is unavailable/i),
    ).toBeInTheDocument()
  })
})
