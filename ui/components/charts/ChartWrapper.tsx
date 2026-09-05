'use client'

import React from 'react'
import Surface from '@/components/ui/Surface'

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
  /** Children contain interactive controls (e.g. legend buttons); avoid role="img" so focusable descendants stay announced */
  interactiveChildren?: boolean
  /** Additional classes on the outer container */
  className?: string
  /** Children — the actual Recharts content */
  children: React.ReactNode
}

/** Shared chart shell: a working surface with honest loading and empty states. */
export default function ChartWrapper({
  height = 320,
  loading = false,
  empty = false,
  emptyMessage = 'No data yet.',
  ariaLabel = 'Chart',
  interactiveChildren = false,
  className,
  children,
}: ChartWrapperProps) {
  if (loading) {
    return (
      <Surface
        surfaceRole="working"
        className={`flex items-center justify-center ${className ?? ''}`}
        style={{ height }}
        aria-busy="true"
      >
        <div className="w-full h-full rounded-lg skeleton" />
      </Surface>
    )
  }

  if (empty) {
    return (
      <Surface
        surfaceRole="working"
        className={`flex items-center justify-center ${className ?? ''}`}
        style={{ height }}
      >
        <p className="text-sm text-[var(--text-tertiary)]">{emptyMessage}</p>
      </Surface>
    )
  }

  return (
    <Surface
      surfaceRole="working"
      className={className}
      style={{ height }}
      role={interactiveChildren ? 'group' : 'img'}
      aria-label={ariaLabel}
    >
      {children}
    </Surface>
  )
}
