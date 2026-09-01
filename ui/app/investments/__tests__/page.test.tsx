import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import InvestmentsPage from '@/app/investments/page'

vi.mock('@/components/layout/PageLayout', () => ({ default: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/components/ui/PageHeader', () => ({ default: ({ title, description }: { title: string; description?: string }) => <header><h1>{title}</h1><p>{description}</p></header> }))

describe('Investment Command Center UI-02 route', () => {
  it('renders canonical investment surfaces without execution actions', () => {
    render(<InvestmentsPage />)
    expect(screen.getByRole('heading', { name: 'Command Center' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Daily Investment Brief/i })).toHaveAttribute('href', '/investments/brief')
    expect(screen.getByRole('link', { name: /Portfolio intelligence/i })).toHaveAttribute('href', '/portfolio')
    expect(screen.getByRole('link', { name: /Research workspace/i })).toHaveAttribute('href', '/market-intelligence')
    expect(screen.queryByRole('button', { name: /buy|sell|execute|trade|rebalance|order/i })).not.toBeInTheDocument()
    expect(screen.getByText(/No execution actions/i)).toBeInTheDocument()
  })

  it('supports the slash shortcut for surface search', () => {
    render(<InvestmentsPage />)
    const input = screen.getByRole('searchbox')
    fireEvent.keyDown(window, { key: '/' })
    expect(document.activeElement).toBe(input)
  })
})
