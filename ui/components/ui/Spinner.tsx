'use client'

import React from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SpinnerProps {
  /** Size preset — controls the overall container dimensions. */
  size?: 'sm' | 'md' | 'lg'
  /** Optional text label rendered below the spinner (e.g. "Loading…"). */
  label?: string
  /** Additional CSS classes on the outer wrapper. */
  className?: string
}

// ---------------------------------------------------------------------------
// Size map
// ---------------------------------------------------------------------------

const sizeMap = {
  sm: 'w-5 h-5',
  md: 'w-8 h-8',
  lg: 'w-12 h-12',
} as const

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Animated loading spinner.
 *
 * Two usage patterns:
 * 1. **Inline** — drop into a flex container alongside text.
 * 2. **Overlay** — use inside a centered wrapper for full-section loading.
 *
 * Uses CSS `animate-spin` + a ring style that respects the project's
 * `--primary-500` design token, so it works in both light and dark mode.
 */
export default function Spinner({
  size = 'md',
  label,
  className = '',
}: SpinnerProps) {
  return (
    <div
      className={`inline-flex flex-col items-center justify-center gap-2 ${className}`}
      role="status"
      aria-label={label ?? 'Loading'}
    >
      <svg
        className={`animate-spin ${sizeMap[size]}`}
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
      >
        <circle
          cx="12"
          cy="12"
          r="10"
          stroke="var(--slate-200)"
          strokeWidth="3"
        />
        <path
          d="M12 2a10 10 0 0 1 10 10"
          stroke="var(--primary-500)"
          strokeWidth="3"
          strokeLinecap="round"
        />
      </svg>
      {label && (
        <span className="text-xs font-medium text-[var(--text-tertiary)]">
          {label}
        </span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Skeleton helper — full-area loading placeholder
// ---------------------------------------------------------------------------

export interface SkeletonProps {
  /** Height in px, or any CSS length string. */
  height?: number | string
  /** Width — defaults to 100%. */
  width?: number | string
  /** Border radius. Default: `var(--radius-lg)`. */
  rounded?: boolean
  /** Additional CSS classes. */
  className?: string
}

/**
 * Pulsing skeleton rectangle for content-loading placeholders.
 *
 * Drop-in replacement for the scattered `skeleton` class usage across
 * dashboard components. Wraps the same CSS animation in a typed component
 * so consumers get prop-based sizing instead of Tailwind string gymnastics.
 *
 * @example
 *   <Skeleton height={240} />                // chart placeholder
 *   <Skeleton height={16} width="40%" />     // text line placeholder
 */
export function Skeleton({
  height,
  width,
  rounded = true,
  className = '',
}: SkeletonProps) {
  const style: React.CSSProperties = {}
  if (height !== undefined) style.height = typeof height === 'number' ? `${height}px` : height
  if (width !== undefined) style.width = typeof width === 'number' ? `${width}px` : width

  return (
    <div
      className={`skeleton ${rounded ? 'rounded-lg' : ''} ${className}`}
      style={style}
      aria-hidden="true"
    />
  )
}
