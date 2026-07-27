'use client'

import FloatingTimeRangeBar from '@/components/ui/FloatingTimeRangeBar'

interface GlobalFilterBarProps {
  /** Earliest transaction date in the dataset (ISO string). */
  earliestDate?: string | null
  /** Latest transaction date in the dataset (ISO string). */
  latestDate?: string | null
  className?: string
}

/**
 * DEPRECATION SHIM — use ``@/components/ui/FloatingTimeRangeBar``
 * directly. This file is intentionally a thin wrapper that maps the
 * previous ``earliestDate`` / ``latestDate`` props to the unified
 * ``rightSlot`` slot so /app/page.tsx continues to compile.
 *
 * Coverage text formatting (the original bar's right-aligned
 * "Data from Mar 2023 to Jul 2026") is preserved verbatim.
 */
export default function GlobalFilterBar({
  earliestDate,
  latestDate,
  className = '',
}: GlobalFilterBarProps) {
  const coverageText = earliestDate
    ? `Data from ${new Date(earliestDate).toLocaleDateString('en-US', {
        month: 'short',
        year: 'numeric',
      })}${latestDate ? ` to ${new Date(latestDate).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}` : ''}`
    : null
  return (
    <FloatingTimeRangeBar
      className={`top-[64px] ${className}`}
      rightSlot={
        coverageText ? (
          <p className="text-xs text-[var(--text-tertiary)] truncate hidden sm:block">
            {coverageText}
          </p>
        ) : undefined
      }
    />
  )
}
