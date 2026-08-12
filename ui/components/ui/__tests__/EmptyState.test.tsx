import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import EmptyState from '../EmptyState'

describe('EmptyState', () => {
  it('answers what the feature is, why it matters, and what is next', () => {
    render(
      <EmptyState
        testId="example-empty"
        title="Start a plan"
        description="A plan gives your spending a clear purpose."
        action={<button type="button">Create plan</button>}
        guidance={<p>Use current data to review it later.</p>}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Start a plan' })).toBeInTheDocument()
    expect(screen.getByText('A plan gives your spending a clear purpose.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create plan' })).toBeInTheDocument()
    expect(screen.getByText('Use current data to review it later.')).toBeInTheDocument()
    const region = screen.getByTestId('example-empty')
    expect(region).toHaveAttribute('aria-labelledby', screen.getByRole('heading', { name: 'Start a plan' }).id)
  })

  it('does not invent an action when none is supplied', () => {
    render(<EmptyState testId="quiet-empty" title="Nothing here yet" description="The feature is waiting for source data." />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    const region = screen.getByTestId('quiet-empty')
    expect(region).toHaveAttribute('aria-labelledby')
    expect(screen.getByRole('heading', { name: 'Nothing here yet' }).id).toBeTruthy()
  })
})
