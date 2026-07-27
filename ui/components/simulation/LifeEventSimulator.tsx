'use client'

import { Home, Baby, Briefcase, Sunset, type LucideIcon } from 'lucide-react'
import { SCENARIOS, useSimulation, type ScenarioId } from './WealthSimulationContext'

/**
 * Phase 5 — LifeEventSimulator.
 *
 * Four preset life-event chips. Tapping a chip activates the matching
 * scenario in the simulation context; tapping again deactivates it. The
 * active scenario applies a PMT delta (and an optional stop-year) to
 * the projection math used by ``WealthTimeline`` and ``FinancialTwin``.
 *
 * Each chip's body shows the cash-flow direction (down/up) and a
 * one-line description so the user can read the impact without opening
 * a sidebar.
 *
 * data-testid surface:
 *   - ``life-events``       — root container
 *   - ``life-event-chip-{id}`` — each preset chip
 *   - ``life-event-empty``  — empty state when no scenario is active
 */

const SCENARIO_ICONS: Record<ScenarioId, LucideIcon> = {
  'buy-house': Home,
  'new-child': Baby,
  'job-change': Briefcase,
  'early-retirement': Sunset,
}

export default function LifeEventSimulator({ className }: { className?: string }) {
  const sim = useSimulation()
  const activeId = sim.activeScenario

  const activate = (id: ScenarioId) => {
    sim.setActiveScenario(activeId === id ? null : id)
  }

  return (
    <div className={`card p-6 ${className ?? ''}`} data-testid="life-events">
      <div className="mb-4">
        <h3 className="headline-md text-primary">Life Event Simulator</h3>
        <p className="body-sm text-on-surface-variant">Tap a scenario to apply it. Tap again to clear.</p>
      </div>

      {(Object.values(SCENARIOS) as Array<typeof SCENARIOS[ScenarioId]>).map((scenario) => {
        const isActive = activeId === scenario.id
        const Icon = SCENARIO_ICONS[scenario.id]
        const deltaStr =
          scenario.deltaPMT === 0
            ? 'Stops at year 10'
            : `${scenario.deltaPMT > 0 ? '+' : '-'}$${Math.abs(scenario.deltaPMT).toLocaleString('en-US')}/mo`
        return (
          <button
            type="button"
            key={scenario.id}
            onClick={() => activate(scenario.id)}
            className={`
              w-full mt-2 first:mt-0 px-4 py-3 rounded-[var(--radius-md)]
              flex items-start gap-3 text-left
              border transition-all duration-150
              ${isActive
                ? 'border-[var(--accent-cyan)] bg-[color-mix(in_srgb,var(--accent-cyan)_8%,transparent)]'
                : 'border-[var(--border-color)] hover:bg-surface-container'}
            `}
            style={isActive ? { boxShadow: '0 0 0 2px color-mix(in srgb, var(--accent-cyan) 30%, transparent)' } : undefined}
            data-testid={`life-event-chip-${scenario.id}`}
            aria-pressed={isActive}
          >
            <span
              className={`
                flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center
                ${isActive ? 'bg-[var(--accent-cyan)] text-white' : 'bg-surface-container text-on-surface-variant'}
                transition-colors duration-150
              `}
            >
              <Icon className="w-4 h-4" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex-between gap-2">
                <span className="font-semibold text-sm text-primary truncate">{scenario.name}</span>
                <span
                  className={`text-xs font-bold tabular-nums px-2 py-0.5 rounded-full ${
                    scenario.deltaPMT < 0
                      ? 'text-[var(--warning-700)] bg-[color-mix(in_srgb,var(--warning-500)_14%,transparent)]'
                      : scenario.deltaPMT > 0
                        ? 'text-[var(--success-700)] bg-[color-mix(in_srgb,var(--success-500)_14%,transparent)]'
                        : 'text-on-surface-variant bg-surface-container'
                  }`}
                >
                  {deltaStr}
                </span>
              </div>
              <p className="text-xs text-on-surface-variant mt-0.5 leading-snug">
                {scenario.description}
              </p>
            </div>
          </button>
        )
      })}
    </div>
  )
}
