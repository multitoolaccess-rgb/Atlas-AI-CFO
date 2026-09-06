import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import SimpleDonutChart from '../SimpleDonutChart'

describe('SimpleDonutChart', () => {
  it('renders a fillable path when a single segment fills 100% of the ring', () => {
    // Regression: a single 100% segment produced ONE arc command whose start
    // and end points coincide, which per the SVG spec draws nothing — the
    // fill vanished and only the thin dark stroke showed (a "grey ring").
    // The path must now be split into two semicircle sectors (2 'M' commands)
    // so the fill always paints.
    const { container } = render(
      <SimpleDonutChart
        data={[{ id: 'flexible', name: 'Flexible', value: 123428, color: '#FBBF24' }]}
        size={220}
        thickness={44}
      />,
    )

    const path = container.querySelector('svg path')
    expect(path).toBeInTheDocument()
    const d = path?.getAttribute('d') ?? ''
    expect(d.match(/M /g)?.length).toBe(2)
    // Every sector closes with Z so the annulus area is fillable.
    expect(d.match(/Z/g)?.length).toBe(2)
  })

  it('renders one sector per segment for partial shares', () => {
    const { container } = render(
      <SimpleDonutChart
        data={[
          { id: 'flexible', name: 'Flexible', value: 210183, color: '#FBBF24' },
          { id: 'other', name: 'Other', value: 26075, color: '#2DD4BF' },
        ]}
      />,
    )

    const paths = Array.from(container.querySelectorAll('svg path'))
    // Two segments → two sector paths, each a single closed loop.
    expect(paths).toHaveLength(2)
    for (const p of paths) {
      const d = p.getAttribute('d') ?? ''
      expect(d.match(/M /g)?.length).toBe(1)
      expect(d.endsWith('Z')).toBe(true)
    }
  })

  it('renders the background track ring', () => {
    const { container } = render(
      <SimpleDonutChart data={[{ id: 'a', name: 'A', value: 1, color: '#FBBF24' }]} />,
    )
    const track = container.querySelector('circle')
    expect(track).toBeInTheDocument()
    expect(track?.getAttribute('fill')).toBe('none')
  })
})