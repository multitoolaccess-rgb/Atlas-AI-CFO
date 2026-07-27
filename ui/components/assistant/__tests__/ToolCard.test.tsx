/**
 * Phase 30e — ToolCard component tests.
 *
 * Verifies that ToolCard renders the correct card type for each tool
 * result, formats numbers as currency, and handles edge cases (empty
 * results, errors, null results).
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import ToolCard from '../ToolCard'

describe('Phase 30e — ToolCard', () => {
  it('renders a summary card for get_totals', () => {
    render(
      <ToolCard
        tool="get_totals"
        result={{
          total_balance: 125000.0,
          total_income_month: 8500.0,
          total_expenses_month: 4200.0,
        }}
      />,
    )
    expect(screen.getByTestId('tool-card')).toBeTruthy()
    expect(screen.getByTestId('tool-card-value-total_balance').textContent).toMatch(/125,000/)
    expect(screen.getByTestId('tool-card-value-total_income_month').textContent).toMatch(/8,500/)
    expect(screen.getByTestId('tool-card-value-total_expenses_month').textContent).toMatch(/4,200/)
  })

  it('renders a savings rate card with a progress bar', () => {
    render(
      <ToolCard
        tool="compute_savings_rate"
        result={{
          income: 5000.0,
          expenses: 1300.0,
          net: 3700.0,
          savings_rate: 74.0,
          months_back: 0,
        }}
      />,
    )
    expect(screen.getByTestId('tool-card')).toBeTruthy()
    expect(screen.getByTestId('tool-card-value-savings_rate').textContent).toMatch(/74/)
  })

  it('renders a trends card with a mini bar chart', () => {
    render(
      <ToolCard
        tool="get_trends"
        result={{
          trend: [
            { month: '2026-05', expenses: 1000.0, income: 5000.0, net: 4000.0 },
            { month: '2026-06', expenses: 1200.0, income: 5000.0, net: 3800.0 },
            { month: '2026-07', expenses: 1500.0, income: 5000.0, net: 3500.0 },
          ],
          direction: 'increasing',
          months: 3,
        }}
      />,
    )
    expect(screen.getByTestId('tool-card')).toBeTruthy()
    expect(screen.getByTestId('tool-card-trend-chart')).toBeTruthy()
    expect(screen.getByTestId('tool-card-value-direction').textContent).toMatch(/increasing/)
  })

  it('renders a comparison table for compare_periods', () => {
    render(
      <ToolCard
        tool="compare_periods"
        result={{
          period_a: { months_back: 1, income: 5000.0, expenses: 1000.0, net: 4000.0 },
          period_b: { months_back: 0, income: 5000.0, expenses: 1500.0, net: 3500.0 },
          deltas: { income: 0.0, expenses: 500.0, net: -500.0 },
          percent_changes: { income: 0.0, expenses: 50.0, net: -12.5 },
        }}
      />,
    )
    expect(screen.getByTestId('tool-card')).toBeTruthy()
    expect(screen.getByTestId('tool-card-compare-table')).toBeTruthy()
  })

  it('renders an anomaly alert list', () => {
    render(
      <ToolCard
        tool="detect_anomalies"
        result={{
          anomalies: [
            { transaction_id: 1, merchant: 'STARBUCKS', amount: 1500.0, median: 175.0, multiplier: 8.6, date: '2026-07-01' },
          ],
          count: 1,
          lookback_days: 90,
          threshold_multiplier: 2.0,
        }}
      />,
    )
    expect(screen.getByTestId('tool-card')).toBeTruthy()
    expect(screen.getByTestId('tool-card-anomalies-list')).toBeTruthy()
  })

  it('renders empty state for anomalies when none found', () => {
    render(
      <ToolCard
        tool="detect_anomalies"
        result={{ anomalies: [], count: 0, lookback_days: 90, threshold_multiplier: 2.0 }}
      />,
    )
    expect(screen.getByTestId('tool-card-anomalies-empty')).toBeTruthy()
  })

  it('renders an upcoming bills list', () => {
    render(
      <ToolCard
        tool="predict_upcoming_bills"
        result={{
          bills: [
            { merchant: 'SERVICEMAC', median_amount: 300.0, median_interval_days: 30, last_date: '2026-06-27', predicted_next_date: '2026-07-27', confidence: 0.95, hit_count: 3 },
          ],
          count: 1,
        }}
      />,
    )
    expect(screen.getByTestId('tool-card')).toBeTruthy()
    expect(screen.getByTestId('tool-card-bills-list')).toBeTruthy()
  })

  it('renders empty state for bills when none found', () => {
    render(
      <ToolCard
        tool="predict_upcoming_bills"
        result={{ bills: [], count: 0 }}
      />,
    )
    expect(screen.getByTestId('tool-card-bills-empty')).toBeTruthy()
  })

  it('renders a search history results list', () => {
    render(
      <ToolCard
        tool="search_history"
        result={{
          query: 'dining',
          matches: [
            { conversation_id: 1, role: 'user', content: 'How much on dining?', created_at: '2026-07-04' },
          ],
          count: 1,
        }}
      />,
    )
    expect(screen.getByTestId('tool-card')).toBeTruthy()
    expect(screen.getByTestId('tool-card-search-list')).toBeTruthy()
  })

  it('renders empty state for search history when no matches', () => {
    render(
      <ToolCard
        tool="search_history"
        result={{ query: 'nonexistent', matches: [], count: 0 }}
      />,
    )
    expect(screen.getByTestId('tool-card-search-empty')).toBeTruthy()
  })

  it('renders an investable surplus card with goal target', () => {
    render(
      <ToolCard
        tool="compute_investable_surplus"
        result={{
          income: 5000.0,
          expenses: 2800.0,
          net_cash_flow: 2200.0,
          monthly_goal_target: 1000.0,
          investable_surplus: 1200.0,
          has_goals: true,
          goal_count: 1,
          months_back: 0,
        }}
      />,
    )
    expect(screen.getByTestId('tool-card')).toBeTruthy()
    expect(screen.getByTestId('tool-card-value-investable_surplus').textContent).toMatch(/1,200/)
  })

  it('renders an error card when result has an error key', () => {
    render(
      <ToolCard
        tool="get_totals"
        result={{ error: 'User not resolved for this query.' }}
      />,
    )
    expect(screen.getByTestId('tool-card')).toBeTruthy()
    expect(screen.getByTestId('tool-card').textContent).toMatch(/User not resolved/)
  })

  it('renders nothing for null results', () => {
    const { container } = render(
      <ToolCard tool="get_totals" result={null as unknown as Record<string, unknown>} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders a category spend card with merchant name', () => {
    render(
      <ToolCard
        tool="get_merchant_spend"
        result={{
          merchant: 'STARBUCKS',
          total_spend: 200.0,
          transaction_count: 1,
          months_back: 0,
        }}
      />,
    )
    expect(screen.getByTestId('tool-card')).toBeTruthy()
    expect(screen.getByTestId('tool-card-value-merchant').textContent).toMatch(/STARBUCKS/)
    expect(screen.getByTestId('tool-card-value-total_spend').textContent).toMatch(/200/)
  })
})
