import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import InvestmentAssistantPage from '../page'

vi.mock('@/lib/investmentAssistant', () => ({
  resolveInvestmentAssistantContext: vi.fn(),
}))
vi.mock('@/lib/api', () => ({
  rulesService: { assistantChat: vi.fn(), getProfile: vi.fn().mockResolvedValue(null) },
}))

describe('Investment Scout', () => {
  it('exposes labeled, read-only context controls and safety boundary', () => {
    render(<InvestmentAssistantPage />)
    expect(screen.getByRole('main', { name: 'Investment Scout workspace' })).toBeInTheDocument()
    expect(screen.getByLabelText('Context type')).toBeInTheDocument()
    expect(screen.getByLabelText('Persisted context ID')).toBeInTheDocument()
    expect(screen.getByText(/security, discovery, and portfolio selectors are not enabled/i)).toBeInTheDocument()
    expect(screen.getByText(/cannot create recommendations/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Load context' })).toBeDisabled()
    expect(screen.queryByText(/JSON.stringify/i)).not.toBeInTheDocument()
  })
})
