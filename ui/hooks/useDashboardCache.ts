'use client'

import { useState, useCallback, useEffect } from 'react'

interface CacheEntry<T> {
  data: T
  timestamp: number
}

const CACHE_TTL_MS = 5 * 60 * 1000 // 5 minutes

/**
 * Hook for dashboard data caching with 5-minute TTL.
 * Provides automatic cache invalidation and refresh UI.
 */
export function useDashboardCache<T>(
  fetchFn: () => Promise<T>,
  key: string,
  enabled = true
) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<number | null>(null)
  const [isStale, setIsStale] = useState(false)

  // Load from localStorage
  const loadFromCache = useCallback((): T | null => {
    if (typeof window === 'undefined') return null
    try {
      const cached = localStorage.getItem(`cache:${key}`)
      if (!cached) return null
      const entry: CacheEntry<T> = JSON.parse(cached)
      const age = Date.now() - entry.timestamp
      if (age > CACHE_TTL_MS) {
        setIsStale(true)
        localStorage.removeItem(`cache:${key}`)
        return null
      }
      setLastUpdated(entry.timestamp)
      return entry.data
    } catch {
      return null
    }
  }, [key])

  // Save to localStorage
  const saveToCache = useCallback(
    (newData: T) => {
      if (typeof window === 'undefined') return
      try {
        const entry: CacheEntry<T> = {
          data: newData,
          timestamp: Date.now(),
        }
        localStorage.setItem(`cache:${key}`, JSON.stringify(entry))
        setLastUpdated(entry.timestamp)
        setIsStale(false)
      } catch {
        // Storage full or unavailable
      }
    },
    [key]
  )

  // Initial load
  useEffect(() => {
    if (!enabled) return

    const cached = loadFromCache()
    if (cached) {
      setData(cached)
      setLoading(false)
      return
    }

    const loadData = async () => {
      try {
        setLoading(true)
        const fresh = await fetchFn()
        setData(fresh)
        saveToCache(fresh)
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load')
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [enabled, key, fetchFn, loadFromCache, saveToCache])

  // Manual refresh
  const refresh = useCallback(async () => {
    try {
      setLoading(true)
      const fresh = await fetchFn()
      setData(fresh)
      saveToCache(fresh)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh')
    } finally {
      setLoading(false)
    }
  }, [fetchFn, saveToCache])

  // Clear cache
  const clearCache = useCallback(() => {
    if (typeof window === 'undefined') return
    localStorage.removeItem(`cache:${key}`)
    setData(null)
    setLastUpdated(null)
    setIsStale(false)
  }, [key])

  // Time since last update
  const minutesSinceUpdate =
    lastUpdated != null ? Math.floor((Date.now() - lastUpdated) / 60000) : null

  return {
    data,
    loading,
    error,
    lastUpdated,
    minutesSinceUpdate,
    isStale,
    refresh,
    clearCache,
  }
}
