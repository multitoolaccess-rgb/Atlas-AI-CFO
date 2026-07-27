'use client'

/**
 * Reusable skeleton placeholder for loading states.
 *
 * Wraps the `.skeleton` CSS class from `animations.css` into a
 * composable React component. Supports rectangle, circle, and
 * text-line shapes with configurable dimensions.
 *
 * Usage:
 *   <Skeleton width="w-48" height="h-6" />
 *   <Skeleton variant="circle" size="w-10 h-10" />
 *   <SkeletonCard />   // pre-built card skeleton
 */

import { type CSSProperties } from 'react'

interface SkeletonProps {
  /** Tailwind width class (e.g. 'w-48', 'w-full'). Default: 'w-full'. */
  width?: string
  /** Tailwind height class (e.g. 'h-6', 'h-4'). Default: 'h-4'. */
  height?: string
  /** Extra classes merged onto the skeleton div. */
  className?: string
  /** Inline style override (e.g. for percentage widths). */
  style?: CSSProperties
  /** Screen-reader label while loading. */
  'aria-label'?: string
}

export function Skeleton({
  width = 'w-full',
  height = 'h-4',
  className = '',
  style,
  'aria-label': ariaLabel,
}: SkeletonProps) {
  return (
    <div
      className={`skeleton ${width} ${height} ${className}`.trim()}
      style={style}
      aria-hidden={!ariaLabel}
      {...(ariaLabel ? { 'aria-label': ariaLabel, role: 'status' } : {})}
    />
  )
}

/**
 * Pre-built skeleton for card-shaped content (e.g. dashboard panels).
 * Renders a shimmer rectangle with rounded corners.
 */
export function SkeletonCard({
  height = 'h-48',
  className = '',
}: {
  height?: string
  className?: string
}) {
  return (
    <div
      className={`card p-6 ${className}`.trim()}
      aria-busy="true"
      role="status"
    >
      <Skeleton height={height} />
    </div>
  )
}

/**
 * Pre-built skeleton for a text block (heading + body lines).
 */
export function SkeletonText({
  lines = 3,
  headingWidth = 'w-1/3',
  className = '',
}: {
  lines?: number
  headingWidth?: string
  className?: string
}) {
  return (
    <div className={`space-y-3 ${className}`.trim()} aria-busy="true" role="status">
      <Skeleton width={headingWidth} height="h-6" />
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} height="h-4" width={i === lines - 1 ? 'w-2/3' : 'w-full'} />
      ))}
    </div>
  )
}

export default Skeleton
