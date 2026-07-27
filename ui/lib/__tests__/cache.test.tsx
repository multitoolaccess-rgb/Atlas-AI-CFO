/**
 * Regression guard for ui/lib/cache.ts: the floating time-range bar on
 * /overview (and any page with useCachedFetch + a range dep) must
 * refetch when the range changes, not return cached data from the
 * previous range.
 *
 * Bug history: `useCachedFetch` keyed its module-level cache by
 * `group:cacheKey` (no deps). Switching timeRange from `YTD` to `30D`
 * re-triggered the useEffect but `fullKey` stayed the same, so
 * `cacheGet(fullKey)` returned the previous range's data as fresh and
 * the hook short-circuited without refetching. This suite locks in
 * the correct behavior: deps change → different cache entries →
 * refetch fires.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useCachedFetch, cacheInvalidate } from '../cache'

beforeEach(() => {
  // Module-level Map cache survives across tests; clear before each.
  cacheInvalidate()
  vi.useRealTimers()
})

describe('useCachedFetch — cache key is scoped by deps', () => {
  it('refetches when the deps array changes (time-range change)', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce('YTD data')
      .mockResolvedValueOnce('30D data')

    const { result, rerender } = renderHook(
      ({ timeRange }: { timeRange: 'YTD' | '30D' }) =>
        useCachedFetch('dashboard-flow', fetcher, [timeRange]),
      { initialProps: { timeRange: 'YTD' } },
    )

    // First mount with deps=[YTD] → fetches and caches under the
    // YTD-scoped cache key.
    await waitFor(() => expect(result.current.data).toBe('YTD data'))
    expect(fetcher).toHaveBeenCalledTimes(1)

    // Switching to 30D must NOT return the YTD-data from cache.
    rerender({ timeRange: '30D' })

    await waitFor(() => expect(result.current.data).toBe('30D data'))
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('re-uses cached data when deps revert to a previously-fetched value', async () => {
    // Bonus lock-in: with deps scoped into the key, switching the bar
    // and switching it BACK should hit the cache on return — no
    // duplicate network round trip. (This is what TanStack/SWR users
    // expect from key-scoped caches.)
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce('YTD data')
      .mockResolvedValueOnce('30D data')

    const { result, rerender } = renderHook(
      ({ timeRange }: { timeRange: 'YTD' | '30D' }) =>
        useCachedFetch('dashboard-flow', fetcher, [timeRange]),
      { initialProps: { timeRange: 'YTD' } },
    )

    await waitFor(() => expect(result.current.data).toBe('YTD data'))
    expect(fetcher).toHaveBeenCalledTimes(1)

    rerender({ timeRange: '30D' })
    await waitFor(() => expect(result.current.data).toBe('30D data'))
    expect(fetcher).toHaveBeenCalledTimes(2)

    // Step back to YTD — instant cache hit on the entry we created
    // on first mount, no third fetch.
    rerender({ timeRange: 'YTD' })
    await waitFor(() => expect(result.current.data).toBe('YTD data'))
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('does not refetch when the deps array is structurally identical across re-renders', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce('payload')

    const { result, rerender } = renderHook(
      ({ unused }: { unused: number }) =>
        useCachedFetch('stable-key', fetcher, ['YTD']),
      { initialProps: { unused: 1 } },
    )

    await waitFor(() => expect(result.current.data).toBe('payload'))
    expect(fetcher).toHaveBeenCalledTimes(1)

    // Force a parent re-render with a different prop; the deps array
    // literally contains the same string, so the cache key must
    // stay identical and the hook must not refetch.
    rerender({ unused: 2 })
    // Wait a few ticks for any spurious effect to fire.
    await new Promise((r) => setTimeout(r, 30))
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('uses the group prefix before deps, so two groups with the same cacheKey do NOT collide', async () => {
    // The fix appends depsKey AFTER the group colon (e.g.
    // `dashboard:foo:[YTD]` vs `analytics:foo:[YTD]`), so different
    // groups stay isolated even when the inner cacheKey is identical.
    const fetcher = vi.fn().mockResolvedValue('payload')

    renderHook(
      () => useCachedFetch('dup-key', fetcher, ['YTD'], { group: 'dashboard' }),
    )
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1))

    renderHook(
      () => useCachedFetch('dup-key', fetcher, ['YTD'], { group: 'analytics' }),
    )
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2))

    // No group at all → distinct key from `dup-key:[YTD]`.
    renderHook(() => useCachedFetch('dup-key', fetcher, ['YTD']))
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3))
  })
})
