'use client'

import { useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'

interface AnimatedRadialProgressProps {
  /** 0-100 */
  percentage: number
  size?: number
  strokeWidth?: number
  color?: string
  trackColor?: string
  className?: string
  label?: React.ReactNode
}

export default function AnimatedRadialProgress({
  percentage,
  size = 64,
  strokeWidth = 6,
  color = 'var(--primary-500)',
  trackColor = 'var(--bg-tertiary)',
  className = '',
  label,
}: AnimatedRadialProgressProps) {
  const reduced = useReducedMotion()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const clampedPct = Math.min(100, Math.max(0, percentage))
  const targetOffset = circumference - (clampedPct / 100) * circumference
  const initialOffset = reduced ? targetOffset : circumference

  return (
    <div
      className={`relative inline-flex items-center justify-center ${className}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={`Progress ${clampedPct.toFixed(0)}%`}
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={trackColor}
          strokeWidth={strokeWidth}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: initialOffset }}
          animate={{
            strokeDashoffset: mounted || reduced ? targetOffset : initialOffset,
          }}
          transition={
            reduced
              ? { duration: 0 }
              : { duration: 1, ease: [0.16, 1, 0.3, 1] }
          }
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      {label && (
        <div className="absolute inset-0 flex items-center justify-center">
          {label}
        </div>
      )}
    </div>
  )
}
