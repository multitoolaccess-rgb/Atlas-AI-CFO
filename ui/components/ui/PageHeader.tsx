'use client'

import type { ReactNode } from 'react'

interface PageHeaderProps {
  title: string
  description?: string
  eyebrow?: string
  actions?: ReactNode
  className?: string
}

/** Shared route-header composition: readable mission, context, and actions. */
export default function PageHeader({
  title,
  description,
  eyebrow,
  actions,
  className = '',
}: PageHeaderProps) {
  return (
    <header className={`atlas-page-header ${className}`.trim()}>
      <div className="min-w-0">
        {eyebrow && <p className="label-md text-accent mb-2">{eyebrow}</p>}
        <h1 className="headline-xl text-primary">{title}</h1>
        {description && <p className="body-md text-secondary mt-2 max-w-3xl">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  )
}
