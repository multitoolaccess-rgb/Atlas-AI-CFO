'use client'

import type { HTMLAttributes, ReactNode } from 'react'

type SurfaceRole = 'ambient' | 'working' | 'focal'

interface SurfaceProps extends HTMLAttributes<HTMLDivElement> {
  surfaceRole?: SurfaceRole
  children: ReactNode
}

/**
 * Shared surface vocabulary. Use tonal role before adding borders or shadow;
 * focal is reserved for decisions, primary intelligence, and guided states.
 */
export default function Surface({ surfaceRole = 'working', children, className = '', ...props }: SurfaceProps) {
  return (
    <div className={`surface-${surfaceRole} ${className}`.trim()} {...props}>
      {children}
    </div>
  )
}
