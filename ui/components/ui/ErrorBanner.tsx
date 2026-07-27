'use client'

import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { Button } from './index'

interface ErrorBannerProps {
  title: string
  message: string
  onRetry?: () => void
  /**
   * Optional external dismiss handler. When provided, the X button
   * calls this function (the parent controls visibility). When omitted,
   * the banner manages its OWN internal dismiss state — clicking X
   * hides it until the title/message props change (e.g. a new error).
   */
  onDismiss?: () => void
  /**
   * Plain ``<a href={retryHref}>`` Retry control — used by the
   * SSR-rendered banner in ``app/layout.tsx`` so the alert is
   * actionable even if client JS has not hydrated yet. Clicking
   * triggers a full page reload which re-runs the SSR health probe.
   * Mutually exclusive with ``onRetry`` (onRetry wins if both set).
   */
  retryHref?: string
  variant?: 'danger' | 'warning' | 'success'
}

/**
 * Reusable banner with optional Retry and Dismiss buttons.
 *
 * Used by app/page.tsx (Overview) and all 7 sub-routes. The
 * ``onRetry`` prop re-runs the page's data fetch — the parent
 * component is expected to expose a `retry` callback from its
 * data-loading hook.
 *
 * **Self-dismissing behavior**: when no ``onDismiss`` prop is passed,
 * the banner manages its own visibility internally. Clicking the X
 * button hides it. If ``title`` or ``message`` changes (a new error
 * appears), the banner automatically re-shows.
 */
export default function ErrorBanner({
  title,
  message,
  onRetry,
  onDismiss,
  retryHref,
  variant = 'danger',
}: ErrorBannerProps) {
  // Internal dismiss state — used when the parent doesn't provide onDismiss.
  const [internallyDismissed, setInternallyDismissed] = useState(false)

  // Reset internal dismiss when the error content changes (new error appeared).
  useEffect(() => {
    setInternallyDismissed(false)
  }, [title, message])

  // Determine visibility: if parent controls it, always render (parent
  // conditionally renders the component). If self-managing, check internal state.
  const visible = onDismiss !== undefined || !internallyDismissed
  if (!visible) return null

  const styles =
    variant === 'danger'
      ? 'border-danger-200 bg-danger-50 text-danger-700'
      : variant === 'warning'
        ? 'border-warning-200 bg-warning-50 text-warning-700'
        : 'border-success-200 bg-success-50 text-success-700'

  const handleDismiss = onDismiss ?? (() => setInternallyDismissed(true))

  return (
    <div
      className={`mb-6 p-4 rounded-lg border ${styles}`}
      role={variant === 'success' ? 'status' : 'alert'}
      aria-live={variant === 'success' ? 'polite' : 'assertive'}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <strong>{title}</strong> {message}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {onRetry ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={onRetry}
              ariaLabel="Retry loading data"
            >
              Retry
            </Button>
          ) : retryHref ? (
            <a
              href={retryHref}
              aria-label="Retry loading data"
              className="flex items-center justify-center h-9 px-4 text-sm font-bold rounded-md border border-outline-variant/30 bg-surface text-on-surface hover:bg-surface-container transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              Retry
            </a>
          ) : null}
          <button
            type="button"
            onClick={handleDismiss}
            aria-label="Dismiss notification"
            className="
              p-1 rounded-[var(--radius-sm)]
              text-current opacity-60 hover:opacity-100
              transition-opacity
              focus-visible:outline-2 focus-visible:outline-offset-2
              focus-visible:outline-current
            "
            data-testid="error-banner-dismiss"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  )
}
