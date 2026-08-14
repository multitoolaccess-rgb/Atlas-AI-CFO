'use client'

import type { ReactNode } from 'react'
import FloatingTimeRangeBar from '@/components/ui/FloatingTimeRangeBar'
import { useAtlasFilters } from '@/components/ui/AtlasFilterContext'

export interface AnalyticalContextBarProps {
  /** False when time range cannot alter the authoritative page query. */
  showRange?: boolean
  showCompare?: boolean
  accountSlot?: ReactNode
  pageSlot?: ReactNode
  coverage?: ReactNode
  freshness?: ReactNode
  className?: string
}

/** Inactive shared contract. It delegates range behavior to FloatingTimeRangeBar to prevent a second selector. */
function CompareControl() {
  const { isComparing, setIsComparing } = useAtlasFilters()
  return <label className="flex items-center gap-2 text-xs text-[var(--text-secondary)]"><input type="checkbox" checked={isComparing} onChange={(event) => setIsComparing(event.target.checked)} /> Compare</label>
}

export default function AnalyticalContextBar({ showRange = true, showCompare = false, accountSlot, pageSlot, coverage, freshness, className }: AnalyticalContextBarProps) {
  if (!showRange) return <div className={`flex flex-wrap items-center gap-3 rounded-xl border border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-3 ${className ?? ''}`} data-testid="analytical-context-bar">{showCompare && <CompareControl />}{accountSlot}{pageSlot}<span className="ml-auto flex gap-3 text-xs text-[var(--text-tertiary)]">{coverage}{freshness}</span></div>
  return <FloatingTimeRangeBar className={className} rightSlot={<span className="flex gap-3 text-xs text-[var(--text-tertiary)]">{coverage}{freshness}</span>}><span data-testid="context-bar-controls" className="flex flex-wrap items-center gap-3">{showCompare && <CompareControl />}{accountSlot}{pageSlot}</span></FloatingTimeRangeBar>
}
