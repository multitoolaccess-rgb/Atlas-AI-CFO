'use client'

import React from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Content inside the card. */
  children: React.ReactNode
  /**
   * Visual variant — maps to the semantic card classes defined in
   * `globals.css` (`card-primary`, `card-success`, `card-warning`, `card-danger`).
   * Defaults to the base `.card` style.
   */
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'danger'
  /**
   * Interactive card — adds hover border highlight + cursor pointer.
   * Uses the `.card-interactive` class from globals.css.
   */
  interactive?: boolean
  /** Padding preset. Default `'default'` (p-6). */
  padding?: 'none' | 'compact' | 'default' | 'large'
  /** Additional CSS classes merged onto the outer `<div>`. */
  className?: string
}

// ---------------------------------------------------------------------------
// Padding map
// ---------------------------------------------------------------------------

const paddingMap = {
  none: '',
  compact: 'p-4',
  default: 'p-6',
  large: 'p-8',
} as const

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Structural card wrapper.
 *
 * Delegates border, shadow, and background to the `.card` CSS class
 * defined in `globals.css` so the component stays in sync with the
 * design-system tokens without hard-coding Tailwind utilities.
 *
 * @example
 *   <Card>
 *     <h3>Title</h3>
 *     <p>Body text</p>
 *   </Card>
 *
 *   <Card variant="success" padding="large">
 *     <SuccessContent />
 *   </Card>
 *
 *   <Card interactive onClick={() => navigate('/details')}>
 *     <DetailPreview />
 *   </Card>
 */
export default function Card({
  children,
  variant = 'default',
  interactive = false,
  padding = 'default',
  className = '',
  ...rest
}: CardProps) {
  // Build the class string from the CSS-layer tokens
  const variantClass =
    variant === 'default' ? '' : `card-${variant}`

  const interactiveClass = interactive ? 'card-interactive' : ''

  const classes = [
    'card',
    variantClass,
    interactiveClass,
    paddingMap[padding],
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={classes} {...rest}>
      {children}
    </div>
  )
}
