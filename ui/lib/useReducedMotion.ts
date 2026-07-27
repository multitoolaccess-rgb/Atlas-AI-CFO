'use client'

import { useEffect, useState } from 'react'

/**
 * Shared hook that reads the `prefers-reduced-motion: reduce` media query.
 * Returns `true` when the user has enabled reduced motion in their OS settings.
 *
 * SSR-safe: defaults to `false` on the server, resolves on mount.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false)

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReduced(mq.matches)
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  return reduced
}
