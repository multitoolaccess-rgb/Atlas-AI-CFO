'use client'

/**
 * Phase 2 Slice 2 — Decision Recorded Toast.
 *
 * A bounded sanitized success toast tied to a freshly-appended journal
 * entry. Shows the action verb and the ``decided_at`` timestamp.
 * Auto-dismisses after a bounded
 * window so the "Recorded" state on the parent card remains the
 * source of truth after the toast fades.
 *
 * Persisted-state across reload is intentionally NOT stored here
 * because the Phase 2 plan §2 AC10 explicitly lists cross-reload
 * journal-state visibility as a non-goal ("kept for a future
 * Phase 2.x extension"). Reload reverts to action buttons; a
 * re-click is idempotent and collapses to the same journal row.
 */

import { useEffect } from 'react'
import { Check, X as XIcon } from 'lucide-react'
import type { DecisionJournalEntryWire } from '@/lib/api_phase2'

export interface DecisionRecordedToastProps {
  entry: DecisionJournalEntryWire | null
  onDismiss: () => void
  /** Auto-dismiss in ms (bounded 1..10000). */
  autoDismissMs?: number
}

function compactTimestamp(rfc3339: string): string {
  return rfc3339.replace('T', ' ').slice(0, 19) + 'Z'
}

export default function DecisionRecordedToast({
  entry,
  onDismiss,
  autoDismissMs = 5000,
}: DecisionRecordedToastProps) {
  useEffect(() => {
    if (!entry) return
    const bounded = Math.min(Math.max(autoDismissMs, 1000), 10000)
    const t = window.setTimeout(() => onDismiss(), bounded)
    return () => window.clearTimeout(t)
  }, [entry, autoDismissMs, onDismiss])

  if (!entry) return null

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="decision-recorded-toast"
      className="fixed bottom-6 right-6 z-50 inline-flex items-start gap-3 px-4 py-3 max-w-sm bg-[var(--success-50)] border border-[var(--success-200)] rounded-lg shadow-lg animate-fadeIn"
    >
      <Check
        className="w-5 h-5 text-[var(--success-700)] mt-0.5 flex-shrink-0"
        aria-hidden="true"
      />
      <div className="flex-1">
        <p className="text-sm font-bold text-[var(--success-700)]">Recorded.</p>
        <p className="text-xs text-[var(--success-700)] mt-0.5">
          Action:{' '}
          <strong className="text-[var(--success-700)]">{entry.action_taken}</strong>
        </p>
        <p className="text-[0.65rem] text-[var(--success-700)] mt-0.5">
          Decided at {compactTimestamp(entry.decided_at)}
        </p>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss notification"
        className="text-[var(--success-700)] hover:text-[var(--success-800)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--success-700)] transition-colors"
      >
        <XIcon className="w-4 h-4" aria-hidden="true" />
      </button>
    </div>
  )
}
