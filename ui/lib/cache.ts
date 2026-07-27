/**
 * Lightweight API response cache for the frontend.
 *
 * Provides a `useCachedFetch` hook that caches API responses in a
 * module-level Map with configurable TTL (default 5 min). Integrates
 * with the existing `dataRefresh` bus so mutations invalidate stale
 * entries automatically.
 *
 * Usage:
 *   const { data, loading, error, refetch } = useCachedFetch(
 *     'dashboard-summary',
 *     () => rulesService.getDashboardSummary(),
 *     [retryCount],
 *   )
 *
 * Design choices:
 *   - Module-level cache (not React state) so entries survive across
 *     page navigations — the user visiting /activity then back to /
 *     gets instant cached data instead of a loading spinner.
 *   - Stale-while-revalidate: returns cached data immediately, then
 *     refetches in background if stale (TTL expired).
 *   - Integrates with `onDataRefresh` so a file upload on /activity
 *     invalidates the dashboard cache on next visit.
 *   - No external dependencies (no TanStack Query, no SWR).
 */

'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { onDataRefresh } from './dataRefresh'

// ---- Cache store --------------------------------------------------------

interface CacheEntry<T> {
  data: T
  timestamp: number
  /** In-flight promise for deduplication. */
  inflight: Promise<T> | null
}

const _cache = new Map<string, CacheEntry<unknown>>()

/** Default TTL: 5 minutes. Short enough for a finance app; long enough
 *  to eliminate redundant fetches during a single session. */
const DEFAULT_TTL_MS = 5 * 60 * 1000

/** Read from cache. Returns null if missing or expired.
 *  Pure read — does NOT delete expired entries (that would be a
 *  surprising side effect for a "get"). Use `cacheInvalidate` to
 *  explicitly remove entries. */
function cacheGet<T>(key: string, ttlMs: number): T | null {
  const entry = _cache.get(key) as CacheEntry<T> | undefined
  if (!entry) return null
  if (Date.now() - entry.timestamp > ttlMs) return null
  return entry.data
}

/** Write to cache. */
function cacheSet<T>(key: string, data: T): void {
  _cache.set(key, { data, timestamp: Date.now(), inflight: null })
}

/** Invalidate entries matching a prefix (or all if no prefix). */
export function cacheInvalidate(prefix?: string): void {
  if (!prefix) {
    _cache.clear()
    return
  }
  for (const key of _cache.keys()) {
    if (key.startsWith(prefix)) _cache.delete(key)
  }
}

/** Get or compute: returns cached data if fresh, otherwise calls fetcher
 *  and caches the result. Deduplicates in-flight requests. */
async function cacheGetOrCompute<T>(
  key: string,
  fetcher: () => Promise<T>,
  ttlMs: number,
): Promise<T> {
  const cached = cacheGet<T>(key, ttlMs)
  if (cached !== null) return cached

  const entry = _cache.get(key) as CacheEntry<T> | undefined
  if (entry?.inflight) return entry.inflight

  const promise = fetcher().then((data) => {
    cacheSet(key, data)
    return data
  }).finally(() => {
    const e = _cache.get(key) as CacheEntry<T> | undefined
    if (e) e.inflight = null
  })

  // Store inflight promise for deduplication
  const existing = _cache.get(key) as CacheEntry<T> | undefined
  if (existing) {
    existing.inflight = promise
  } else {
    _cache.set(key, { data: undefined as unknown as T, timestamp: 0, inflight: promise })
  }

  return promise
}

// ---- Hook ---------------------------------------------------------------

interface UseCachedFetchOptions {
  /** Cache TTL in milliseconds. Default: 5 minutes. */
  ttlMs?: number
  /** When false, skip the fetch entirely (e.g. when parent is loading). */
  enabled?: boolean
  /** Cache key prefix for invalidation grouping. */
  group?: string
}

interface UseCachedFetchResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  refetch: () => void
}

/**
 * Fetch with caching, stale-while-revalidate, and dataRefresh integration.
 *
 * @param cacheKey  Unique key for this query (e.g. 'dashboard-summary').
 * @param fetcher   Async function that returns the data.
 * @param deps      Dependency array — refetches when these change (like useEffect).
 * @param options   Cache options (TTL, enabled, group).
 */
export function useCachedFetch<T>(
  cacheKey: string,
  fetcher: () => Promise<T>,
  deps: unknown[],
  options: UseCachedFetchOptions = {},
): UseCachedFetchResult<T> {
  const { ttlMs = DEFAULT_TTL_MS, enabled = true, group } = options
  // Cache key MUST include deps, otherwise changing the floating
  // time-range bar (or any other dependency that influences the
  // fetched data) makes `cacheGet(fullKey)` return the previous
  // range's payload as fresh, and `fetchData` short-circuits without
  // hitting the API. The hot-path regression this prevents: clicking
  // 30D on /overview kept rendering the YTD dataset. Format keeps the
  // `group:` prefix when present so different domains stay isolated
  // even with identical inner cacheKey+deps.
  //   group present:   `<group>:<cacheKey>:<depsKey>`
  //   group absent:    `<cacheKey>:<depsKey>`
  const depsKey = JSON.stringify(deps)
  const fullKey = group ? `${group}:${cacheKey}:${depsKey}` : `${cacheKey}:${depsKey}`

  const [data, setData] = useState<T | null>(() => cacheGet<T>(fullKey, ttlMs))
  const [loading, setLoading] = useState<boolean>(() => !cacheGet<T>(fullKey, ttlMs))
  const [error, setError] = useState<string | null>(null)
  const [, forceUpdate] = useState(0)
  const mountedRef = useRef(true)
  // Store fetcher in a ref so inline arrow functions don't cause
  // infinite refetch loops (new reference on every render). Only
  // the cacheKey and deps control when to refetch.
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  // Stale-while-revalidate: if we have cached data but it's stale,
  // show the stale data immediately and refetch in background.
  const fetchData = useCallback(async () => {
    if (!enabled) return

    const stale = cacheGet<T>(fullKey, ttlMs + 60_000) // 1 min grace for stale data
    const fresh = cacheGet<T>(fullKey, ttlMs)

    if (fresh !== null) {
      // Fully fresh — no fetch needed
      setData(fresh)
      setLoading(false)
      return
    }

    if (stale !== null) {
      // Stale but usable — show stale, refetch in background
      setData(stale)
      setLoading(false)
    } else {
      setLoading(true)
    }

    setError(null)
    try {
      const result = await cacheGetOrCompute(fullKey, fetcherRef.current, ttlMs)
      if (!mountedRef.current) return
      setData(result)
      setLoading(false)
      // Force re-render to pick up cache
      forceUpdate((n) => n + 1)
    } catch (err: unknown) {
      if (!mountedRef.current) return
      const msg = err instanceof Error ? err.message : 'Fetch failed'
      setError(msg)
      setLoading(false)
    }
  }, [fullKey, ttlMs, enabled])

  const refetch = useCallback(() => {
    cacheInvalidate(fullKey)
    fetchData()
  }, [fullKey, fetchData])

  // Fetch on mount + when deps change (depsKey is a stable string)
  useEffect(() => {
    mountedRef.current = true
    fetchData()
    return () => { mountedRef.current = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchData, depsKey])

  // Invalidate cache on dataRefresh events
  useEffect(() => {
    return onDataRefresh(() => {
      cacheInvalidate(fullKey)
      fetchData()
    })
  }, [fullKey, fetchData])

  return { data, loading, error, refetch }
}

/**
 * Prefetch a cache entry without mounting a component.
 * Useful for preloading data that will be needed soon.
 */
export function cachePrefetch<T>(
  key: string,
  fetcher: () => Promise<T>,
  ttlMs: number = DEFAULT_TTL_MS,
): void {
  cacheGetOrCompute(key, fetcher, ttlMs).catch(() => {
    // Prefetch failures are silent
  })
}
