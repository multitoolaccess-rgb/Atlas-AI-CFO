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
    expect(screen.queryByRole('link', { name: /Budgeting/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Scout/i })).not.toBeInTheDocument()
  })
})
