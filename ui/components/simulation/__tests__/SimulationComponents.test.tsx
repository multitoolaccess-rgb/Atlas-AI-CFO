import { describe, it, expect, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { WealthSimulationProvider, useSimulation } from '@/components/simulation/WealthSimulationContext'
import WealthTimeline from '@/components/simulation/WealthTimeline'
import MoneyFlowSimulator from '@/components/simulation/MoneyFlowSimulator'
import LifeEventSimulator from '@/components/simulation/LifeEventSimulator'
import FinancialDNA from '@/components/simulation/FinancialDNA'
import FinancialTwin from '@/components/simulation/FinancialTwin'

function withProvider(ui: React.ReactNode, opts?: { netWorth?: number; pmt?: number; rate?: number }) {
  return render(
    <WealthSimulationProvider
      netWorth={opts?.netWorth ?? 100000}
      initialMonthlyContribution={opts?.pmt ?? 1000}
      initialAnnualReturnRate={opts?.rate ?? 0.07}
    >
      {ui}
    </WealthSimulationProvider>,
  )
}

beforeEach(() => {
  // jsdom doesn't ship matchMedia by default; stub it.
  // matches=true for "(prefers-reduced-motion: reduce)" so CountUp
  // jumps straight to its target value instead of animating over
  // 800ms — keeps comparison tests fast (no need to waitFor rAF).
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: query.includes('reduce'),
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
      onchange: null,
    }),
  })
})

afterEach(() => {
  cleanup()
})

describe('WealthTimeline', () => {
  it('renders with past trend points', () => {
    withProvider(
      <WealthTimeline
        pastTrends={Array.from({ length: 6 }).map((_, i) => ({
          month: `2024-${String(i + 1).padStart(2, '0')}`,
          netWorth: 80000 + i * 5000,
        }))}
        netWorth={120000}
      />,
    )
    expect(screen.getByTestId('wealth-timeline')).toBeTruthy()
    expect(screen.getByTestId('wealth-timeline-now')).toBeTruthy()
  })
})

describe('MoneyFlowSimulator', () => {
  it('renders 3 sliders and 3 preview tiles', () => {
    withProvider(<MoneyFlowSimulator />, { pmt: 500, rate: 0.07 })
    expect(screen.getByTestId('simulator-card')).toBeTruthy()
    expect(screen.getByTestId('simulator-slider-pmt')).toBeTruthy()
    expect(screen.getByTestId('simulator-slider-rate')).toBeTruthy()
    expect(screen.getByTestId('simulator-slider-inflation')).toBeTruthy()
    expect(screen.getByTestId('simulator-preview-5y')).toBeTruthy()
    expect(screen.getByTestId('simulator-preview-10y')).toBeTruthy()
    expect(screen.getByTestId('simulator-preview-20y')).toBeTruthy()
  })

  it('changing PMT updates the preview counts', () => {
    withProvider(<MoneyFlowSimulator />, { pmt: 100, rate: 0.07 })
    // The preview div's textContent is like "$217,000" — strip non-digits
    // before parsing, otherwise parseInt returns NaN on the "$" prefix.
    const parseVal = (id: string) =>
      parseInt((screen.getByTestId(id).textContent ?? '0').replace(/[^\d]/g, ''), 10) || 0
    const before = parseVal('simulator-preview-10y-value')
    fireEvent.change(screen.getByTestId('simulator-slider-pmt'), { target: { value: '3000' } })
    // reducedMotion matchMedia stub lets CountUp snap to the new target,
    // so the value should update synchronously after fireEvent.
    const after = parseVal('simulator-preview-10y-value')
    expect(after).toBeGreaterThan(before)
  })

  it('reset button restores baseline values', () => {
    withProvider(<MoneyFlowSimulator />, { pmt: 500 })
    fireEvent.change(screen.getByTestId('simulator-slider-pmt'), { target: { value: '2500' } })
    expect(screen.getByTestId('simulator-slider-pmt').getAttribute('value')).toBe('2500')
    fireEvent.click(screen.getByTestId('simulator-reset'))
    expect(screen.getByTestId('simulator-slider-pmt').getAttribute('value')).toBe('500')
  })
})

describe('LifeEventSimulator', () => {
  it('renders 4 life-event chips', () => {
    withProvider(<LifeEventSimulator />)
    expect(screen.getByTestId('life-event-chip-buy-house')).toBeTruthy()
    expect(screen.getByTestId('life-event-chip-new-child')).toBeTruthy()
    expect(screen.getByTestId('life-event-chip-job-change')).toBeTruthy()
    expect(screen.getByTestId('life-event-chip-early-retirement')).toBeTruthy()
  })

  it('toggling a chip activates and deactivates a scenario', () => {
    withProvider(<LifeEventSimulator />)
    const chip = screen.getByTestId('life-event-chip-buy-house')
    fireEvent.click(chip)
    expect(chip.getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(chip)
    expect(chip.getAttribute('aria-pressed')).toBe('false')
  })
})

describe('FinancialDNA', () => {
  it('renders the radar SVG + center score', () => {
    withProvider(
      <FinancialDNA
        summary={{
          total_balance: 100000,
          total_income_month: 5000,
          total_expenses_month: 3000,
          accounts_count: 3,
          transactions_count: 100,
          user_goals: [{ id: 1, name: 'Goal', target_amount: 200000 }],
        } as any}
      />,
    )
    expect(screen.getByTestId('dna-card')).toBeTruthy()
    expect(screen.getByTestId('dna-polygon')).toBeTruthy()
    expect(screen.getByTestId('dna-score')).toBeTruthy()
  })

  it('exposes all 5 axis labels', () => {
    withProvider(<FinancialDNA summary={null} />)
    ;['savingsRate', 'investmentDiversity', 'cashBuffer', 'debtDiscipline', 'goalVelocity'].forEach((k) => {
      expect(screen.getByTestId(`dna-axis-${k}`)).toBeTruthy()
    })
  })
})

describe('FinancialTwin', () => {
  it('renders 3 age cards', () => {
    withProvider(<FinancialTwin currentAge={30} targetAges={[50, 60, 65]} />)
    expect(screen.getByTestId('twin-card-50')).toBeTruthy()
    expect(screen.getByTestId('twin-card-60')).toBeTruthy()
    expect(screen.getByTestId('twin-card-65')).toBeTruthy()
  })
})
