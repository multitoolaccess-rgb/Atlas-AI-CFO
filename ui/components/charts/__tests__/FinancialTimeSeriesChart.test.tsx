import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import FinancialTimeSeriesChart from '@/components/charts/FinancialTimeSeriesChart'

const series = [{ key: 'value', name: 'Value', color: '#2563eb' }]

describe('FinancialTimeSeriesChart UI-06', () => {
  it('renders canonical metadata and an accessible tabular fallback', () => {
    render(<FinancialTimeSeriesChart title="Price trend" data={[{ timestamp: '2026-08-01', value: 100 }, { timestamp: '2026-08-02', value: 101 }]} series={series} unit="USD" asOf="2026-08-02T16:00:00Z" source="server market projection" freshness="observed" />)
    expect(screen.getByRole('heading', { name: 'Price trend' })).toBeInTheDocument()
    expect(screen.getAllByText(/Unit: USD/)).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'View data table' }))
    expect(screen.getByRole('table')).toHaveTextContent('2026-08-01')
    expect(screen.getByRole('table')).toHaveTextContent('100')
  })

  it('preserves explicit unavailable state without fabricating a series', () => {
    render(<FinancialTimeSeriesChart title="Drawdown" data={[]} series={series} unit="ratio" freshness="insufficient_history" emptyMessage="Insufficient history for this view." />)
    expect(screen.getByText('Insufficient history for this view.')).toBeInTheDocument()
    expect(screen.getByText(/State: insufficient history/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'View data table' })).not.toBeInTheDocument()
  })

  it('does not introduce execution controls', () => {
    render(<FinancialTimeSeriesChart title="Portfolio exposure" data={[]} series={series} unit="percent" freshness="unavailable" />)
    expect(screen.queryByRole('button', { name: /buy|sell|execute|trade|order|rebalance/i })).not.toBeInTheDocument()
  })
})
