'use client'

/**
 * DEPRECATION SHIM — the canonical implementation lives in
 * ``@/components/ui/AtlasFilterContext``.
 *
 * This file is intentionally a thin re-export of the unified context
 * so all existing imports continue to compile and run identically.
 * New code should import from ``@/components/ui/AtlasFilterContext``
 * directly. The two-context split (this file + ``GlobalFilterContext``)
 * was collapsed in Phase 2: a single URL-synced context now serves the
 * Overview, Budgeting, Income, Expenses, and any future page with a
 * floating time-range bar.
 */
export {
  AtlasFilterProvider as DashboardFilterProvider,
  useAtlasFilters as useDashboardFilters,
  type AtlasFilterState as DashboardFilterState,
} from '@/components/ui/AtlasFilterContext'
