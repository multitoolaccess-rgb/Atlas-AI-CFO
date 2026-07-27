/**
 * Vitest unit tests for AIWealthOverview.
 *
 * Verifies:
 *  - The hero zone renders with the correct data-testid attributes.
 *  - Net worth displays via CountUp when not loading.
 *  - Loading state renders skeletons instead of numbers.
 *  - Secondary tiles (Income/Spend/CashFlow/Saved) render.
 *  - WealthScoreRing is rendered inside the hero.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { createElement } from 'react'
import AIWealthOverview from '../AIWealthOverview'
import type { DashboardSummary, DashboardBreakdownResponse, TrendDataPoint } from '@/lib/api'

// ---- Mocks --------------------------------------------------------------

// CountUp renders a span with the target number. Mock it to surface the
// `end` prop as text so we can assert on the final value without waiting
// for requestAnimationFrame.
vi.mock('@/components/ui/CountUp', () => ({
  default: ({ end, className }: { end: number; className?: string }) => (
    <span data-testid="countup-mock" className={className}>{end}</span>
  ),
}))

// WealthScoreRing renders a mocked gauge so we can assert it's present
// without needing the full GaugeRing SVG geometry.
vi.mock('../WealthScoreRing', () => ({
  default: ({ loading }: { loading?: boolean }) => (
    <div data-testid="wealth-score-ring-mock" data-loading={loading ?? false} />
  ),
}))

// ---- Fixtures -----------------------------------------------------------

const baseSummary: DashboardSummary = {
  total_balance: 125_000,
  total_income_month: 8_500,
  total_expenses_month: 4_200,
  accounts_count: 4,
  transactions_count: 320,
  import_batches_count: 2,
  last_sync: null,
  last_import_at: null,
}

const baseBreakdown: DashboardBreakdownResponse = {
  buckets: [
    { label: 'Savings', amount: 2_000, color: '#10b981', percentage: 30 },
  ],
  total_spend: 4_200,
  period: '2026-07',
}

const baseTrends: TrendDataPoint[] = [
  { month: '2026-06', income: 8_000, spend: 4_500, retained: 3_500 },
  { month: '2026-07', income: 8_500, spend: 4_200, retained: 4_300 },
]

// ---- Tests --------------------------------------------------------------

describe('AIWealthOverview', () => {
  afterEach(() => cleanup())

  it('renders the hero zone with data-testid="ai-wealth-overview"', () => {
    render(createElement(AIWealthOverview, {
      summary: baseSummary,
      breakdown: baseBreakdown,
      trends: baseTrends,
      loading: false,
    }))
    expect(screen.getByTestId('ai-wealth-overview')).toBeTruthy()
  })

  it('renders the net worth tile with data-testid="hero-net-worth"', () => {
    render(createElement(AIWealthOverview, {
      summary: baseSummary,
      breakdown: baseBreakdown,
      trends: baseTrends,
      loading: false,
    }))
    expect(screen.getByTestId('hero-net-worth')).toBeTruthy()
  })

  it('displays the net worth value via CountUp when not loading', () => {
    render(createElement(AIWealthOverview, {
      summary: baseSummary,
      breakdown: baseBreakdown,
      trends: baseTrends,
      loading: false,
    }))
    const countup = screen.getByTestId('countup-mock')
    expect(countup.textContent).toBe('125000')
  })

  it('renders loading skeleton when loading=true', () => {
    render(createElement(AIWealthOverview, {
      summary: null,
      loading: true,
    }))
    // The net worth tile should have a loading skeleton
    const netWorthTile = screen.getByTestId('hero-net-worth')
    expect(netWorthTile.querySelector('.skeleton')).toBeTruthy()
    // CountUp should NOT be rendered during loading
    expect(screen.queryByTestId('countup-mock')).toBeNull()
  })

  it('renders the wealth score ring', () => {
    render(createElement(AIWealthOverview, {
      summary: baseSummary,
      breakdown: baseBreakdown,
      trends: baseTrends,
      loading: false,
    }))
    expect(screen.getByTestId('wealth-score-ring-mock')).toBeTruthy()
  })

  it('renders the 2 secondary tiles with correct data-testids', () => {
    render(createElement(AIWealthOverview, {
      summary: baseSummary,
      breakdown: baseBreakdown,
      trends: baseTrends,
      loading: false,
    }))
    expect(screen.getByTestId('hero-income')).toBeTruthy()
    expect(screen.getByTestId('hero-spend')).toBeTruthy()
    // Cash flow and saved tiles were removed in the Phase 6 hero redesign.
    expect(screen.queryByTestId('hero-cashflow')).toBeNull()
    expect(screen.queryByTestId('hero-saved')).toBeNull()
  })

  it('renders secondary tiles as loading skeletons when loading=true', () => {
    render(createElement(AIWealthOverview, {
      summary: null,
      loading: true,
    }))
    expect(screen.getByTestId('hero-income-loading')).toBeTruthy()
    expect(screen.getByTestId('hero-spend-loading')).toBeTruthy()
  })

  it('renders net worth delta when trends has >= 2 data points', () => {
    render(createElement(AIWealthOverview, {
      summary: baseSummary,
      breakdown: baseBreakdown,
      trends: baseTrends,
      loading: false,
    }))
    expect(screen.getByTestId('hero-net-worth-delta')).toBeTruthy()
  })

  it('does not render net worth delta when trends is null', () => {
    render(createElement(AIWealthOverview, {
      summary: baseSummary,
      breakdown: baseBreakdown,
      trends: null,
      loading: false,
    }))
    expect(screen.queryByTestId('hero-net-worth-delta')).toBeNull()
  })

  it('renders net worth label and value when summary has data', () => {
    render(createElement(AIWealthOverview, {
      summary: baseSummary,
      breakdown: baseBreakdown,
      trends: baseTrends,
      loading: false,
    }))
    const netWorthTile = screen.getByTestId('hero-net-worth')
    expect(netWorthTile.textContent).toContain('Total Net Worth')
    expect(netWorthTile.textContent).toContain('125000')
  })

  it('handles null summary and null breakdown gracefully', () => {
    render(createElement(AIWealthOverview, {
      summary: null,
      breakdown: null,
      trends: null,
      loading: false,
    }))
    // Should still render the hero zone structure
    expect(screen.getByTestId('ai-wealth-overview')).toBeTruthy()
    expect(screen.getByTestId('hero-net-worth')).toBeTruthy()
    // CountUp should render 0 for null summary
    expect(screen.getByTestId('countup-mock').textContent).toBe('0')
  })
})
