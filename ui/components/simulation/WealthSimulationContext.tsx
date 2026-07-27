'use client'

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { projectDashboardTrajectory, calculateFutureValue } from '@/lib/math/projection'

/**
 * Phase 5 — WealthSimulationContext.
 *
 * Single source of truth for the dashboard's simulation state. Five
 * components (WealthTimeline, MoneyFlowSimulator, LifeEventSimulator,
 * FinancialDNA, FinancialTwin) consume this context so moving a slider
 * in the simulator flows into the timeline's curve and the twin cards'
 * projected values without prop-drilling.
 *
 * State shape is intentionally small (sliders + active scenario id)
 * — the projection numbers are derived in a ``useMemo`` so we never
 * confuse stored values with computed ones.
 *
 * Why React Context (A) over prop-drilling (B) or module store (C):
 *   - The 5 components span 4 sibling sections on the dashboard page,
 *     so prop-drilling would require >>>3 levels of nesting.
 *   - React 18 batches state updates; the simulator-slider → timeline
 *     re-render always happens in a single commit (no tearing).
 *   - Existing patterns (SidebarProvider, DashboardFilterProvider)
 *     are exactly this shape, so it's idiomatic for the codebase.
 *   - Module stores would break the React DevTools inspection flow.
 *
 * Defaults are seeded from the dashboard summary when available
 * (initialMonthlyContribution = income - expenses). If the summary is
 * missing, defaults to a stable baseline ($0 contribution, 7% return,
 * 0% inflation) so first paint is never blank.
 */

// ---- Scenario types ------------------------------------------------------

export type ScenarioId = 'buy-house' | 'new-child' | 'job-change' | 'early-retirement'

export interface ScenarioConfig {
  id: ScenarioId
  name: string
  /** Monthly cash-flow delta in USD. Negative = pressure; positive = boost. */
  deltaPMT: number
  /** Years from now the scenario starts taking effect. 0 = immediate. */
  startYear: number
  /** Optional horizon-year for scenarios that STOP contributions. */
  stopsAtYear?: number
  description: string
}

export const SCENARIOS: Record<ScenarioId, ScenarioConfig> = {
  'buy-house': {
    id: 'buy-house',
    name: 'Buy House',
    deltaPMT: -2500,
    startYear: 0,
    description: '$2,500/mo less to save — saving for the down payment.',
  },
  'new-child': {
    id: 'new-child',
    name: 'New Child',
    deltaPMT: -1500,
    startYear: 0,
    description: '$1,500/mo more spent on childcare and family.',
  },
  'job-change': {
    id: 'job-change',
    name: 'Job Change (Raise)',
    deltaPMT: 4000,
    startYear: 0,
    description: '$4,000/mo more from a salary bump at the new role.',
  },
  'early-retirement': {
    id: 'early-retirement',
    name: 'Early Retirement',
    deltaPMT: 0,
    startYear: 0,
    stopsAtYear: 10,
    description: 'Stop contributing at year 10 — coast from there.',
  },
}

// ---- State ---------------------------------------------------------------

export interface SimulationState {
  monthlyContribution: number
  annualReturnRate: number
  inflationRate: number
  activeScenario: ScenarioId | null
}

interface SimulationContextValue extends SimulationState {
  setMonthlyContribution: (n: number) => void
  setAnnualReturnRate: (n: number) => void
  setInflationRate: (n: number) => void
  setActiveScenario: (id: ScenarioId | null) => void
  /** Reset to the original baseline (initial values). */
  reset: () => void
  /** The original baseline values captured at provider mount. */
  baseline: SimulationState
  /**
   * Pure derived projected net worth at N years using current simulator
   * state. Accounts for the active scenario's delta + retirement cutoff.
   */
  projectedNetWorthAt: (years: number, opts?: { netWorth?: number }) => number
}

const DEFAULT_RATE = 0.07
const DEFAULT_INFLATION = 0
const DEFAULT_PMT = 500

const SimulationContext = createContext<SimulationContextValue | null>(null)

// ---- Helpers -------------------------------------------------------------

/**
 * Compute projected net worth at a future year, accounting for the active
 * scenario's PMT delta (``scenarios['buy-house']`` etc.) and any retirement
 * cutoff (``stopsAtYear``).
 *
 * Why we ignore ``inflationRate`` for piecewise scenarios: the underlying
 * ``calculateFutureValue`` already applies the Fisher real rate when
 * callers pass an inflation rate. We only pass inflation when there's NO
 * active scenario (so the "no scenario" branch matches pure dashboard
 * behavior); with scenarios we keep inflation at 0 because the scenario
 * already represents a behavioral pivot.
 */
function computeProjection(
  netWorth: number,
  pmtBase: number,
  rate: number,
  years: number,
  inflation: number,
  scenario: ScenarioConfig | null,
): number {
  if (!scenario) {
    return projectDashboardTrajectory({
      netWorth,
      monthlyContribution: pmtBase,
      annualReturnRate: rate,
      years,
      annualInflationRate: inflation,
    })
  }

  // Scenario active — piecewise PMT over the timeline.
  // Phase 1: years [0, startYear)  → scenario's delta applied
  // Phase 2: years [startYear, stopsAtYear || years)  → scenario's delta + base
  // Early-retirement: contribution stops at stopsAtYear → 0 PMT thereafter.
  const start = Math.max(0, scenario.startYear)
  const stops = scenario.stopsAtYear ?? Infinity

  let value = netWorth
  // Year 0 is the current snapshot.
  if (start === 0) {
    value = projectDashboardTrajectory({
      netWorth,
      monthlyContribution: pmtBase + scenario.deltaPMT,
      annualReturnRate: rate,
      years: Math.min(stops, years),
    })
    if (stops < years) {
      // Flat-growth after stop.
      const remainingYears = years - stops
      const stoppedFV = calculateFutureValue({
        pv: value,
        pmt: 0,
        rate,
        years: remainingYears,
      })
      return stoppedFV
    }
    return value
  }

  // Scenario starts at year `start`; pre-scenario the base PMT runs.
  if (start >= years) {
    // Scenario never fires within the horizon.
    return projectDashboardTrajectory({
      netWorth,
      monthlyContribution: pmtBase,
      annualReturnRate: rate,
      years,
    })
  }

  // Pre-scenario phase
  value = projectDashboardTrajectory({
    netWorth,
    monthlyContribution: pmtBase,
    annualReturnRate: rate,
    years: start,
  })
  // Scenario phase
  const scenarioYears = Math.min(stops, years) - start
  if (scenarioYears > 0) {
    value = projectDashboardTrajectory({
      netWorth: value,
      monthlyContribution: pmtBase + scenario.deltaPMT,
      annualReturnRate: rate,
      years: scenarioYears,
    })
  }
  // Post-scenario-stop phase (only for early-retirement)
  if (stops < years) {
    const remainingYears = years - stops
    value = calculateFutureValue({
      pv: value,
      pmt: 0,
      rate,
      years: remainingYears,
    })
  }
  return value
}

// ---- Provider ------------------------------------------------------------

interface WealtheSimulationProviderProps {
  children: ReactNode
  /** Initial monthly contribution (e.g. dashboard's net cash flow). */
  initialMonthlyContribution?: number
  /** Initial annual return rate. Defaults to 7%. */
  initialAnnualReturnRate?: number
  /** Net worth baseline (used by `projectedNetWorthAt`). */
  netWorth?: number
}

export function WealthSimulationProvider({
  children,
  initialMonthlyContribution = DEFAULT_PMT,
  initialAnnualReturnRate = DEFAULT_RATE,
  netWorth = 0,
}: WealtheSimulationProviderProps) {
  const [monthlyContribution, setMonthlyContribution] = useState(initialMonthlyContribution)
  const [annualReturnRate, setAnnualReturnRate] = useState(initialAnnualReturnRate)
  const [inflationRate, setInflationRate] = useState(DEFAULT_INFLATION)
  const [activeScenario, setActiveScenario] = useState<ScenarioId | null>(null)

  const baseline = useMemo<SimulationState>(
    () => ({
      monthlyContribution: initialMonthlyContribution,
      annualReturnRate: initialAnnualReturnRate,
      inflationRate: DEFAULT_INFLATION,
      activeScenario: null,
    }),
    [initialMonthlyContribution, initialAnnualReturnRate],
  )

  const reset = useCallback(() => {
    setMonthlyContribution(baseline.monthlyContribution)
    setAnnualReturnRate(baseline.annualReturnRate)
    setInflationRate(baseline.inflationRate)
    setActiveScenario(null)
  }, [baseline])

  // Pure projection helper exposed to consumers.
  // Memoized by scenario+sliders so callers don't recompute on every render.
  const projectedNetWorthAt = useCallback(
    (years: number, opts?: { netWorth?: number }) => {
      const scenario = activeScenario ? SCENARIOS[activeScenario] : null
      return computeProjection(
        opts?.netWorth ?? netWorth,
        monthlyContribution,
        annualReturnRate,
        years,
        inflationRate,
        scenario,
      )
    },
    [netWorth, monthlyContribution, annualReturnRate, inflationRate, activeScenario],
  )

  const value = useMemo<SimulationContextValue>(
    () => ({
      monthlyContribution,
      annualReturnRate,
      inflationRate,
      activeScenario,
      baseline,
      setMonthlyContribution,
      setAnnualReturnRate,
      setInflationRate,
      setActiveScenario,
      reset,
      projectedNetWorthAt,
    }),
    [
      monthlyContribution,
      annualReturnRate,
      inflationRate,
      activeScenario,
      baseline,
      reset,
      projectedNetWorthAt,
    ],
  )

  return <SimulationContext.Provider value={value}>{children}</SimulationContext.Provider>
}

export function useSimulation(): SimulationContextValue {
  const ctx = useContext(SimulationContext)
  if (!ctx) {
    throw new Error('useSimulation must be used inside <WealthSimulationProvider>')
  }
  return ctx
}
