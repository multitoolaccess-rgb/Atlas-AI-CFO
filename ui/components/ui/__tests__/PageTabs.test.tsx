import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PageTabs, { withTabQuery } from '@/components/ui/PageTabs'

const tabs = [{ id: 'overview', label: 'Overview', panel: <p>Overview panel</p> }, { id: 'income', label: 'Income', panel: <p>Income panel</p> }, { id: 'spending', label: 'Spending', panel: <p>Spending panel</p> }, { id: 'transactions', label: 'Transactions', disabled: true, panel: <p>Transactions panel</p> }] as const

describe('PageTabs', () => {
  it('uses roving focus and skips disabled tabs with keyboard navigation', () => {
    const onChange = vi.fn()
    render(<PageTabs tabs={tabs} defaultActiveId="overview" onChange={onChange} />)
    const overview = screen.getByRole('tab', { name: 'Overview' })
    fireEvent.keyDown(overview, { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: 'Income' })).toHaveFocus()
    expect(onChange).toHaveBeenLastCalledWith('income')
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Income' }), { key: 'End' })
    expect(screen.getByRole('tab', { name: 'Spending' })).toHaveFocus()
    expect(screen.getByRole('tab', { name: 'Transactions' })).toBeDisabled()
  })

  it('reports selected state and provides the URL-state-compatible query key', () => {
    render(<PageTabs tabs={tabs} activeId="income" queryKey="view" />)
    expect(screen.getByRole('tab', { name: 'Income' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Income panel')
    fireEvent.click(screen.getByRole('tab', { name: 'Spending' }))
    expect(screen.getByTestId('page-tabs')).toHaveAttribute('data-mobile-overflow', 'horizontal')
    expect(withTabQuery('range=YTD&account=all', 'view', 'spending')).toBe('?range=YTD&account=all&view=spending')
  })
})
