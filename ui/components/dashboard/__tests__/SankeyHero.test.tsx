import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import SankeyHero from '../SankeyHero'
import type { DashboardFlowsResponse } from '@/lib/api'

vi.mock('@/components/ui/CountUp', () => ({
  default: ({ end }: { end: number }) => <span>{end}</span>,
}))

vi.mock('@/components/charts/SankeyFlow', () => ({
  default: ({ displayValues }: { displayValues?: Record<string, number> }) => (
    <div data-testid="sankey-flow-mock">
      {displayValues?.['Total Income']}
    </div>
  ),
}))

const flows: DashboardFlowsResponse = {
  nodes: [
    { name: 'Salary', node_type: 'income', role: 'earn', group: 'Income', level: 0 },
    { name: 'Total Income', node_type: 'income', role: 'earn', group: 'Income', level: 1 },
    { name: 'Overspend', node_type: 'outcome', role: 'spend', level: 0 },
  ],
  links: [
    { source: 0, target: 1, value: 1000 },
    { source: 2, target: 1, value: 200 },
  ],
  period_start: '2026-01-01',
  period_end: '2026-01-31',
  total_income: 1000,
}

describe('SankeyHero', () => {
  afterEach(() => cleanup())

  it('passes earned income to the Total Income label even when overspend balances the layout', () => {
    render(<SankeyHero flows={flows} />)

    expect(screen.getByTestId('sankey-flow-mock')).toHaveTextContent('1000')
    expect(screen.getByTestId('sankey-total-income')).toHaveTextContent('1000')
    expect(screen.getByTestId('sankey-overspend-note')).toHaveTextContent(/not counted as earned income/i)
  })

  it('exposes focus mode for the main flow visualization', () => {
    render(<SankeyHero flows={flows} />)
    expect(screen.getByRole('button', { name: 'Open focus mode' })).toBeInTheDocument()
  })
})
