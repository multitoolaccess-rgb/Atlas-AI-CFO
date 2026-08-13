'use client'

import { useId, type ReactNode } from 'react'

interface EmptyStateProps {
  icon?: ReactNode
  visual?: ReactNode
  title: string
  description: string
  action?: ReactNode
  guidance?: ReactNode
  className?: string
  testId?: string
  focal?: boolean
}

/**
 * Composed empty state for data surfaces. The visual is intentionally
 * decorative: callers provide the real next action, while this component
 * explains what is missing and why the surface matters.
 */
export default function EmptyState({
  icon,
  visual,
  title,
  description,
  action,
  guidance,
  className = '',
  testId,
  focal = false,
}: EmptyStateProps) {
  const generatedTitleId = useId()
  const titleId = `${testId ?? 'empty-state'}-${generatedTitleId.replace(/:/g, '')}-title`

  return (
    <section
      className={`empty-state ${focal ? 'empty-state-focal' : ''} ${className}`.trim()}
      data-testid={testId}
      aria-labelledby={titleId}
    >
      {visual}
      <div className="empty-state-mark" aria-hidden="true">
        {icon}
      </div>
      <div className="max-w-xl">
        <h2 id={titleId} className="headline-md text-primary">
          {title}
        </h2>
        <p className="mt-2 body-md text-secondary">{description}</p>
      </div>
      {action && <div className="mt-6">{action}</div>}
      {guidance && <div className="empty-state-guidance">{guidance}</div>}
    </section>
  )
}
