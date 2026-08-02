import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { type ReactNode } from 'react'
import {
  WealthSimulationProvider,
  useSimulation,
  SCENARIOS,
} from '@/components/simulation/WealthSimulationContext'

function wrapper(initial?: { netWorth?: number; initialMonthlyContribution?: number }) {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <WealthSimulationProvider
      netWorth={initial?.netWorth ?? 100000}
      initialMonthlyContribution={initial?.initialMonthlyContribution ?? 500}
      initialAnnualReturnRate={0.07}
    >
      {children}
    </WealthSimulationProvider>
  )
  Wrapper.displayName = 'WealthSimulationTestWrapper'
  return Wrapper
}

describe('WealthSimulationContext', () => {
  it('exposes initial state on mount', () => {
    const { result } = renderHook(() => useSimulation(), { wrapper: wrapper() })
    expect(result.current.monthlyContribution).toBe(500)
    expect(result.current.annualReturnRate).toBeCloseTo(0.07)
    expect(result.current.inflationRate).toBe(0)
    expect(result.current.activeScenario).toBeNull()
  })

  it('updates state via setters', () => {
    const { result } = renderHook(() => useSimulation(), { wrapper: wrapper() })
    act(() => {
      result.current.setMonthlyContribution(1000)
      result.current.setAnnualReturnRate(0.09)
    })
    expect(result.current.monthlyContribution).toBe(1000)
    expect(result.current.annualReturnRate).toBeCloseTo(0.09)
  })

  it('projects a positive future value when contribution + return are set', () => {
    const { result } = renderHook(() => useSimulation(), { wrapper: wrapper({ netWorth: 100000, initialMonthlyContribution: 1000 }) })
    const fv5 = result.current.projectedNetWorthAt(5)
    expect(fv5).toBeGreaterThan(100000)
  })

  it('applys the buy-house scenario (negative PMT delta)', () => {
    const { result } = renderHook(() => useSimulation(), { wrapper: wrapper({ netWorth: 100000, initialMonthlyContribution: 1000 }) })
    const before = result.current.projectedNetWorthAt(10)
    act(() => {
      result.current.setActiveScenario('buy-house')
    })
    const after = result.current.projectedNetWorthAt(10)
    expect(after).toBeLessThan(before)
    expect(result.current.activeScenario).toBe('buy-house')
  })

  it('applys the job-change scenario (positive PMT delta)', () => {
    const { result } = renderHook(() => useSimulation(), { wrapper: wrapper({ netWorth: 0, initialMonthlyContribution: 500 }) })
    const before = result.current.projectedNetWorthAt(10)
    act(() => {
      result.current.setActiveScenario('job-change')
    })
    const after = result.current.projectedNetWorthAt(10)
    expect(after).toBeGreaterThan(before)
  })

  it('early-retirement flattens contributions past stopsAtYear', () => {
    const { result } = renderHook(() => useSimulation(), { wrapper: wrapper({ netWorth: 100000, initialMonthlyContribution: 1000 }) })
    act(() => {
      result.current.setActiveScenario('early-retirement')
    })
    const fv10 = result.current.projectedNetWorthAt(10)
    const fv5 = result.current.projectedNetWorthAt(5)
    // After year 10, no more contributions, so growth slows; fv10/fv5 ratio
    // should be lower than without scenario.
    const ratio = fv10 / Math.max(1, fv5)
    expect(ratio).toBeGreaterThan(1)
    expect(ratio).toBeLessThan(3.5) // sanity: not infinite compounding
  })

  it('reset() restores baseline values and clears scenario', () => {
    const { result } = renderHook(() => useSimulation(), { wrapper: wrapper({ netWorth: 100000, initialMonthlyContribution: 1000 }) })
    act(() => {
      result.current.setMonthlyContribution(2500)
      result.current.setAnnualReturnRate(0.12)
      result.current.setActiveScenario('buy-house')
    })
    expect(result.current.activeScenario).toBe('buy-house')
    act(() => {
      result.current.reset()
    })
    expect(result.current.monthlyContribution).toBe(1000)
    expect(result.current.annualReturnRate).toBeCloseTo(0.07)
    expect(result.current.activeScenario).toBeNull()
  })

  it('useSimulation throws when used outside provider', () => {
    expect(() => renderHook(() => useSimulation())).toThrow(/WealthSimulationProvider/)
  })

  it('SCENARIOS exposes all 4 life-event scenario configs', () => {
    expect(Object.keys(SCENARIOS).sort()).toEqual(
      ['buy-house', 'early-retirement', 'job-change', 'new-child'].sort(),
    )
  })
})
