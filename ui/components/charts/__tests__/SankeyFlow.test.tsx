import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import SankeyFlow from '../SankeyFlow'

describe('SankeyFlow', () => {
  const emptyPeriodNode = [{ name: 'No transactions this month', node_type: 'income' as const }]

  it('renders an honest empty state instead of invalid SVG geometry for zero-value flow data', () => {
    const { container } = render(
      <SankeyFlow
        nodes={emptyPeriodNode}
        links={[{ source: 0, target: 0, value: 0 }]}
      />,
    )

    expect(screen.getByText('No flow data yet')).toBeInTheDocument()
    expect(container.querySelector('svg')).not.toBeInTheDocument()
  })
})
