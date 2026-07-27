'use client'

import { useMemo, useState, useCallback, useId } from 'react'
import { motion } from 'framer-motion'
import { useReducedMotion } from '@/lib/motion'
import { formatNumber } from '@/lib/format'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface RadialCategoryDatum {
  id: string
  name: string
  value: number
  color: string
}

interface RadialCategoryChartProps {
  data: RadialCategoryDatum[]
  /** Width/height in px. Responsive parent must size the container. */
  size?: number
  /** Thickness of the donut ring. */
  thickness?: number
  /** Called when a segment is clicked. */
  onSelect?: (datum: RadialCategoryDatum) => void
  /** Currently active/hovered id for controlled highlighting. */
  activeId?: string | null
  className?: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function polarToCartesian(cx: number, cy: number, r: number, angle: number) {
  return {
    x: cx + r * Math.cos(angle),
    y: cy + r * Math.sin(angle),
  }
}

function describeArc(
  cx: number,
  cy: number,
  innerR: number,
  outerR: number,
  startAngle: number,
  endAngle: number,
) {
  const startOuter = polarToCartesian(cx, cy, outerR, endAngle)
  const endOuter = polarToCartesian(cx, cy, outerR, startAngle)
  const startInner = polarToCartesian(cx, cy, innerR, endAngle)
  const endInner = polarToCartesian(cx, cy, innerR, startAngle)

  const largeArc = endAngle - startAngle <= Math.PI ? 0 : 1

  return [
    `M ${startOuter.x} ${startOuter.y}`,
    `A ${outerR} ${outerR} 0 ${largeArc} 0 ${endOuter.x} ${endOuter.y}`,
    `L ${endInner.x} ${endInner.y}`,
    `A ${innerR} ${innerR} 0 ${largeArc} 1 ${startInner.x} ${startInner.y}`,
    'Z',
  ].join(' ')
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function RadialCategoryChart({
  data,
  size = 320,
  thickness = 44,
  onSelect,
  activeId,
  className = '',
}: RadialCategoryChartProps) {
  const reduced = useReducedMotion()
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const instanceId = useId().replace(/:/g, '')

  const { total, arcs, center } = useMemo(() => {
    const totalValue = data.reduce((s, d) => s + d.value, 0)
    const radius = size / 2
    const cx = radius
    const cy = radius
    const innerR = radius - thickness
    const outerR = radius

    let currentAngle = -Math.PI / 2
    const generated = data.map((datum) => {
      const share = totalValue > 0 ? datum.value / totalValue : 0
      const sweep = share * Math.PI * 2
      const start = currentAngle
      const end = currentAngle + sweep
      currentAngle = end
      return {
        datum,
        path: describeArc(cx, cy, innerR, outerR, start, end),
        midAngle: start + sweep / 2,
        share,
      }
    })

    return { total: totalValue, arcs: generated, center: { x: cx, y: cy } }
  }, [data, size, thickness])

  const handleClick = useCallback(
    (datum: RadialCategoryDatum) => {
      onSelect?.(datum)
    },
    [onSelect],
  )

  const effectiveActiveId = activeId ?? hoveredId

  return (
    <div className={`relative ${className}`} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Spending by category radial chart">
        <defs>
          {/* Subtle 3D bevel gradient for each segment */}
          {data.map((d, i) => (
            <radialGradient id={`${instanceId}-segment-gradient-${i}`} key={d.id} cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor={d.color} stopOpacity={0.95} />
              <stop offset="80%" stopColor={d.color} stopOpacity={0.85} />
              <stop offset="100%" stopColor={d.color} stopOpacity={0.6} />
            </radialGradient>
          ))}
          {/* Soft shadow/glow filter */}
          <filter id={`${instanceId}-radial-glow`} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur in="SourceAlpha" stdDeviation="4" result="blur" />
            <feOffset in="blur" dx="0" dy="2" result="offsetBlur" />
            <feFlood floodColor="rgba(0,0,0,0.25)" result="color" />
            <feComposite in="color" in2="offsetBlur" operator="in" result="shadow" />
            <feMerge>
              <feMergeNode in="shadow" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Background ring */}
        <circle
          cx={center.x}
          cy={center.y}
          r={size / 2 - thickness / 2}
          fill="none"
          stroke="var(--bg-tertiary)"
          strokeWidth={thickness}
          opacity={0.5}
        />

        {/* Animated segments */}
        {arcs.map(({ datum, path, midAngle }, i) => {
          const isActive = effectiveActiveId === datum.id
          const isDimmed = effectiveActiveId != null && !isActive
          const [x, y] = isActive && !reduced
            ? [Math.cos(midAngle) * 6, Math.sin(midAngle) * 6]
            : [0, 0]

          return (
            <motion.path
              key={datum.id}
              d={path}
              fill={`url(#${instanceId}-segment-gradient-${i})`}
              stroke="var(--bg-primary)"
              strokeWidth={2}
              className="focus:outline-none focus:stroke-[var(--primary-500)] focus:stroke-[4px]"
              style={{
                cursor: onSelect ? 'pointer' : 'default',
                filter: isActive ? `url(#${instanceId}-radial-glow)` : undefined,
              }}
              initial={reduced ? false : { opacity: 0, scale: 0.9 }}
              animate={{
                opacity: isDimmed ? 0.35 : 1,
                scale: 1,
                x,
                y,
              }}
              transition={
                reduced
                  ? { duration: 0 }
                  : {
                      opacity: { duration: 0.2 },
                      scale: { type: 'spring', stiffness: 260, damping: 24 },
                      x: { type: 'spring', stiffness: 300, damping: 22 },
                      y: { type: 'spring', stiffness: 300, damping: 22 },
                    }
              }
              whileHover={reduced ? undefined : { scale: 1.02 }}
              whileTap={reduced ? undefined : { scale: 0.97 }}
              onMouseEnter={() => setHoveredId(datum.id)}
              onMouseLeave={() => setHoveredId((prev) => (prev === datum.id ? null : prev))}
              onClick={() => handleClick(datum)}
              role="button"
              aria-label={`${datum.name}: ${formatNumber(datum.value)}`}
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  handleClick(datum)
                }
              }}
            />
          )
        })}
      </svg>

      {/* Center label */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="text-center">
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">Total</p>
          <p className="text-lg font-bold tabular-nums text-[var(--text-primary)]">
            {formatNumber(total)}
          </p>
        </div>
      </div>
    </div>
  )
}
