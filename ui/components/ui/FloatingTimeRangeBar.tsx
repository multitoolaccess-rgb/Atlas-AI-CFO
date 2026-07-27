'use client'

import type { ReactNode } from 'react'
import { Calendar } from 'lucide-react'
import TimeRangeSelector from '@/components/ui/TimeRangeSelector'
import { useAtlasFilters } from '@/components/ui/AtlasFilterContext'

interface FloatingTimeRangeBarProps {
  /**
   * Optional page-specific controls rendered AFTER the time-range
   * selector on the LEFT side. Examples:
   *   - Activity: <CategoryFilter /> <MerchantFilter />
   *   - Goals:    <GoalFilter />
   *   - Budgeting: <AddBudgetButton />
   *   - Income:    <ExportButton />
   */
  children?: ReactNode
  /**
   * Optional right-aligned helper text/icons. Examples:
   *   - Overview: "Data from Mar 2023 to Jul 2026"
   *   - Goals:    "5 active goals"
   */
  rightSlot?: ReactNode
  /** Override or extend Tailwind classes (e.g. Overview sets `top-[64px]`
   *  because its page chrome is a sticky 64px header; PageLayout pages
   *  sit BELOW the existing page header so the default `top-4` is fine). */
  className?: string
}

/**
 * FloatingTimeRangeBar
 * --------------------
 * Canonical sticky, glass-like control bar for the Atlas app. Replaces
 * the previously split pair:
 *
 *  - ui/components/ui/FloatingFilterBar.tsx — generic sticky wrapper
 *    consumed by Budgeting, Income, and Expenses.
 *  - components/dashboard/GlobalFilterBar.tsx — Overview-specific
 *    hard-coded Calendar icon + "Range" label + TimeRangeSelector +
 *    coverage text.
 *
 * The two shared basically the same visual contract. Keeping them
 * split meant every new page had to choose one or the other AND
 * diverge on the page-specific children slot design.
 *
 * Unified behavior:
 *  - The TIME RANGE IS ALWAYS PRESENT and reads from
 *    ``useAtlasFilters()`` (the unified context that URL-syncs the
 *    ``?range=...`` query param — the same behavior Overview has
 *    shipped since launch and that Budgeting/Income/Expenses only
 *    gained via the Phase 2 unification commit).
 *  - The ``children`` slot renders AFTER the time-range on the left
 *    side — page-specific controls (category filter, merchant
 *    filter, add-button, export-button, etc.) compose here.
 *  - The ``rightSlot`` prop renders on the right edge — coverage
 *    text, count-badges, anything that BENEFITS from being right-
 *    aligned regardless of scroll position.
 *  - The ``className`` prop overrides layout (e.g. ``top-[64px]``
 *    for pages that already have a sticky 64px page header).
 *
 * Migration story:
 *  - ``<FloatingFilterBar>{children}</FloatingFilterBar>`` →
 *    ``<FloatingTimeRangeBar>{children}</FloatingTimeRangeBar>`` —
 *    children render in the same slot, behavior identical.
 *  - ``<GlobalFilterBar earliestDate={d.earliest}
 *      latestDate={d.latest} />`` →
 *    ``<FloatingTimeRangeBar
 *       rightSlot={<span>{coverageText}</span>} />`` — coverage text
 *    moved from inside the bar to a rightSlot; rendering surface
 *    identical.
 */
export default function FloatingTimeRangeBar({
  children,
  rightSlot,
  className = '',
}: FloatingTimeRangeBarProps) {
  const { timeRange, setTimeRange } = useAtlasFilters()

  return (
    <div
      className={`sticky top-4 z-30 flex flex-wrap items-center justify-between gap-3 px-4 py-3 rounded-xl border backdrop-blur-md bg-[var(--bg-primary)]/80 border-[var(--border-color)] shadow-sm mb-4 ${className}`}
    >
      <div className="flex items-center gap-3 min-w-0 flex-wrap">
        <Calendar className="w-4 h-4 text-[var(--text-tertiary)] flex-shrink-0" />
        <span className="text-xs font-semibold text-[var(--text-secondary)]">
          Range
        </span>
        <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
        {children}
      </div>
      {rightSlot}
    </div>
  )
}
