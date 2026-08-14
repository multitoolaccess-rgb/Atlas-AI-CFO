import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }))
vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ replace, push: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/',
}))
import { AtlasFilterProvider } from '@/components/ui/AtlasFilterContext'
import AnalyticalContextBar from '@/components/ui/AnalyticalContextBar'
import AnalyticalPageFrame from '@/components/ui/AnalyticalPageFrame'
import { useAtlasFilters } from '@/components/ui/AtlasFilterContext'

function FilterControls() {
  const { isComparing, setIsComparing, setTimeRange } = useAtlasFilters()
  return <><button onClick={() => setIsComparing(true)}>Enable compare</button><button onClick={() => setTimeRange('30D')}>Set 30D</button><output>{String(isComparing)}</output></>
}

describe('analytical foundation contracts', () => {
  it('delegates the sole range selector to FloatingTimeRangeBar', () => {
    render(<AtlasFilterProvider><AnalyticalContextBar showCompare accountSlot={<span>Accounts</span>} pageSlot={<span>Category</span>} /></AtlasFilterProvider>)
    expect(screen.getByRole('radiogroup', { name: 'Time range' })).toBeInTheDocument()
    expect(screen.getAllByText('Range')).toHaveLength(1)
    const compare = screen.getByRole('checkbox', { name: 'Compare' })
    fireEvent.click(compare)
    expect(compare).toBeChecked()
  })

  it('can omit controls that do not affect its query', () => {
    const { container } = render(<AnalyticalContextBar showRange={false} coverage="98% coverage" freshness="Fresh" />)
    expect(screen.queryByRole('radiogroup', { name: 'Time range' })).not.toBeInTheDocument()
    expect(container).toHaveTextContent('98% coverage')
  })

  it('retains back-to-back compare and range changes before router params refresh', () => {
    render(<AtlasFilterProvider><FilterControls /></AtlasFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'Enable compare' }))
    fireEvent.click(screen.getByRole('button', { name: 'Set 30D' }))
    expect(replace).toHaveBeenLastCalledWith('?compare=true&range=30D', { scroll: false })
  })

  it('provides responsive rail and recoverable state slots without owning data', () => {
    const { rerender, container } = render(<AnalyticalPageFrame header={<h1>Cash Flow</h1>} primaryVisualization={<div>Chart</div>} attentionRail={<div>Attention</div>} drilldown={{ title: 'Evidence', preserveFilterContext: true }} />)
    expect(container.querySelector('[data-drilldown-preserves-context="true"]')).toBeInTheDocument()
    expect(screen.getByLabelText('Needs attention')).toBeInTheDocument()
    rerender(<AnalyticalPageFrame header={<h1>Cash Flow</h1>} state="error" stateSlot={<p>Retry safely</p>} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Retry safely')
  })
})
