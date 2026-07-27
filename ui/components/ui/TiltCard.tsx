'use client'

import { useRef, type MouseEvent, type ReactNode } from 'react'
import { motion, useMotionValue, useSpring, useReducedMotion } from 'framer-motion'

interface TiltCardProps {
  children: ReactNode
  className?: string
  /** Max rotation in degrees. */
  tilt?: number
  onClick?: () => void
  ['data-testid']?: string
  id?: string
}

/**
 * TiltCard — 3D hover effect that follows the mouse position.
 *
 * - Uses Framer Motion motion values + springs; no React re-renders on mousemove.
 * - Disabled when the user prefers reduced motion.
 * - SSR safe: starts with no transform; tilt is computed client-side only.
 */
export default function TiltCard({
  children,
  className = '',
  tilt = 8,
  onClick,
  'data-testid': dataTestId,
  id,
}: TiltCardProps) {
  const reduced = useReducedMotion()
  const ref = useRef<HTMLDivElement>(null)

  const rawX = useMotionValue(0)
  const rawY = useMotionValue(0)

  const rotateX = useSpring(rawY, { stiffness: 200, damping: 20 })
  const rotateY = useSpring(rawX, { stiffness: 200, damping: 20 })

  const handleMouseMove = (e: MouseEvent<HTMLDivElement>) => {
    if (reduced || !ref.current) return
    const rect = ref.current.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width
    const y = (e.clientY - rect.top) / rect.height
    rawX.set((x - 0.5) * tilt)
    rawY.set((0.5 - y) * tilt)
  }

  const handleMouseLeave = () => {
    rawX.set(0)
    rawY.set(0)
  }

  return (
    <motion.div
      ref={ref}
      onClick={onClick}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{
        perspective: 1000,
        transformStyle: 'preserve-3d',
        rotateX: reduced ? 0 : rotateX,
        rotateY: reduced ? 0 : rotateY,
      }}
      whileTap={reduced ? undefined : { scale: 0.985 }}
      className={className}
      id={id}
      data-testid={dataTestId}
    >
      {children}
    </motion.div>
  )
}
