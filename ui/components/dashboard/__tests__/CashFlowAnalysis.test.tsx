import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import CashFlowAnalysis from '../CashFlowAnalysis'

describe('CashFlowAnalysis', () => {
  afterEach(() => cleanup())

  it('renders the range-scoped income, spending, and net values', () => {
    render(
      <CashFlowAnalysis
        income={1200}
        expenses={450}
        rangeLabel="Last 30 days"
      />,
    )

    expect(screen.getByText('Last 30 days')).toBeInTheDocument()
    expect(screen.getByText('+$1,200')).toBeInTheDocument()
    expect(screen.getByText('−$450')).toBeInTheDocument()
    expect(screen.getByText('+$750')).toBeInTheDocument()
  })

  it('updates its label and numbers when the active range changes', () => {
    const { rerender } = render(
      <CashFlowAnalysis income={1200} expenses={450} rangeLabel="Last 30 days" />,
    )

    rerender(
      <CashFlowAnalysis income={300} expenses={500} rangeLabel="Last 7 days" />,
    )

    expect(screen.queryByText('Last 30 days')).not.toBeInTheDocument()
    expect(screen.getByText('Last 7 days')).toBeInTheDocument()
    expect(screen.getByText('+$300')).toBeInTheDocument()
    expect(screen.getByText('−$500')).toBeInTheDocument()
    expect(screen.getByText('−$200')).toBeInTheDocument()
  })
})
