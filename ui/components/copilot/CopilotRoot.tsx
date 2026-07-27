'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import CopilotOrb from './CopilotOrb'
import CopilotDock from './CopilotDock'
import type { InsightItem } from '@/lib/api'

/**
 * Phase 4 — CopilotRoot.
 *
 * Single mount point for the persistent AI copilot surface. Combines
 * the floating CopilotOrb (bottom-right) with the slide-in CopilotDock
 * side panel. Manages its own open/closed state and persists the last
 * insight count to localStorage so the unread badge survives reloads.
 *
 * Render this component ONCE per layout (e.g. once in PageLayout and
 * once in the Home page). It's safely re-mountable; the persistence
 * is keyed off localStorage so the user sees a consistent badge count
 * across navigations.
 *
 * The Dock receives the dashboard's insight stream as input — this
 * doesn't trigger network activity (insights arrive from the parent
 * layout's existing caches). When the array is empty, the Dock shows
 * the empty-state copy in its Insights tab.
 */

interface CopilotRootProps {
  /** Dashboard insights to feed the proactive insights tab. */
  insights?: InsightItem[]
}

const STORAGE_KEY = 'fc_copilot_last_insight_count'

export default function CopilotRoot({ insights = [] }: CopilotRootProps) {
  const [open, setOpen] = useState(false)
  const [insightCount, setInsightCount] = useState(0)
  const orbRef = useRef<HTMLButtonElement>(null)
  const prevOpenRef = useRef(open)

  const handleToggle = useCallback(() => setOpen((v) => !v), [])
  const handleClose = useCallback(() => setOpen(false), [])

  // Sync unread insight count — every time the insights array changes,
  // write the count. The orb badge shows this number; when the user
  // opens the dock we treat the insights as "read" and clear the badge.
  useEffect(() => {
    if (open) {
      setInsightCount(0)
      try {
        localStorage.setItem(STORAGE_KEY, '0')
      } catch {
        // localStorage may be unavailable in private mode; ignore.
      }
    } else if (insights.length > 0) {
      setInsightCount(insights.length)
      try {
        localStorage.setItem(STORAGE_KEY, String(insights.length))
      } catch {
        // ignore
      }
    }
  }, [open, insights.length])

  // Hydrate the persisted count on mount.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      const parsed = raw ? Number(raw) : 0
      if (Number.isFinite(parsed) && parsed > 0) setInsightCount(parsed)
    } catch {
      // ignore
    }
  }, [])

  // Return focus to the orb trigger when the dock closes.
  useEffect(() => {
    if (!open && prevOpenRef.current) {
      orbRef.current?.focus()
    }
    prevOpenRef.current = open
  }, [open])

  return (
    <>
      <CopilotOrb ref={orbRef} open={open} onToggle={handleToggle} insightCount={insightCount} />
      <CopilotDock open={open} onClose={handleClose} insights={insights} />
    </>
  )
}
