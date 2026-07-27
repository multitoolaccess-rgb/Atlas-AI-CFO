'use client'

import { type ReactNode } from 'react'
import { motion, useReducedMotion } from 'framer-motion'

interface AnimatedKPICardProps {
  icon: ReactNode
  label: string
  value: ReactNode
  subtext?: ReactNode
  accentClass?: string
  className?: string
  /** Renders a subtle gradient border when true. */
  highlighted?: boolean
}

export default function AnimatedKPICard({
  icon,
  label,
  value,
  subtext,
  accentClass = 'bg-primary-500',
  highlighted = false,
  className = '',
}: AnimatedKPICardProps) {
  const reduced = useReducedMotion()

  return (
    <motion.div
      className={`relative overflow-hidden rounded-xl border border-[var(--border-color)] bg-[var(--bg-secondary)] p-5 shadow-sm transition-shadow hover:shadow-lg ${className}`}
      initial={reduced ? false : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={
        reduced
          ? { duration: 0 }
          : { duration: 0.35, ease: [0.16, 1, 0.3, 1] }
      }
      whileHover={reduced ? undefined : { y: -4 }}
      whileTap={reduced ? undefined : { scale: 0.98 }}
    >
      {highlighted && (
        <div
          className={`absolute left-0 top-0 h-full w-1 ${accentClass}`}
          aria-hidden="true"
        />
      )}
      <div className="relative z-10 flex items-start justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
            {label}
          </p>
          <div className="mt-1 text-2xl font-bold tabular-nums text-[var(--text-primary)]">
            {value}
          </div>
          {subtext && (
            <div className="mt-1 text-xs font-medium text-[var(--text-secondary)]">
              {subtext}
            </div>
          )}
        </div>
        <div
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${accentClass} bg-opacity-15`}
        >
          {icon}
        </div>
      </div>
    </motion.div>
  )
}
