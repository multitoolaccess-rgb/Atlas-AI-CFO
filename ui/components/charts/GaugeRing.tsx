'use client'

import { useEffect, useState } from 'react'
import { formatNumber } from '@/lib/format'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface GaugeRingProps {
  /** Current value (0–100 percentage) */
  value: number
  /** Label inside the ring */
  label: string
  /** Sub-label or status text */
  subLabel?: string
  /** Ring color — uses CSS variable or hex */
  color?: string
  /** Background ring color */
  trackColor?: string
  /** Ring size in px */
  size?: number
  /** Ring stroke width */
  strokeWidth?: number
  /** Format value as percentage or currency */
  format?: 'percent' | 'currency' | 'number'
  /** Raw value (when format is currency/number) */
  rawValue?: number
  /** Show the percentage number inside */
  showValue?: boolean
  /** Additional CSS classes */
  className?: string
  /** Enable entrance animation */
  animate?: boolean
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function GaugeRing({
  value,
  label,
  subLabel,
  color = 'var(--primary-500)',
  trackColor = 'var(--slate-200)',
  size = 120,
  strokeWidth = 8,
  format = 'percent',
  rawValue,
  showValue = true,
  className = '',
  animate = true,
}: GaugeRingProps) {
  const [animatedValue, setAnimatedValue] = useState(animate ? 0 : value)
  const safeValue = Math.min(100, Math.max(0, value))

  useEffect(() => {
    if (!animate) {
      setAnimatedValue(safeValue)
      return
    }
    // Animate from 0 to target value
    const timeout = setTimeout(() => {
      setAnimatedValue(safeValue)
    }, 100)
    return () => clearTimeout(timeout)
  }, [safeValue, animate])

  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (animatedValue / 100) * circumference
  const center = size / 2

  // Format the display value
  const displayValue = (() => {
    if ((format === 'currency' || format === 'number') && rawValue != null) {
      return formatNumber(rawValue)
    }
    return `${Math.round(animatedValue)}%`
  })()

  // Determine ring color based on value ranges
  const resolvedColor =
    color === 'auto'
      ? animatedValue >= 80
        ? 'var(--success-500)'
        : animatedValue >= 50
          ? 'var(--warning-500)'
          : 'var(--danger-500)'
      : color

  return (
    <div
      className={`flex flex-col items-center gap-2 ${className}`}
      role="meter"
      aria-valuenow={Math.round(animatedValue)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <div className="relative" style={{ width: size, height: size }}>
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="transform -rotate-90"
        >
          {/* Track ring */}
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke={trackColor}
            strokeWidth={strokeWidth}
          />
          {/* Value ring */}
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke={resolvedColor}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="butt"
            className="transition-all duration-1000 ease-out"
          />
        </svg>

        {/* Center content */}
        {showValue && (
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span
              className="font-mono font-bold tabular-nums text-[var(--text-primary)]"
              style={{ fontSize: size * 0.18 }}
            >
              {displayValue}
            </span>
            {subLabel && (
              <span
                className="text-[var(--text-tertiary)] font-medium mt-0.5"
                style={{ fontSize: Math.max(9, size * 0.09) }}
              >
                {subLabel}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Label below ring */}
      <span className="label-sm text-[var(--text-secondary)] text-center">
        {label}
      </span>
    </div>
  )
}
