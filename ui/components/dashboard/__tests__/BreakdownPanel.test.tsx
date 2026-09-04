import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import BreakdownPanel from '../BreakdownPanel'
import type { DashboardBreakdownResponse } from '@/lib/api'

vi.mock('@/components/charts/SimpleDonutChart', () => ({
  default: ({
    data,
    onSelect,
    center,
  }: {
    data: { name: string }[]
    onSelect?: (datum: { name: string }) => void
    center?: React.ReactNode
  }) => (
    <div data-testid="simple-donut-mock">
      {center}
      <button type="button" onClick={() => data[0] && onSelect?.(data[0])}>
        select first category
      </button>
    </div>
  ),
}))

const breakdown: DashboardBreakdownResponse = {
  buckets: [
    { label: 'Essential', amount: 1234, color: '#dc2626', percentage: 100 },
  ],
  categories: [
    { label: 'Groceries', amount: 1234, color: '#dc2626', percentage: 100 },
  ],
  total_spend: 1234,
  period: '2026-08-01 to 2026-08-19',
}

describe('BreakdownPanel', () => {
  afterEach(() => cleanup())

  it('uses canonical categories and renders dollar amounts without overlap-prone layout', () => {
    render(<BreakdownPanel breakdown={breakdown} rangeLabel="Last 30 days" />)

    expect(screen.getAllByText('$1,234').length).toBeGreaterThan(0)
    expect(screen.getByText(/Last 30 days/)).toBeInTheDocument()
    expect(screen.getAllByText('Groceries').length).toBeGreaterThan(0)
    expect(screen.queryByText('Essential')).not.toBeInTheDocument()
  })

  it('forwards a category click to the shared drilldown handler', () => {
    const onSegmentClick = vi.fn()
    render(<BreakdownPanel breakdown={breakdown} onSegmentClick={onSegmentClick} />)

    fireEvent.click(screen.getByRole('button', { name: 'select first category' }))
    expect(onSegmentClick).toHaveBeenCalledWith('Groceries')
  })

  it('shows an explicit empty state when the selected range has no spending', () => {
    render(
      <BreakdownPanel
        breakdown={{ buckets: [], categories: [], total_spend: 0, period: '2026-08-01 to 2026-08-19' }}
        rangeLabel="Last 7 days"
      />,
    )

    expect(screen.getByText('No spending in this range')).toBeInTheDocument()
  })
})
