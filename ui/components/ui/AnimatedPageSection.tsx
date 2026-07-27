'use client'

import { forwardRef } from 'react'
import { motion } from 'framer-motion'
import { useReducedMotion } from '@/lib/useReducedMotion'

/**
 * AnimatedPageSection
 * -------------------
 * Drop-in wrapper for page-level entrance animations. It fades and
 * slides content up while respecting the user's reduced-motion
 * preference (motion is disabled when prefers-reduced-motion is on).
 *
 * Use this instead of duplicating the same `motion.div` + useReducedMotion
 * boilerplate across every top-level page.
 */

type MotionProps = React.ComponentProps<typeof motion.div>

// Pick the props we want explicit defaults for; inherit everything
// else (including className, style, data-* attributes, etc.) from
// motion.div so the wrapper is a transparent replacement.
type AnimatedPageSectionProps = Omit<
  MotionProps,
  'children' | 'initial' | 'animate' | 'transition'
> & {
  children: React.ReactNode
  initial?: MotionProps['initial']
  animate?: MotionProps['animate']
  transition?: MotionProps['transition']
}

const AnimatedPageSection = forwardRef<
  HTMLDivElement,
  AnimatedPageSectionProps
>(
  (
    {
      children,
      initial = { opacity: 0, y: 16 },
      animate = { opacity: 1, y: 0 },
      transition,
      ...rest
    },
    ref,
  ) => {
    const reducedMotion = useReducedMotion()

    // Under reduced motion, jump straight to the final state and
    // suppress any custom transition. This also catches non-fade
    // transitions such as springs that a caller might pass.
    const finalInitial = reducedMotion ? animate : initial
    const baseTransition =
      transition ?? {
        duration: reducedMotion ? 0 : 0.4,
        ease: 'easeOut',
      }
    const finalTransition = reducedMotion
      ? { ...baseTransition, duration: 0 }
      : baseTransition

    return (
      <motion.div
        ref={ref}
        initial={finalInitial}
        animate={animate}
        transition={finalTransition}
        {...rest}
      >
        {children}
      </motion.div>
    )
  },
)

AnimatedPageSection.displayName = 'AnimatedPageSection'

export default AnimatedPageSection
