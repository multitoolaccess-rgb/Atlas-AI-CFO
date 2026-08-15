import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/components/layout/PageLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

import HelpPage from '@/app/help/page'

describe('System Help destination', () => {
  it('documents the final product structure and safe recovery boundaries', () => {
    render(<HelpPage />)

    expect(screen.getByRole('heading', { name: 'Help' })).toBeInTheDocument()
    expect(screen.getByTestId('help-navigation')).toHaveTextContent('Mission Control')
    expect(screen.getByTestId('help-navigation')).toHaveTextContent('System')
    expect(screen.getByText(/accepting a decision does not execute it/i)).toBeInTheDocument()
    expect(screen.getByText(/never paste credentials/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /System/i })).toHaveAttribute('href', '/data-connections')
  })

  it('keeps FAQ disclosure keyboard and screen-reader state explicit', () => {
    render(<HelpPage />)
    const firstQuestion = screen.getByRole('button', { name: 'Where should I start?' })
    const firstPanel = document.getElementById('faq-panel-0')

    expect(firstQuestion).toHaveAttribute('aria-expanded', 'true')
    expect(firstPanel).toBeVisible()

    fireEvent.click(firstQuestion)
    expect(firstQuestion).toHaveAttribute('aria-expanded', 'false')
    expect(firstPanel).not.toBeVisible()

    fireEvent.click(firstQuestion)
    expect(firstQuestion).toHaveAttribute('aria-expanded', 'true')
    expect(firstPanel).toBeVisible()
  })
})
