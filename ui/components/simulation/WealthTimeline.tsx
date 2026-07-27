'use client'

import { useMemo } from 'react'
import { useSimulation } from './WealthSimulationContext'
import CountUp from '@/components/ui/CountUp'

/**
 * Phase 5 — WealthTimeline.
 *
 * Horizontal interactive timeline showing the user's net-worth journey:
 *   - Past: trend points from ``DashboardTrendsResponse.trends`` (12 months).
 *   - Present: current net worth (the boundary between past and future).
 *   - Future: 10-year projection computed by the simulation context so it
 *     reflects any active scenario or slider adjustment.
 *
 * The curve is drawn as an SVG `<path>` with a smooth bezier through the
 * data points. Hover/tap on a year-marker shows a tooltip with the year
 * and value. The "Present" marker is emphasized with a glow ring; future
 * markers use the cyan AI accent so the aura reads as "scanned future".
 *
 * data-testid surface:
 *   - ``wealth-timeline`` — root container
 *   - ``wealth-timeline-now`` — "Now" marker
 *   - ``wealth-timeline-marker-{y}`` — each year marker
 */

export interface TimelinePoint {
  /** Years from now (negative = past, 0 = now, positive = future). */
  yearOffset: number
  /** Net worth at that point in USD. */
  value: number
  /** "actual" for past (from the trends data), "projected" for future. */
  kind: 'actual' | 'projected' | 'now'
}

export interface WealthTimelineProps {
  /** Past monthly trend points (most recent first or last, both fine). */
  pastTrends?: Array<{ month: string; netWorth?: number | null }>
  /** Current net worth; falls back to 0. */
  netWorth: number
  /** Number of future years to project. Default 10. */
  futureYears?: number
  className?: string
}

const VIEW_W = 720
const VIEW_H = 220
const PAD_X = 32
const PAD_TOP = 28
const PAD_BOT = 36

function buildPath(points: Array<{ x: number; y: number }>): string {
  if (points.length === 0) return ''
  let d = `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1]
    const next = points[i]
    const cpx = (prev.x + next.x) / 2
    d += ` C ${cpx.toFixed(2)} ${prev.y.toFixed(2)}, ${cpx.toFixed(2)} ${next.y.toFixed(2)}, ${next.x.toFixed(2)} ${next.y.toFixed(2)}`
  }
  return d
}

export default function WealthTimeline({
  pastTrends = [],
  netWorth,
  futureYears = 10,
  className,
}: WealthTimelineProps) {
  const sim = useSimulation()

  const data = useMemo(() => {
    // Past: last 12 months from `pastTrends`, treat as years from now by
    // mapping each month to monthIndex. Use a 12-month → yearOffset -1..-1/12
    // mapping so the X-axis spacing stays roughly linear.
    const past: TimelinePoint[] = pastTrends.slice(-12).map((p, i, arr) => ({
      yearOffset: -((arr.length - i) / 12),
      value: p.netWorth ?? null,
      kind: 'actual',
    })).filter((p): p is TimelinePoint => p.value != null)

    // Now
    const now: TimelinePoint = { yearOffset: 0, value: netWorth, kind: 'now' }

    // Future: simulate per-year calls (cached via useMemo on inputs).
    const future: TimelinePoint[] = []
    for (let y = 1; y <= futureYears; y++) {
      future.push({
        yearOffset: y,
        value: sim.projectedNetWorthAt(y, { netWorth }),
        kind: 'projected',
      })
    }

    const all: TimelinePoint[] = [...past, now, ...future]
    return all
  }, [pastTrends, netWorth, futureYears, sim])

  // Project to SVG coords
  const projected = useMemo(() => {
    if (data.length === 0) return { points: [], path: '', areaPath: '', yMin: 0, yMax: 1 }
    const yearOffsets = data.map((p) => p.yearOffset)
    const values = data.map((p) => p.value)
    const yMin = Math.min(...values, 0)
    const yMax = Math.max(...values, 1)
    const xMin = Math.min(...yearOffsets)
    const xMax = Math.max(...yearOffsets)
    const xSpan = xMax - xMin || 1
    const ySpan = yMax - yMin || 1

    const pts = data.map((p) => ({
      x: PAD_X + ((p.yearOffset - xMin) / xSpan) * (VIEW_W - 2 * PAD_X),
      y: PAD_TOP + (1 - (p.value - yMin) / ySpan) * (VIEW_H - PAD_TOP - PAD_BOT),
      ...p,
    }))

    const path = buildPath(pts)
    // Area path: path + line down to baseline
    const last = pts[pts.length - 1]
    const first = pts[0]
    const areaPath = `${path} L ${last.x.toFixed(2)} ${(VIEW_H - PAD_BOT).toFixed(2)} L ${first.x.toFixed(2)} ${(VIEW_H - PAD_BOT).toFixed(2)} Z`

    return { points: pts, path, areaPath, yMin, yMax }
  }, [data])

  if (data.length === 0) {
    return (
      <div className={`card p-6 ${className ?? ''}`} aria-busy="true" data-testid="wealth-timeline-loading">
        <div className="skeleton h-6 w-1/3 mb-4" />
        <div className="skeleton h-[220px] w-full" />
      </div>
    )
  }

  return (
    <div className={`card p-6 ${className ?? ''}`} data-testid="wealth-timeline">
      <div className="flex-between mb-4">
        <div>
          <h3 className="headline-md text-primary">Wealth Timeline</h3>
          <p className="body-sm text-on-surface-variant">
            Past → Present → Future. {sim.activeScenario
              ? `Reflects "${sim.activeScenario}" scenario.`
              : 'Adjust sliders to test scenarios.'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-on-surface-variant tabular-nums">
            ${Math.round(projected.yMin).toLocaleString('en-US')} – ${Math.round(projected.yMax).toLocaleString('en-US')}
          </span>
          <div className="hidden sm:flex items-center gap-2 text-xs">
            <span className="inline-flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-full bg-[var(--primary-500)]" />
              Actual
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-full bg-[var(--accent-cyan)]" />
              Projected
            </span>
          </div>
        </div>
      </div>

      <div className="relative w-full overflow-x-auto">
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          className="w-full h-auto"
          preserveAspectRatio="none"
          aria-label="Wealth timeline showing past, present, and projected net worth"
        >
          <defs>
            <linearGradient id="wt-area-gradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent-electric)" stopOpacity="0.25" />
              <stop offset="100%" stopColor="var(--accent-electric)" stopOpacity="0" />
            </linearGradient>
            <linearGradient id="wt-line-gradient" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="var(--primary-500)" />
              <stop offset="100%" stopColor="var(--accent-cyan)" />
            </linearGradient>
          </defs>

          {/* Area fill */}
          <path d={projected.areaPath} fill="url(#wt-area-gradient)" />

          {/* Curve */}
          <path
            d={projected.path}
            fill="none"
            stroke="url(#wt-line-gradient)"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Year markers */}
          {projected.points.map((p) => {
            const isNow = p.kind === 'now'
            const color =
              p.kind === 'projected'
                ? 'var(--accent-cyan)'
                : isNow
                  ? 'var(--accent-gold, var(--warning-500))'
                  : 'var(--primary-500)'
            const r = isNow ? 6 : 3.5
            return (
              <g key={`m-${p.yearOffset}`}>
                {isNow && (
                  <circle
                    cx={p.x}
                    cy={p.y}
                    r={r + 6}
                    fill="none"
                    stroke={color}
                    strokeOpacity="0.35"
                    strokeWidth="1.5"
                  />
                )}
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={r}
                  fill={color}
                  data-testid={`wealth-timeline-marker-${p.yearOffset.toFixed(2)}`}
                />
                {isNow && (
                  <text
                    x={p.x}
                    y={p.y - 12}
                    textAnchor="middle"
                    fontSize="10"
                    fontWeight="600"
                    fill="var(--text-primary)"
                    data-testid="wealth-timeline-now"
                  >
                    Now
                  </text>
                )}
              </g>
            )
          })}

          {/* X-axis baseline */}
          <line
            x1={PAD_X}
            y1={VIEW_H - PAD_BOT}
            x2={VIEW_W - PAD_X}
            y2={VIEW_H - PAD_BOT}
            stroke="var(--border-color)"
            strokeOpacity="0.4"
          />
        </svg>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-on-surface-variant">
        <span>
          {futureYears}-year projected:
          <span className="ml-1 text-primary font-semibold tabular-nums">
            <CountUp end={sim.projectedNetWorthAt(futureYears, { netWorth })} duration={900} className="text-primary font-semibold" />
          </span>
        </span>
        <span>
          Δ vs now:
          <span className="ml-1 font-semibold tabular-nums text-[var(--accent-cyan)]">
            +${Math.round(sim.projectedNetWorthAt(futureYears, { netWorth }) - netWorth).toLocaleString('en-US')}
          </span>
        </span>
      </div>
    </div>
  )
}
