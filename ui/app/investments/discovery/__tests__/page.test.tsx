import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import InvestmentDiscoveryPage from '@/app/investments/discovery/page'

vi.mock('@/components/layout/PageLayout', () => ({ default: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/components/ui/PageHeader', () => ({ default: ({ title, description }: { title: string; description?: string }) => <header><h1>{title}</h1><p>{description}</p></header> }))
vi.mock('@/lib/investmentDiscovery', () => ({
  investmentDiscovery: { list: vi.fn().mockResolvedValue({ candidates: [], universe: 'portfolio', as_of: '2026-01-01T00:00:00Z', methodology_version: 'v1', omitted_count: 0 }), compare: vi.fn() },
}))

describe('UI-09 discovery', () => {
  it('renders the bounded universe controls and empty state', async () => {
    render(<InvestmentDiscoveryPage />)
    await waitFor(() => expect(screen.getByText(/No candidates in this universe/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'My portfolio' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'S&P 500' })).toBeInTheDocument()
    expect(screen.getByText(/does not create recommendations/i)).toBeInTheDocument()
  })
})
