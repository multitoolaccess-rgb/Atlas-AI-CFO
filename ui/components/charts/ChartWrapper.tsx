'use client'

import React from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChartWrapperProps {
  /** Height of the chart area in pixels */
  height?: number
  /** Show skeleton loading state */
  loading?: boolean
  /** Show empty state message when data is absent */
  empty?: boolean
  /** Custom empty-state message */
  emptyMessage?: string
  /** Accessible label for the chart region */
  ariaLabel?: string
  /** Additional CSS classes on the outer container */
  className?: string
  /** Children — the actual Recharts content */
  children: React.ReactNode
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ChartWrapper({
  height = 320,
  loading = false,
  empty = false,
  emptyMessage = 'No data yet.',
  ariaLabel = 'Chart',
  className,
  children,
}: ChartWrapperProps) {
  if (loading) {
    return (
      <div
        className={`flex items-center justify-center ${className ?? ''}`}
        style={{ height }}
        aria-busy="true"
      >
        <div className="w-full h-full rounded-lg skeleton" />
      </div>
    )
  }

  if (empty) {
    return (
      <div
        className={`flex items-center justify-center ${className ?? ''}`}
        style={{ height }}
      >
        <p className="text-sm text-[var(--text-tertiary)]">{emptyMessage}</p>
      </div>
    )
  }

  return (
    <div
      className={className}
      style={{ height }}
      role="img"
      aria-label={ariaLabel}
    >
      {children}
    </div>
  )
}
