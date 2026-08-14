import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Sidebar from '@/components/layout/Sidebar'
import { SidebarProvider } from '@/components/layout/SidebarContext'

describe('production Sidebar compatibility during Step 1', () => {
  it('retains the existing route destinations and Scout fallback', () => {
    render(<SidebarProvider><Sidebar /></SidebarProvider>)
    expect(screen.getByRole('link', { name: /Overview/i })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: /Scout/i })).toHaveAttribute('href', '/assistant')
    expect(screen.getByRole('link', { name: /Budgeting/i })).toHaveAttribute('href', '/budgeting')
    expect(screen.queryByRole('link', { name: 'Cash Flow' })).not.toBeInTheDocument()
  })
})
