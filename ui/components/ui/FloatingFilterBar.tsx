'use client'

import type { ReactNode } from 'react'

/**
 * DEPRECATION SHIM — use ``@/components/ui/FloatingTimeRangeBar``
 * directly. This file is intentionally a thin sticky wrapper whose
 * RENDER OUTPUT IS BYTE-IDENTICAL to the original ``FloatingFilterBar``
 * so existing imports (``<FloatingFilterBar>{existing children}</...>``
 * in Budgeting, Income, Expenses) keep rendering as-is.
 *
 * Crucially this shim does NOT auto-render a TimeRangeSelector inside
 * the bar (the unified bar does). If we re-exported the new bar here
 * directly, the existing consumers — which currently colocate their
 * own ``<TimeRangeSelector>`` inside the children slot — would
 * render TWO TimeRangeSelectors on the same bar (a regression).
 * Keeping it as a pure sticky wrapper preserves the old contract.
 *
 * Per-page migration to ``<FloatingTimeRangeBar>`` will: (1) swap
 * the import, (2) REMOVE the colocated ``<TimeRangeSelector>`` from
 * children since the new bar renders it automatically, (3) move
 * any page-specific controls (button + add-form trigger, export
 * button, etc.) into the children slot.
 */
interface FloatingFilterBarProps {
  children?: ReactNode
  className?: string
}

export default function FloatingFilterBar({ children, className = '' }: FloatingFilterBarProps) {
  return (
    <div
      className={`sticky top-4 z-30 flex flex-wrap items-center justify-between gap-3 px-4 py-3 rounded-xl border backdrop-blur-md bg-[var(--bg-primary)]/80 border-[var(--border-color)] shadow-sm ${className}`}
    >
      {children}
    </div>
  )
}
