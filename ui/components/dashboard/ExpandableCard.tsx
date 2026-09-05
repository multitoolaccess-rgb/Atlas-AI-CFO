'use client'

import { useState, useCallback, useEffect, type ReactNode } from 'react'
import { ChevronDown, ChevronUp, Maximize2, Minimize2 } from 'lucide-react'

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

/** Shared focus-mode state for dashboard visualizations outside ExpandableCard. */
export function useDashboardFocus() {
  const [focused, setFocused] = useState(false)

  useEffect(() => {
    if (!focused) return
    const previousOverflow = document.body.style.overflow
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setFocused(false)
    }
    document.body.style.overflow = 'hidden'
    document.documentElement.classList.add('dashboard-focus-active')
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      document.documentElement.classList.remove('dashboard-focus-active')
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [focused])

  return { focused, setFocused }
}

export function DashboardFocusToggle({ focused, onToggle }: { focused: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="p-1.5 rounded-lg text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--slate-100)] transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--primary-500)]"
      aria-label={focused ? 'Exit focus mode' : 'Open focus mode'}
      aria-pressed={focused}
      title={focused ? 'Exit focus mode (Esc)' : 'Open focus mode'}
      data-testid="dashboard-focus-toggle"
    >
      {focused ? <Minimize2 className="w-4 h-4" aria-hidden="true" /> : <Maximize2 className="w-4 h-4" aria-hidden="true" />}
    </button>
  )
}

/**
 * Full-screen presentation layer shared by all analytical cards.
 * The floating range bar sits above this layer (z-60), so the selected
 * range remains available while a chart is in focus mode.
 */
export function DashboardFocusLayer({
  focused,
  title,
  children,
}: {
  focused: boolean
  title: string
  children: ReactNode
}) {
  if (!focused) return <>{children}</>

  return (
    // pt-40 reserves space for the pinned floating range bar (fixed at
    // top 4.5rem, up to ~80px tall when wrapped) so it never overlaps
    // the focused visualization.
    <div
      className="fixed inset-0 z-50 touch-pan-y overflow-y-auto overscroll-contain bg-[var(--bg-primary)]/95 p-3 pt-40 backdrop-blur-sm sm:p-6 sm:pt-40"
      role="dialog"
      aria-modal="true"
      aria-label={`${title} focus mode`}
      data-testid="dashboard-focus-layer"
    >
      <div className="mx-auto min-h-full w-full max-w-[1400px]">
        {children}
      </div>
    </div>
  )
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
  const { focused, setFocused } = useDashboardFocus()

  const toggle = useCallback(() => {
    setExpanded((prev) => {
      const next = !prev
      onExpand?.(next)
      return next
    })
  }, [onExpand])

  const card = (
    <div
      className={`card overflow-hidden transition-all duration-200 ${
        expanded ? 'ring-1 ring-[var(--primary-200)]' : ''
      } ${focused ? 'min-h-[calc(100vh-3rem)]' : ''} ${className}`}
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
              title={expanded ? 'Collapse details' : 'Expand details'}
            >
              {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
          )}
          <DashboardFocusToggle focused={focused} onToggle={() => setFocused((value) => !value)} />
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

  return <DashboardFocusLayer focused={focused} title={title}>{card}</DashboardFocusLayer>
}
