'use client'

import { createContext, useContext, useState, useCallback, useMemo, useRef, useEffect, type ReactNode } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import type { TimeRangePreset } from '@/components/ui/TimeRangeSelector'

/**
 * AtlasFilterContext
 * ------------------
 * Canonical unified filter context for the Atlas financial UI. Replaces
 * the previously-split pair:
 *
 *   - `DashboardFilterContext` (URL-synced timeRange, account filters)
 *   - `GlobalFilterContext`    (in-memory timeRange, account + budget +
 *                              category filters)
 *
 * The two old contexts share 95% of their shape and identical TS
 * interfaces for the consumer — keeping them separate meant every new
 * page had to pick one or the other, and Budgeting/Income/Expenses
 * drifted onto the in-memory variant which lost URL persistence (a
 * shared link to a 30-day Budgeting view collapsed to the page-default
 * YTD on the recipient's machine).
 *
 * Merged semantics (conservative — only IMPROVEMENTS, no behavior
 * removals):
 *   - ``timeRange``: URL-synced via the ``?range=...`` query param.
 *     The Dashboard pattern wins here because sharing a URL preserves
 *     the recipient's view; the old in-memory variant reset on every
 *     reload.
 *   - ``selectedAccountId`` / ``selectedAccountType``: in-memory
 *     (unchanged from both originals).
 *   - ``selectedBudgetGroup`` / ``selectedCategoryId``: in-memory
 *     (unchanged from GlobalFilterContext).
 *
 * Back-compat: ``DashboardFilterContext.tsx`` and ``GlobalFilterContext.tsx``
 * are kept as DELETED SOURCE FILES that re-export their public API
 * from here. Existing ``<DashboardFilterProvider>``, ``useDashboardFilters``,
 * ``<GlobalFilterProvider>``, ``useGlobalFilters``, ``dateRangeFromPreset``,
 * ``BUDGET_GROUP_OPTIONS`` imports continue to resolve to this unified
 * implementation. The old files have a header banner calling out that
 * they are deprecation shims.
 *
 * New code should import from ``@/components/ui/AtlasFilterContext``
 * directly. New pages can render ``<AtlasFilterProvider>`` and use
 * ``useAtlasFilters()`` to access all 8 fields.
 */

/** Valid presets — used to validate URL search param. */
const VALID_PRESETS: ReadonlySet<string> = new Set<TimeRangePreset>([
  '7D', '30D', '90D', 'MTD', 'QTD', 'YTD', '1Y', 'ALL',
])

export interface AtlasFilterState {
  /** Global time range preset. URL-synced via ``?range=...``. */
  timeRange: TimeRangePreset
  setTimeRange: (preset: TimeRangePreset) => void
  /** URL-synced comparison intent; pages opt in only when it changes their query. */
  isComparing: boolean
  setIsComparing: (enabled: boolean) => void
  /** Filter to a single account (null = all accounts). */
  selectedAccountId: number | null
  setSelectedAccountId: (id: number | null) => void
  /** Filter to a single account type (null = all types). */
  selectedAccountType: string | null
  setSelectedAccountType: (type: string | null) => void
  /** Filter to a budget group (null = all groups). */
  selectedBudgetGroup: string | null
  setSelectedBudgetGroup: (group: string | null) => void
  /** Filter to a single category (null = all categories). */
  selectedCategoryId: number | null
  setSelectedCategoryId: (id: number | null) => void
}

const AtlasFilterContext = createContext<AtlasFilterState | null>(null)

export function AtlasFilterProvider({ children }: { children: ReactNode }) {
  const searchParams = useSearchParams()
  const router = useRouter()

  // Default to YTD. The useEffect below syncs from the browser URL
  // after client hydration, which is the authoritative source.
  const [timeRange, setTimeRangeRaw] = useState<TimeRangePreset>('YTD')
  const [isComparing, setIsComparingRaw] = useState(false)
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
  const [selectedAccountType, setSelectedAccountType] = useState<string | null>(null)
  const [selectedBudgetGroup, setSelectedBudgetGroup] = useState<string | null>(null)
  const [selectedCategoryId, setSelectedCategoryId] = useState<number | null>(null)

  // Sync from browser URL on mount. Reads window.location.search directly
  // to bypass Next.js useSearchParams() timing issues inside Suspense
  // boundaries (the hook may return empty params during SSR/hydration).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const range = params.get('range')
    if (range && VALID_PRESETS.has(range)) {
      setTimeRangeRaw(range as TimeRangePreset)
    }
    setIsComparingRaw(params.get('compare') === 'true')
  }, [])

  // Update both state and URL search param on change.
  const searchParamString = searchParams.toString()
  const searchParamsRef = useRef(new URLSearchParams(searchParamString))
  useEffect(() => { searchParamsRef.current = new URLSearchParams(searchParamString) }, [searchParamString])

  // Keep a local pending query snapshot so back-to-back controls cannot lose
  // each other's change while Next refreshes useSearchParams after replace().
  const replaceQuery = useCallback((update: (params: URLSearchParams) => void) => {
    const params = new URLSearchParams(searchParamsRef.current.toString())
    update(params)
    searchParamsRef.current = params
    router.replace(`?${params.toString()}`, { scroll: false })
  }, [router])

  const setTimeRange = useCallback(
    (preset: TimeRangePreset) => {
      setTimeRangeRaw(preset)
      replaceQuery((params) => params.set('range', preset))
    },
    [replaceQuery],
  )

  const setIsComparing = useCallback(
    (enabled: boolean) => {
      setIsComparingRaw(enabled)
      replaceQuery((params) => {
        if (enabled) params.set('compare', 'true')
        else params.delete('compare')
      })
    },
    [replaceQuery],
  )

  const value = useMemo(
    () => ({
      timeRange,
      setTimeRange,
      isComparing,
      setIsComparing,
      selectedAccountId,
      setSelectedAccountId,
      selectedAccountType,
      setSelectedAccountType,
      selectedBudgetGroup,
      setSelectedBudgetGroup,
      selectedCategoryId,
      setSelectedCategoryId,
    }),
    [timeRange, setTimeRange, isComparing, setIsComparing, selectedAccountId, selectedAccountType, selectedBudgetGroup, selectedCategoryId],
  )

  return (
    <AtlasFilterContext.Provider value={value}>
      {children}
    </AtlasFilterContext.Provider>
  )
}

export function useAtlasFilters(): AtlasFilterState {
  const ctx = useContext(AtlasFilterContext)
  if (!ctx) throw new Error('useAtlasFilters must be used within <AtlasFilterProvider>')
  return ctx
}

/**
 * Derive ISO date strings (YYYY-MM-DD) from a TimeRangePreset.
 * Returns ``{ from, to }`` suitable for API query params.
 *
 * Lifted from the old ``GlobalFilterContext`` so the back-compat
 * re-export resolves correctly. New code can import it from
 * ``@/components/ui/AtlasFilterContext`` directly.
 */
export function dateRangeFromPreset(preset: string): { from: string; to: string } {
  const now = new Date()
  const to = now.toISOString().slice(0, 10)
  let from: string

  switch (preset) {
    case '7D': {
      const d = new Date(now)
      d.setDate(d.getDate() - 7)
      from = d.toISOString().slice(0, 10)
      break
    }
    case '30D': {
      const d = new Date(now)
      d.setDate(d.getDate() - 30)
      from = d.toISOString().slice(0, 10)
      break
    }
    case '90D': {
      const d = new Date(now)
      d.setDate(d.getDate() - 90)
      from = d.toISOString().slice(0, 10)
      break
    }
    case 'MTD': {
      from = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
      break
    }
    case 'QTD': {
      const qMonth = Math.floor(now.getMonth() / 3) * 3
      from = `${now.getFullYear()}-${String(qMonth + 1).padStart(2, '0')}-01`
      break
    }
    case 'YTD': {
      from = `${now.getFullYear()}-01-01`
      break
    }
    case '1Y': {
      const d = new Date(now)
      d.setFullYear(d.getFullYear() - 1)
      from = d.toISOString().slice(0, 10)
      break
    }
    case 'ALL':
    default:
      from = '2000-01-01'
      break
  }

  return { from, to }
}

/** Budget group filter options — comprehensive taxonomy. */
export const BUDGET_GROUP_OPTIONS = [
  { value: 'fixed', label: 'Fixed' },
  { value: 'flexible', label: 'Flexible' },
  { value: 'debt', label: 'Debt' },
  { value: 'savings', label: 'Savings' },
  { value: 'other', label: 'Other' },
] as const
