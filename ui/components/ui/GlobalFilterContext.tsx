'use client'

/**
 * DEPRECATION SHIM — the canonical implementation lives in
 * ``@/components/ui/AtlasFilterContext``.
 *
 * This file is intentionally a thin re-export of the unified context
 * so all existing imports (``<GlobalFilterProvider>``, ``useGlobalFilters``,
 * ``dateRangeFromPreset``, ``BUDGET_GROUP_OPTIONS``) continue to compile
 * and run identically. The notable behavior change is that
 * ``timeRange`` is now URL-synced via ``?range=...`` (the same behavior
 * the Overview page has had since launch) instead of in-memory —
 * recipients of shared Budgeting/Income/Expenses links now see the
 * sender's selected range rather than the page-default YTD.
 *
 * New code should import from ``@/components/ui/AtlasFilterContext``
 * directly.
 */
export {
  AtlasFilterProvider as GlobalFilterProvider,
  useAtlasFilters as useGlobalFilters,
  dateRangeFromPreset,
  BUDGET_GROUP_OPTIONS,
  type AtlasFilterState as GlobalFilterState,
} from '@/components/ui/AtlasFilterContext'
