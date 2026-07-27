'use client'

import { Clock } from 'lucide-react'
import CountUp from '@/components/ui/CountUp'
import { useSimulation } from './WealthSimulationContext'

/**
 * Phase 5 — FinancialTwin.
 *
 * Three narrative cards projecting the user's future self at age 50,
 * 60, and 65. Each card shows the projected net worth via the shared
 * simulation context, so changes from the simulator sliders or active
 * scenarios flow through.
 *
 * The card narrative is a deterministic template that pulls from the
 * projection magnitude (large vs small) to give a "personality" line:
 *   - "You're coasting on your own momentum."
 *   - "Compound interest is doing the heavy lifting."
 *   - "High-conviction saver."
 *
 * data-testid surface:
 *   - ``financial-twin`` — root container
 *   - ``twin-card-{age}`` — each age card (50/60/65)
 *   - ``twin-card-{age}-value`` — projected value in that card
 */

interface TwinProps {
  /** The user's current age in years (used to compute yearsFromNow). */
  currentAge?: number
  /** Combined target ages to project for. */
  targetAges?: Array<50 | 60 | 65>
  className?: string
}

function narrativeFor(value: number, age: number, baseline: number): string {
  const years = age - 50
  const growthFactor = value / Math.max(1, baseline)
  if (growthFactor < 1.05) {
    return `Stretched thin over the next ${years} years — revisit the simulator.`
  }
  if (growthFactor < 2) {
    return `Modest but real compounding. Even small consistent contributions matter.`
  }
  if (growthFactor < 5) {
    return `Compound interest is doing the heavy lifting. ${Math.round(growthFactor)}× your current baseline.`
  }
  return `High-conviction saver. At this pace, you're ${Math.round(growthFactor)}× your baseline.`
}

export default function FinancialTwin({
  currentAge = 35,
  targetAges = [50, 60, 65],
  className,
}: TwinProps) {
  const sim = useSimulation()

  return (
    <div className={`card p-6 ${className ?? ''}`} data-testid="financial-twin">
      <div className="mb-4">
        <h3 className="headline-md text-primary">Your Financial Twin</h3>
        <p className="body-sm text-on-surface-variant">
          Projections for {currentAge}-year-old you at three future checkpoints.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {targetAges.map((age) => {
          const yearsFromNow = Math.max(1, age - currentAge)
          const fv = sim.projectedNetWorthAt(yearsFromNow)
          const baseline = sim.projectedNetWorthAt(yearsFromNow, { netWorth: 0 })
          return (
            <div
              key={age}
              className="rounded-[var(--radius-md)] p-4 border border-[var(--border-color)]
                         bg-[color-mix(in_srgb,var(--accent-electric)_4%,transparent)]"
              data-testid={`twin-card-${age}`}
            >
              <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-[var(--accent-electric)]">
                <Clock className="w-3.5 h-3.5" aria-hidden="true" />
                You at {age}
              </div>
              <div
                className="mt-2 text-2xl font-bold tabular-nums text-primary"
                data-testid={`twin-card-${age}-value`}
              >
                $<CountUp end={fv} duration={900} />
              </div>
              <p className="mt-2 text-xs text-on-surface-variant leading-snug">
                {narrativeFor(fv, age, baseline)}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
