import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Sidebar from '@/components/layout/Sidebar'
import { SidebarProvider } from '@/components/layout/SidebarContext'

describe('production Sidebar Money migration', () => {
  it('activates Money destinations while leaving Scout in the header fallback route', () => {
    render(<SidebarProvider><Sidebar /></SidebarProvider>)
    expect(screen.getByRole('link', { name: /Mission Control/i })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: 'Cash Flow' })).toHaveAttribute('href', '/cash-flow')
    expect(screen.getByRole('link', { name: 'Plan' })).toHaveAttribute('href', '/plan')
    expect(screen.getByRole('link', { name: 'Wealth' })).toHaveAttribute('href', '/wealth')
    expect(screen.getByRole('link', { name: 'Portfolio' })).toHaveAttribute('href', '/portfolio')
    expect(screen.getByRole('link', { name: 'Goals' })).toHaveAttribute('href', '/goals')
    expect(screen.queryByRole('link', { name: /^Debts$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /^Universe$/i })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Decisions' })).toHaveAttribute('href', '/decisions')
    expect(screen.getByRole('link', { name: 'Market Intelligence' })).toHaveAttribute('href', '/market-intelligence')
    expect(screen.getByRole('link', { name: 'Scenario Lab' })).toHaveAttribute('href', '/scenario-lab')
    expect(screen.queryByRole('link', { name: /Recommendations/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Market Briefs/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Budgeting/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Scout/i })).not.toBeInTheDocument()
  })
})
