import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ExpandableCard from '@/components/dashboard/ExpandableCard'

describe('ExpandableCard', () => {
  it('renders title and children', () => {
    render(
      <ExpandableCard title="Test Card">
        <p>Card content</p>
      </ExpandableCard>,
    )
    expect(screen.getByText('Test Card')).toBeInTheDocument()
    expect(screen.getByText('Card content')).toBeInTheDocument()
  })

  it('renders subtitle when provided', () => {
    render(
      <ExpandableCard title="Test Card" subtitle="A subtitle">
        <p>Content</p>
      </ExpandableCard>,
    )
    expect(screen.getByText('A subtitle')).toBeInTheDocument()
  })

  it('does not show expand button when no expandedContent', () => {
    render(
      <ExpandableCard title="Test Card">
        <p>Content</p>
      </ExpandableCard>,
    )
    expect(screen.queryByRole('button', { name: /expand/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /collapse/i })).not.toBeInTheDocument()
  })

  it('shows expand button when expandedContent is provided', () => {
    render(
      <ExpandableCard title="Test Card" expandedContent={<p>Expanded!</p>}>
        <p>Content</p>
      </ExpandableCard>,
    )
    expect(screen.getByRole('button', { name: 'Expand' })).toBeInTheDocument()
  })

  it('toggles expanded state on button click', () => {
    render(
      <ExpandableCard title="Test Card" expandedContent={<p>Expanded!</p>}>
        <p>Content</p>
      </ExpandableCard>,
    )
    const toggle = screen.getByRole('button', { name: 'Expand' })
    fireEvent.click(toggle)
    expect(screen.getByRole('button', { name: 'Collapse' })).toBeInTheDocument()
    expect(screen.getByText('Expanded!')).toBeInTheDocument()
  })

  it('has aria-expanded attribute on the toggle button', () => {
    render(
      <ExpandableCard title="Test Card" expandedContent={<p>Expanded!</p>}>
        <p>Content</p>
      </ExpandableCard>,
    )
    const toggle = screen.getByRole('button', { name: 'Expand' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
  })

  it('calls onExpand callback when toggled', () => {
    const onExpand = vi.fn()
    render(
      <ExpandableCard title="Test Card" expandedContent={<p>Expanded!</p>} onExpand={onExpand}>
        <p>Content</p>
      </ExpandableCard>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Expand' }))
    expect(onExpand).toHaveBeenCalledWith(true)
    fireEvent.click(screen.getByRole('button', { name: 'Collapse' }))
    expect(onExpand).toHaveBeenCalledWith(false)
  })

  it('opens a reusable focus mode even without expanded details', () => {
    render(
      <ExpandableCard title="Focus Card">
        <p>Chart content</p>
      </ExpandableCard>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Open focus mode' }))
    expect(screen.getByTestId('dashboard-focus-layer')).toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: 'Focus Card focus mode' })).toBeInTheDocument()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByTestId('dashboard-focus-layer')).not.toBeInTheDocument()
  })

  it('starts expanded when defaultExpanded is true', () => {
    render(
      <ExpandableCard title="Test Card" expandedContent={<p>Expanded!</p>} defaultExpanded>
        <p>Content</p>
      </ExpandableCard>,
    )
    expect(screen.getByRole('button', { name: 'Collapse' })).toBeInTheDocument()
    expect(screen.getByText('Expanded!')).toBeInTheDocument()
  })
})
