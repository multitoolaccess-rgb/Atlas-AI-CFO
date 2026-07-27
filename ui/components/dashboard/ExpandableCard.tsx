'use client'

import { useState, useCallback, type ReactNode } from 'react'
import { Maximize2, Minimize2 } from 'lucide-react'

interface ExpandableCardProps {
  title: string
  subtitle?: string
  icon?: ReactNode
  /** Content rendered to the right of the title row (e.g. KPIs, badges). */
  headerRight?: ReactNode
  /** Base content (always visible). */
  children: ReactNode
  /** Content shown only when expanded. Omit to disable expand/collapse. */
  expandedContent?: ReactNode
  defaultExpanded?: boolean
  className?: string
  onExpand?: (expanded: boolean) => void
}

export default function ExpandableCard({
  title,
  subtitle,
  icon,
  headerRight,
  children,
  expandedContent,
  defaultExpanded = false,
  className = '',
  onExpand,
}: ExpandableCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)

  const toggle = useCallback(() => {
    setExpanded((prev) => {
      const next = !prev
      onExpand?.(next)
      return next
    })
  }, [onExpand])

  return (
    <div
      className={`card overflow-hidden transition-all duration-200 ${
        expanded ? 'ring-1 ring-[var(--primary-200)]' : ''
      } ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between p-5 pb-0">
        <div className="flex items-center gap-3 min-w-0">
          {icon && (
            <div className="w-8 h-8 rounded-lg bg-[var(--primary-50)] flex items-center justify-center border border-[var(--primary-200)] flex-shrink-0">
              {icon}
            </div>
          )}
          <div className="min-w-0">
            <h2 className="headline-md text-primary truncate">{title}</h2>
            {subtitle && (
              <p className="text-xs text-tertiary truncate">{subtitle}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {headerRight}
          {expandedContent && (
            <button
              type="button"
              onClick={toggle}
              className="p-1.5 rounded-lg text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--slate-100)] transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--primary-500)]"
              aria-label={expanded ? 'Collapse' : 'Expand'}
              aria-expanded={expanded}
            >
              {expanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>
          )}
        </div>
      </div>

      {/* Base content */}
      <div className="p-5">{children}</div>

      {/* Expanded content with smooth height transition */}
      {expandedContent && (
        <div
          className="overflow-hidden transition-all duration-200 ease-in-out"
          style={{ maxHeight: expanded ? '2000px' : '0px', opacity: expanded ? 1 : 0 }}
        >
          <div className="px-5 pb-5 border-t border-[var(--border-color)] pt-4">
            {expandedContent}
          </div>
        </div>
      )}
    </div>
  )
}
