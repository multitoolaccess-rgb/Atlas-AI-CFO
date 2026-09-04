'use client'

import { useMemo, useState, useCallback, useId } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { formatCurrency } from '@/lib/format'

export interface DonutDatum {
  id: string
  name: string
  value: number
  color: string
}

interface SimpleDonutChartProps {
  data: DonutDatum[]
  size?: number
  thickness?: number
  onSelect?: (datum: DonutDatum) => void
  activeId?: string | null
  className?: string
  /** Optional center content. */
  center?: React.ReactNode
}

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

export default function SimpleDonutChart({
  data,
  size = 240,
  thickness = 40,
  onSelect,
  activeId,
  className = '',
  center,
}: SimpleDonutChartProps) {
  const reduced = useReducedMotion()
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const instanceId = useId().replace(/:/g, '')

  const { total, arcs } = useMemo(() => {
    const totalValue = data.reduce((s, d) => s + d.value, 0)
    const radius = size / 2
    const innerR = radius - thickness
    let currentAngle = -Math.PI / 2
    const generated = data.map((datum) => {
      const share = totalValue > 0 ? datum.value / totalValue : 0
      const sweep = share * Math.PI * 2
      const start = currentAngle
      const end = currentAngle + sweep
      currentAngle = end
      return {
        datum,
        path: describeArc(radius, radius, innerR, radius, start, end),
        midAngle: start + sweep / 2,
        share,
      }
    })
    return { total: totalValue, arcs: generated }
  }, [data, size, thickness])

  const handleClick = useCallback(
    (datum: DonutDatum) => onSelect?.(datum),
    [onSelect],
  )

  const effectiveActiveId = activeId ?? hoveredId

  return (
    <div className={`relative ${className}`} style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label="Donut chart"
      >
        <defs>
          {data.map((d, i) => (
            <radialGradient id={`${instanceId}-donut-grad-${i}`} key={d.id} cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor={d.color} stopOpacity={0.95} />
              <stop offset="100%" stopColor={d.color} stopOpacity={0.7} />
            </radialGradient>
          ))}
        </defs>

        {/* Track ring */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={size / 2 - thickness / 2}
          fill="none"
          stroke="var(--border-color)"
          strokeWidth={thickness}
          opacity={0.4}
        />

        {arcs.map(({ datum, path, midAngle }) => {
          const isActive = effectiveActiveId === datum.id
          const isDimmed = effectiveActiveId != null && !isActive
          const [x, y] = isActive && !reduced ? [Math.cos(midAngle) * 5, Math.sin(midAngle) * 5] : [0, 0]

          return (
            <motion.path
              key={datum.id}
              d={path}
              fill={`url(#${instanceId}-donut-grad-${arcs.findIndex((a) => a.datum.id === datum.id)})`}
              stroke="var(--bg-primary)"
              strokeWidth={2}
              className="focus:outline-none focus:stroke-[var(--primary-500)] focus:stroke-[3px]"
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
              style={{ filter: 'drop-shadow(0px 1px 2px rgba(0,0,0,0.15))', cursor: onSelect ? 'pointer' : 'default' }}
              whileHover={reduced ? undefined : { scale: 1.02 }}
              whileTap={reduced ? undefined : { scale: 0.97 }}
              onMouseEnter={() => setHoveredId(datum.id)}
              onMouseLeave={() => setHoveredId((prev) => (prev === datum.id ? null : prev))}
              onClick={() => handleClick(datum)}
              role="button"
              aria-label={`${datum.name}: ${formatCurrency(datum.value)}`}
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

      {center && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          {center}
        </div>
      )}
    </div>
  )
}
