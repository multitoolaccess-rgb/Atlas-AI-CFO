/**
 * Vitest unit tests for WealthScoreRing.
 *
 * Verifies:
 *  - The 5-component wealth score computation produces values in the
 *    300–850 band.
 *  - Status thresholds (Excellent/Good/Fair/Building) map correctly.
 *  - Loading state renders the skeleton.
 *  - Trend delta renders when trends data is available.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { createElement } from 'react'
import WealthScoreRing, { computeWealthScore, scoreStatus } from '../WealthScoreRing'
import type { DashboardSummary, DashboardBreakdownResponse, TrendDataPoint } from '@/lib/api'

// ---- Mocks --------------------------------------------------------------

// GaugeRing renders an SVG; jsdom doesn't draw it but the DOM is present.
// We mock it to surface the rawValue prop (the score) as text so we can
// assert on it without needing SVG geometry.
vi.mock('@/components/charts/GaugeRing', () => ({
  default: ({ rawValue, label, subLabel }: any) => (
    <div data-testid="gauge-ring-mock">
      <span data-testid="gauge-raw-value">{rawValue}</span>
      <span data-testid="gauge-label">{label}</span>
      <span data-testid="gauge-sub-label">{subLabel}</span>
    </div>
  ),
}))

// ---- Fixtures -----------------------------------------------------------

const baseSummary: DashboardSummary = {
  total_balance: 100_000,
  total_income_month: 8_000,
  total_expenses_month: 4_000,
  accounts_count: 4,
  transactions_count: 500,
  import_batches_count: 2,
  last_sync: null,
  last_import_at: null,
}

const baseBreakdown: DashboardBreakdownResponse = {
  buckets: [
    { label: 'Savings', amount: 1_500, color: '#10b981', percentage: 25 },
    { label: 'Debt', amount: 600, color: '#f59e0b', percentage: 10 },
  ],
  total_spend: 4_000,
  period: '2026-07',
}

const baseTrends: TrendDataPoint[] = [
  { month: '2026-05', income: 7_500, spend: 4_200, retained: 3_300 },
  { month: '2026-06', income: 7_800, spend: 4_100, retained: 3_700 },
  { month: '2026-07', income: 8_000, spend: 4_000, retained: 4_000 },
]

// ---- Tests --------------------------------------------------------------

describe('computeWealthScore', () => {
  it('returns score 0 and null trend when summary is null', () => {
    const { score, trend } = computeWealthScore(null, null, null)
    expect(score).toBe(0)
    expect(trend).toBeNull()
  })

  it('produces a score in the 300–850 band for valid inputs', () => {
    const { score } = computeWealthScore(baseSummary, baseBreakdown, baseTrends)
    expect(score).toBeGreaterThanOrEqual(300)
    expect(score).toBeLessThanOrEqual(850)
  })

  it('higher savings rate produces a higher score', () => {
    const lowSavings = { ...baseSummary, total_expenses_month: 7_500 } // 6.25% rate
    const highSavings = { ...baseSummary, total_expenses_month: 2_000 } // 75% rate
    const low = computeWealthScore(lowSavings, baseBreakdown, baseTrends)
    const high = computeWealthScore(highSavings, baseBreakdown, baseTrends)
    expect(high.score).toBeGreaterThan(low.score)
  })

  it('higher debt reduces the score', () => {
    const lowDebt = { ...baseBreakdown, buckets: [{ label: 'Debt', amount: 100, color: '', percentage: 2 }] }
    const highDebt = { ...baseBreakdown, buckets: [{ label: 'Debt', amount: 5_000, color: '', percentage: 80 }] }
    const low = computeWealthScore(baseSummary, lowDebt, baseTrends)
    const high = computeWealthScore(baseSummary, highDebt, baseTrends)
    expect(low.score).toBeGreaterThan(high.score)
  })

  it('computes a non-null trend when trends has >= 2 data points', () => {
    const { trend } = computeWealthScore(baseSummary, baseBreakdown, baseTrends)
    expect(trend).not.toBeNull()
    expect(typeof trend).toBe('number')
  })

  it('returns null trend when trends has < 2 data points', () => {
    const { trend } = computeWealthScore(baseSummary, baseBreakdown, [baseTrends[0]])
    expect(trend).toBeNull()
  })

  it('handles undefined breakdown and trends gracefully', () => {
    const { score, trend } = computeWealthScore(baseSummary, undefined, undefined)
    expect(score).toBeGreaterThanOrEqual(300)
    expect(trend).toBeNull()
  })
})

describe('scoreStatus', () => {
  it('maps 750+ to Excellent', () => {
    expect(scoreStatus(800).label).toBe('Excellent')
  })
  it('maps 670–749 to Good', () => {
    expect(scoreStatus(700).label).toBe('Good')
  })
  it('maps 580–669 to Fair', () => {
    expect(scoreStatus(620).label).toBe('Fair')
  })
  it('maps < 580 to Building', () => {
    expect(scoreStatus(400).label).toBe('Building')
  })
})

describe('WealthScoreRing component', () => {
  afterEach(() => cleanup())

  it('renders the score via GaugeRing when not loading', () => {
    render(createElement(WealthScoreRing, {
      summary: baseSummary,
      breakdown: baseBreakdown,
      trends: baseTrends,
      loading: false,
    }))
    const rawValue = screen.getByTestId('gauge-raw-value')
    const score = Number(rawValue.textContent)
    expect(score).toBeGreaterThanOrEqual(300)
    expect(score).toBeLessThanOrEqual(850)
  })

  it('renders loading skeleton when loading=true', () => {
    render(createElement(WealthScoreRing, {
      summary: null,
      loading: true,
    }))
    expect(screen.getByTestId('wealth-score-loading')).toBeTruthy()
  })

  it('renders trend badge when trends available', () => {
    render(createElement(WealthScoreRing, {
      summary: baseSummary,
      breakdown: baseBreakdown,
      trends: baseTrends,
      loading: false,
    }))
    const trend = screen.queryByTestId('wealth-score-trend')
    expect(trend).toBeTruthy()
  })

  it('does not render trend badge when trends unavailable', () => {
    render(createElement(WealthScoreRing, {
      summary: baseSummary,
      breakdown: baseBreakdown,
      trends: null,
      loading: false,
    }))
    expect(screen.queryByTestId('wealth-score-trend')).toBeNull()
  })
})
