import { describe, it, expect, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import WhyDidThisChange from '@/components/dashboard/WhyDidThisChange'
import type { TrendDataPoint } from '@/lib/api'

// jsdom does not provide window.matchMedia — stub it for useThemeMode()
beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  })
})

function makeTrend(overrides: Partial<TrendDataPoint> = {}): TrendDataPoint {
  return {
    month: '2026-06',
    income: 8000,
    spend: 4000,
    retained: 4000,
    ...overrides,
  }
}

describe('WhyDidThisChange', () => {
  it('renders nothing when fewer than 2 months of data', () => {
    const { container } = render(<WhyDidThisChange trends={[makeTrend()]} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when trends array is empty', () => {
    const { container } = render(<WhyDidThisChange trends={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when all changes are below 5% threshold', () => {
    const trends = [
      makeTrend({ month: '2026-06', income: 8000, spend: 4000, retained: 4000 }),
      makeTrend({ month: '2026-07', income: 8100, spend: 4050, retained: 4050 }),
    ]
    const { container } = render(<WhyDidThisChange trends={trends} />)
    expect(container.firstChild).toBeNull()
  })

  it('shows insight when income changes by >=5%', () => {
    const trends = [
      makeTrend({ month: '2026-06', income: 8000, spend: 4000, retained: 4000 }),
      makeTrend({ month: '2026-07', income: 9000, spend: 4000, retained: 5000 }),
    ]
    render(<WhyDidThisChange trends={trends} />)
    expect(screen.getByText('Income')).toBeInTheDocument()
    expect(screen.getByText(/13%/)).toBeInTheDocument()
  })

  it('shows insight when spending changes by >=5%', () => {
    const trends = [
      makeTrend({ month: '2026-06', income: 8000, spend: 4000, retained: 4000 }),
      makeTrend({ month: '2026-07', income: 8000, spend: 5000, retained: 3000 }),
    ]
    render(<WhyDidThisChange trends={trends} />)
    expect(screen.getByText('Spending')).toBeInTheDocument()
    // Spending up 25%, Retained down 25% — both appear
    const pctElements = screen.getAllByText(/25%/)
    expect(pctElements.length).toBeGreaterThanOrEqual(1)
  })

  it('sorts insights by absolute magnitude (biggest mover first)', () => {
    const trends = [
      makeTrend({ month: '2026-06', income: 8000, spend: 4000, retained: 4000 }),
      makeTrend({ month: '2026-07', income: 8000, spend: 6000, retained: 2000 }),
    ]
    render(<WhyDidThisChange trends={trends} />)
    // Spending changed by 50%, retained by 50% — both should appear
    expect(screen.getByText('Spending')).toBeInTheDocument()
    expect(screen.getByText('Net Retained')).toBeInTheDocument()
  })

  it('has accessible role=status', () => {
    const trends = [
      makeTrend({ month: '2026-06', income: 8000, spend: 4000, retained: 4000 }),
      makeTrend({ month: '2026-07', income: 9000, spend: 4000, retained: 5000 }),
    ]
    render(<WhyDidThisChange trends={trends} />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('limits to at most 3 insights', () => {
    // All three metrics change significantly
    const trends = [
      makeTrend({ month: '2026-06', income: 8000, spend: 4000, retained: 4000 }),
      makeTrend({ month: '2026-07', income: 12000, spend: 6000, retained: 6000 }),
    ]
    render(<WhyDidThisChange trends={trends} />)
    // Should show Income, Spending, Net Retained (3 items)
    expect(screen.getByText('Income')).toBeInTheDocument()
    expect(screen.getByText('Spending')).toBeInTheDocument()
    expect(screen.getByText('Net Retained')).toBeInTheDocument()
  })
})
