import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import InvestmentScoutResearchPage from '../page'

vi.mock('@/components/layout/PageLayout', () => ({ default: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/components/ui/PageHeader', () => ({ default: ({ title, description }: { title: string; description?: string }) => <header><h1>{title}</h1><p>{description}</p></header> }))
vi.mock('@/lib/investmentScout', () => ({
  researchInvestmentSecurity: vi.fn(),
  listInvestmentScoutRuns: vi.fn().mockResolvedValue([]),
  getInvestmentScoutRun: vi.fn(),
}))

describe('provider-backed Investment Context Scout', () => {
  it('renders bounded current-context controls and an explicit no-execution boundary', async () => {
    render(<InvestmentScoutResearchPage />)

    expect(screen.getByRole('main', { name: 'Investment Context Scout' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Run current-context research' })).toBeInTheDocument()
    expect(screen.getByLabelText('Context type')).toBeInTheDocument()
    expect(screen.getByLabelText('Canonical ID')).toBeInTheDocument()
    expect(screen.getByLabelText('Research question')).toBeInTheDocument()
    expect(screen.getByText(/Arbitrary URLs and general web search are not accepted/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Run current-context research' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Saved Scout runs' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(/No saved Scout runs are available for this owner/i)).toBeInTheDocument())
    expect(screen.getByText(/cannot create recommendations, decisions, outcomes, orders, trades, transfers, or portfolio changes/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /buy|sell|execute|order|trade|rebalance|transfer/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Research context' })).toBeDisabled()
  })
})
