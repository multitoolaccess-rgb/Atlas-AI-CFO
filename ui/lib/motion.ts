/**
 * Motion utilities — SSR-safe, reduced-motion aware wrappers around Framer Motion.
 *
 * Why this file exists:
 * - Next.js renders components on the server. Framer Motion's `motion` components
 *   render the same markup server/client, but hooks like `useReducedMotion` and
 *   any `window`/`matchMedia` access must only run on the client.
 * - We centralize the reduced-motion check here so every animated component
 *   degrades gracefully without duplicating logic.
 */

'use client'

import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useReducedMotion } from '@/lib/useReducedMotion'

/** Convenience re-exports so consumers import from one place. */
export { motion, AnimatePresence }

/** Re-export the existing reduced-motion hook so all motion utilities
 * share a single source of truth. */
export { useReducedMotion }

/** Hook: true once the component has mounted on the client.
 * Use this to gate any client-only motion/ measurement. */
export function useHasMounted(): boolean {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  return mounted
}

/** Pick a reasonable entrance animation variant based on reduced-motion.
 * Returns static initial/final states so the server render matches. */
export function useSafeEntranceVariants() {
  const reduced = useReducedMotion()
  return {
    hidden: reduced ? { opacity: 0.9 } : { opacity: 0, y: 16, scale: 0.98 },
    visible: { opacity: 1, y: 0, scale: 1 },
  }
}

/** Spring config tuned for dashboard data viz (snappy, not bouncy). */
export const springConfig = {
  type: 'spring' as const,
  stiffness: 260,
  damping: 24,
}

/** Gentler spring for large layout shifts. */
export const softSpringConfig = {
  type: 'spring' as const,
  stiffness: 180,
  damping: 28,
}

/** Reusable hover/tap scale that respects reduced motion. */
export function useInteractiveScale() {
  const reduced = useReducedMotion()
  return reduced ? undefined : { scale: 1.03 }
}
