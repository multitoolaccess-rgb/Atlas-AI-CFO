'use client'

import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from '@/lib/useReducedMotion'

/**
 * Subtle count-up animation — animates a number from 0 (or a start value)
 * to ``end`` over ``duration`` milliseconds.
 *
 * Uses ``requestAnimationFrame`` with an ease-out cubic curve so the
 * animation decelerates towards the target — reads as polished, not
 * distracting. Respects ``prefers-reduced-motion`` by jumping straight
 * to the final value.
 *
 * Renders an inline ``<span>`` with ``tabular-nums`` so the digits stay
 * fixed-width during the animation (no layout shift as the number grows).
 * Accepts an optional ``className`` for additional styling.
 */
interface CountUpProps {
  /** Target number to count up to. */
  end: number
  /** Starting value (default 0). */
  start?: number
  /** Animation duration in ms (default 800). */
  duration?: number
  /** Optional className appended to the span. */
  className?: string
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3)
}

export default function CountUp({
  end,
  start = 0,
  duration = 800,
  className,
}: CountUpProps) {
  const [value, setValue] = useState(start)
  const rafRef = useRef(0)
  const startTimeRef = useRef<number | null>(null)

  // Resolve reduced-motion preference after mount so the server and
  // initial client render agree. useReducedMotion defaults to false on
  // the server and updates once the media query is available.
  const reducedMotion = useReducedMotion()

  useEffect(() => {
    if (reducedMotion) {
      setValue(end)
      return
    }

    const range = end - start
    if (range === 0) {
      setValue(end)
      return
    }

    // Reset on start change (e.g. re-fetch)
    startTimeRef.current = null

    const animate = (timestamp: number) => {
      if (startTimeRef.current === null) {
        startTimeRef.current = timestamp
      }
      const elapsed = timestamp - startTimeRef.current
      const progress = Math.min(elapsed / duration, 1)
      const eased = easeOutCubic(progress)
      const current = Math.round(start + range * eased)
      setValue(current)

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate)
      } else {
        // Ensure we land exactly on the target
        setValue(end)
      }
    }

    rafRef.current = requestAnimationFrame(animate)

    return () => {
      cancelAnimationFrame(rafRef.current)
    }
  }, [end, start, duration, reducedMotion])

  return (
    <span className={`tabular-nums ${className ?? ''}`}>
      {value.toLocaleString('en-US')}
    </span>
  )
}
