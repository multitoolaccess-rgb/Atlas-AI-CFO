'use client'

import { Sliders, RotateCcw, TrendingUp } from 'lucide-react'
import { useSimulation } from './WealthSimulationContext'
import CountUp from '@/components/ui/CountUp'

/**
 * Phase 5 — MoneyFlowSimulator.
 *
 * Three sliders that re-project the user's net worth in real time:
 *   1. Monthly contribution ($0–$5,000, step $50)
 *   2. Annual return rate (0–15%, step 0.5)
 *   3. Inflation rate (0–8%, step 0.25)
 *
 * Live preview shows projected net worth at 5y / 10y / 20y using the
 * shared simulation context's ``projectedNetWorthAt`` helper. A
 * ``Reset`` button restores the dashboard-baseline values.
 *
 * Reduced motion: transitions respecting the global media query are
 * already disabled by the project's animations.css, so slider thumbs
 * snap without animation.
 *
 * data-testid surface:
 *   - ``simulator-card``         — root container
 *   - ``simulator-slider-pmt``   — monthly contribution range
 *   - ``simulator-slider-rate``  — annual return rate range
 *   - ``simulator-slider-inflation`` — inflation rate range
 *   - ``simulator-preview-{n}y`` — each preview CountUp
 *   - ``simulator-reset``        — reset button
 */

const HORIZONS = [5, 10, 20] as const

export default function MoneyFlowSimulator({ className }: { className?: string }) {
  const sim = useSimulation()

  // Project using current simulator state + the provider's net worth baseline.
  const projections = HORIZONS.map((y) => sim.projectedNetWorthAt(y))

  return (
    <div className={`card p-6 ${className ?? ''}`} data-testid="simulator-card">
      <div className="flex-between mb-4">
        <div className="flex items-center gap-3">
          <span
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: 'color-mix(in srgb, var(--accent-electric) 12%, transparent)' }}
          >
            <Sliders className="w-4 h-4 text-[var(--accent-electric)]" aria-hidden="true" />
          </span>
          <div>
            <h3 className="headline-md text-primary">Money Flow Simulator</h3>
            <p className="body-sm text-on-surface-variant">Drag sliders to test scenarios.</p>
          </div>
        </div>
        <button
          type="button"
          onClick={sim.reset}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg
                     text-xs font-medium text-on-surface-variant
                     hover:bg-surface-container transition-colors"
          data-testid="simulator-reset"
        >
          <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
          Reset
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Monthly contribution */}
        <div>
          <div className="flex-between mb-1">
            <label htmlFor="sim-pmt" className="label-sm text-on-surface-variant">
              Monthly contribution
            </label>
            <span className="text-sm font-semibold tabular-nums text-primary">
              ${sim.monthlyContribution.toLocaleString('en-US')}
            </span>
          </div>
          <input
            id="sim-pmt"
            type="range"
            min={0}
            max={5000}
            step={50}
            value={sim.monthlyContribution}
            onChange={(e) => sim.setMonthlyContribution(Number(e.target.value))}
            className="fc-range w-full"
            data-testid="simulator-slider-pmt"
            aria-label="Monthly contribution amount in dollars"
          />
          <div className="flex-between text-[10px] text-on-surface-variant mt-1 tabular-nums">
            <span>$0</span>
            <span>$5k</span>
          </div>
        </div>

        {/* Annual return rate */}
        <div>
          <div className="flex-between mb-1">
            <label htmlFor="sim-rate" className="label-sm text-on-surface-variant">
              Annual return
            </label>
            <span className="text-sm font-semibold tabular-nums text-primary">
              {(sim.annualReturnRate * 100).toFixed(1)}%
            </span>
          </div>
          <input
            id="sim-rate"
            type="range"
            min={0}
            max={0.15}
            step={0.005}
            value={sim.annualReturnRate}
            onChange={(e) => sim.setAnnualReturnRate(Number(e.target.value))}
            className="fc-range w-full"
            data-testid="simulator-slider-rate"
            aria-label="Annual return rate as a percentage"
          />
          <div className="flex-between text-[10px] text-on-surface-variant mt-1 tabular-nums">
            <span>0%</span>
            <span>15%</span>
          </div>
        </div>

        {/* Inflation rate */}
        <div>
          <div className="flex-between mb-1">
            <label htmlFor="sim-inflation" className="label-sm text-on-surface-variant">
              Inflation
            </label>
            <span className="text-sm font-semibold tabular-nums text-primary">
              {(sim.inflationRate * 100).toFixed(1)}%
            </span>
          </div>
          <input
            id="sim-inflation"
            type="range"
            min={0}
            max={0.08}
            step={0.0025}
            value={sim.inflationRate}
            onChange={(e) => sim.setInflationRate(Number(e.target.value))}
            className="fc-range w-full"
            data-testid="simulator-slider-inflation"
            aria-label="Annual inflation rate as a percentage"
          />
          <div className="flex-between text-[10px] text-on-surface-variant mt-1 tabular-nums">
            <span>0%</span>
            <span>8%</span>
          </div>
        </div>
      </div>

      {/* Live preview tiles — projected net worth at 5y / 10y / 20y given current sliders. */}
      <div className="mt-5 grid grid-cols-3 gap-3">
        {HORIZONS.map((y, i) => {
          const value = projections[i]
          return (
            <div
              key={y}
              className="rounded-[var(--radius-md)] p-3 border border-[var(--border-color)]"
              data-testid={`simulator-preview-${y}y`}
            >
              <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-on-surface-variant">
                <TrendingUp className="w-3 h-3" aria-hidden="true" />
                {y}-Year
              </div>
              <div className="text-lg font-bold tabular-nums text-primary mt-1"
                   data-testid={`simulator-preview-${y}y-value`}>
                $<CountUp end={Math.round(value)} duration={600} />
              </div>
              <div className="text-[10px] text-on-surface-variant tabular-nums mt-0.5">
                Per current sliders & scenario
              </div>
            </div>
          )
        })}
      </div>

      {/* Slider thumb styles live in ui/styles/utilities.css (.fc-range).
          They were originally inline <style jsx> here, but that requires
          the ``styled-jsx`` package which is NOT a dependency of this
          project; the resulting runtime error "Fast Refresh had to
          perform a full reload" was hiding every dashboard selector in
          Playwright tests. See ui/styles/utilities.css for the rule. */}
    </div>
  )
}
