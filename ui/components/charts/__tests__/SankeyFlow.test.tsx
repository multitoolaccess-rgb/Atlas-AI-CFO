import { describe, expect, it } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
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

  // Salary → Expenses → Uncategorized → Debt chain: a single source node, one
  // group node, and two category nodes. Hover must be stable (one highlight
  // target) and emphasize the hovered element plus its connections.
  const chainNodes = [
    { name: 'Salary', node_type: 'income' as const },
    { name: 'Expenses', node_type: 'expense' as const },
    { name: 'Uncategorized', node_type: 'expense' as const },
    { name: 'Debt', node_type: 'debt' as const },
  ]
  const chainLinks = [
    { source: 0, target: 1, value: 100 },
    { source: 1, target: 2, value: 60 },
    { source: 2, target: 3, value: 20 },
  ]

  function linkPathOpacity(container: HTMLElement, index: number): string | null {
    return container.querySelector(`#sankey-link-path-${index}`)?.getAttribute('opacity') ?? null
  }

  // Opacity now lives on the node's BAR rect (the group itself is clean so
  // labels never inherit dimming or the glow filter).
  function nodeOpacity(container: HTMLElement, index: number): string | null {
    return container
      .querySelector(`#sankey-node-${index} rect`)
      ?.getAttribute('style')
      ?.match(/(?:^|;)\s*opacity:\s*([^;]+)/)?.[1] ?? null
  }

  function nodeLabelOpacity(container: HTMLElement, index: number): string | null {
    return container
      .querySelector(`#sankey-node-${index} text`)
      ?.getAttribute('style')
      ?.match(/(?:^|;)\s*opacity:\s*([^;]+)/)?.[1] ?? null
  }

  function groupInlineStyle(container: HTMLElement, index: number): string | null {
    return container.querySelector(`#sankey-node-${index}`)?.getAttribute('style') ?? null
  }

  it('highlights the connected flow when a node is hovered and dims disconnected elements', () => {
    const { container } = render(<SankeyFlow nodes={chainNodes} links={chainLinks} />)

    // Initial state: everything fully visible.
    expect(linkPathOpacity(container, 0)).toBe('1')
    expect(linkPathOpacity(container, 1)).toBe('1')
    expect(linkPathOpacity(container, 2)).toBe('1')

    // Hover the middle node (Expenses).
    fireEvent.mouseEnter(screen.getByRole('option', { name: /^Expenses,/ }))

    // Both links touching Expenses stay bright; the disconnected link dims.
    expect(linkPathOpacity(container, 0)).toBe('0.85')
    expect(linkPathOpacity(container, 1)).toBe('0.85')
    expect(linkPathOpacity(container, 2)).toBe('0.08')
    // Connected nodes stay bright; the disconnected node's BAR dims.
    expect(nodeOpacity(container, 0)).toBe('1')
    expect(nodeOpacity(container, 2)).toBe('1')
    expect(nodeOpacity(container, 3)).toBe('0.3')
    // Regression: dimming must never hide the labels. The disconnected
    // node's bar drops to 0.3 but its label clamps to a readable 0.7, and
    // the group itself carries no opacity/filter (so text can't inherit
    // dimming or the glow blur).
    expect(nodeLabelOpacity(container, 0)).toBe('1')
    expect(nodeLabelOpacity(container, 3)).toBe('0.7')
    const groupStyle = groupInlineStyle(container, 3) ?? ''
    expect(groupStyle).not.toContain('opacity')
    expect(groupStyle).not.toContain('filter')

    // Moving the pointer to a different node must not reset the highlight to
    // "everything bright" (the old flicker): hover the source node instead.
    fireEvent.mouseEnter(screen.getByRole('option', { name: /^Salary,/ }))
    expect(linkPathOpacity(container, 0)).toBe('0.85')
    expect(linkPathOpacity(container, 1)).toBe('0.08')
    expect(linkPathOpacity(container, 2)).toBe('0.08')
    expect(nodeOpacity(container, 1)).toBe('1')
    expect(nodeOpacity(container, 2)).toBe('0.3')
    // Labels stay readable even when their bars dim.
    expect(nodeLabelOpacity(container, 2)).toBe('0.7')

    // Leaving the whole diagram clears the highlight completely.
    fireEvent.mouseLeave(container.querySelector('svg')!)
    expect(linkPathOpacity(container, 0)).toBe('1')
    expect(linkPathOpacity(container, 1)).toBe('1')
    expect(linkPathOpacity(container, 2)).toBe('1')
    expect(nodeOpacity(container, 3)).toBe('1')
  })

  it('highlights connected links when a link is hovered and restores on leave', () => {
    const { container } = render(<SankeyFlow nodes={chainNodes} links={chainLinks} />)

    // The first path inside each link group is the invisible wide hit area
    // (the visible path has pointer-events disabled so it cannot steal hover).
    const firstLinkGroup = container.querySelector('#sankey-links g')!
    fireEvent.mouseEnter(firstLinkGroup.querySelector('path')!)

    expect(linkPathOpacity(container, 0)).toBe('1')
    expect(linkPathOpacity(container, 1)).toBe('0.85')
    expect(linkPathOpacity(container, 2)).toBe('0.08')
    expect(nodeOpacity(container, 2)).toBe('0.3')

    fireEvent.mouseLeave(container.querySelector('svg')!)
    expect(linkPathOpacity(container, 0)).toBe('1')
    expect(linkPathOpacity(container, 1)).toBe('1')
    expect(linkPathOpacity(container, 2)).toBe('1')
  })

  it('renders a visible endpoint marker for every category link', () => {
    const nodes = [
      { name: 'Income', node_type: 'income' as const, level: 1 },
      { name: 'Debt', node_type: 'expense' as const, level: 2 },
      { name: 'Credit Card Payments', node_type: 'expense' as const, level: 3 },
    ]
    const links = [
      { source: 0, target: 1, value: 48_718 },
      { source: 1, target: 2, value: 48_718 },
    ]
    const { container } = render(<SankeyFlow nodes={nodes} links={links} />)

    const endpoint = container.querySelector('#sankey-category-endpoints line')
    expect(endpoint).toBeInTheDocument()
    expect(Number(endpoint?.getAttribute('stroke-width'))).toBeGreaterThan(0)
  })

  it('never lets the traveling particle or the visible path capture hover', () => {
    const { container } = render(<SankeyFlow nodes={chainNodes} links={chainLinks} />)

    const visiblePath = container.querySelector('#sankey-link-path-0')!
    const particle = container.querySelector('#sankey-links g:nth-child(2) circle')!
    expect(visiblePath).toHaveStyle({ pointerEvents: 'none' })
    expect(particle).toHaveStyle({ pointerEvents: 'none' })
  })

  // A dense final column (many categories) used to consume the whole layout
  // height in 24px padding gaps, collapsing the ONE global scale d3-sankey
  // applies to every node — so even the largest income flow rendered as a
  // ~26px sliver. The layout must cap each column's padding budget so node
  // bars stay legible. See MAX_COLUMN_PADDING_FRACTION in SankeyFlow.
  const denseNodes = [
    { name: 'Base Salary', node_type: 'income' as const, level: 0 },
    { name: 'Total Income', node_type: 'income' as const, level: 1 },
    { name: 'Expenses', node_type: 'expense' as const, level: 2 },
    { name: 'Debt', node_type: 'expense' as const, level: 2 },
    { name: 'Overspend', node_type: 'outcome' as const, level: 0 },
    { name: 'Uncategorized', node_type: 'expense' as const, level: 3 },
    { name: 'Credit Card Payments', node_type: 'expense' as const, level: 3 },
    { name: 'Mortgage', node_type: 'expense' as const, level: 3 },
    { name: 'Transportation', node_type: 'expense' as const, level: 3 },
    { name: 'Bills & Utilities', node_type: 'expense' as const, level: 3 },
    { name: 'Life Insurance', node_type: 'expense' as const, level: 3 },
    { name: 'Loan Payments', node_type: 'expense' as const, level: 3 },
    { name: 'Shopping', node_type: 'expense' as const, level: 3 },
    { name: 'Brokerage Buys', node_type: 'expense' as const, level: 3 },
    { name: 'Travel', node_type: 'expense' as const, level: 3 },
    { name: 'Interest Paid', node_type: 'expense' as const, level: 3 },
    { name: 'Groceries', node_type: 'expense' as const, level: 3 },
    { name: 'Food & Dining', node_type: 'expense' as const, level: 3 },
    { name: 'Housing', node_type: 'expense' as const, level: 3 },
    { name: 'Education', node_type: 'expense' as const, level: 3 },
  ]
  const denseLinks = [
    { source: 0, target: 1, value: 122534 },
    { source: 4, target: 1, value: 114396 },
    { source: 1, target: 2, value: 84628 },
    { source: 1, target: 3, value: 84275 },
    { source: 2, target: 5, value: 52150 },
    { source: 3, target: 6, value: 48718 },
    { source: 3, target: 7, value: 23906 },
    { source: 2, target: 8, value: 19578 },
    { source: 2, target: 9, value: 10538 },
    { source: 3, target: 10, value: 8519 },
    { source: 3, target: 11, value: 2848 },
    { source: 2, target: 12, value: 1354 },
    { source: 2, target: 13, value: 1200 },
    { source: 2, target: 14, value: 463 },
    { source: 3, target: 15, value: 285 },
    { source: 2, target: 16, value: 241 },
    { source: 2, target: 17, value: 199 },
    { source: 2, target: 18, value: 80 },
    { source: 2, target: 19, value: 25 },
  ]

  function nodeBarHeight(container: HTMLElement, index: number): number {
    const rect = container.querySelector(`#sankey-node-${index} rect`)
    return rect ? Number(rect.getAttribute('height')) : 0
  }

  it('keeps income bars legible when a dense category column would collapse the layout', () => {
    const { container } = render(<SankeyFlow nodes={denseNodes} links={denseLinks} />)

    // Regression: with 24px gaps across ~15 category nodes, d3-sankey's
    // single global scale rendered Base Salary ~26px tall. The adaptive
    // padding budget must keep the biggest income flow clearly visible.
    expect(nodeBarHeight(container, 0)).toBeGreaterThan(100)
    expect(nodeBarHeight(container, 4)).toBeGreaterThan(100)
    // The dense column still fits the layout: nothing can exceed it.
    expect(nodeBarHeight(container, 0)).toBeLessThanOrEqual(400)
  })

  it('caps the rendered height to the viewport in focus mode', () => {
    const { container } = render(<SankeyFlow nodes={chainNodes} links={chainLinks} fitViewport />)
    const svg = container.querySelector('svg')!
    expect(svg).toHaveStyle({ maxHeight: 'calc(100vh - 16rem)' })
    expect(svg).toHaveStyle({ height: 'auto' })
  })

  it('renders unconstrained when not in focus mode', () => {
    const { container } = render(<SankeyFlow nodes={chainNodes} links={chainLinks} />)
    const svg = container.querySelector('svg')!
    expect(svg.style.maxHeight).toBe('')
  })
})
