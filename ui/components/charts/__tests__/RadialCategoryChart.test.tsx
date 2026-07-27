import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import RadialCategoryChart from '../RadialCategoryChart'

describe('RadialCategoryChart', () => {
  const data = [
    { id: '1', name: 'Housing', value: 1200, color: '#3b82f6' },
    { id: '2', name: 'Food', value: 400, color: '#10b981' },
    { id: '3', name: 'Transport', value: 300, color: '#f59e0b' },
  ]

  it('renders an SVG and a total label', () => {
    render(<RadialCategoryChart data={data} size={200} />)
    expect(screen.getByRole('img')).toBeInTheDocument()
    expect(screen.getByText('Total')).toBeInTheDocument()
    expect(screen.getByText('1,900')).toBeInTheDocument()
  })

  it('renders accessible buttons paths for each segment', () => {
    render(<RadialCategoryChart data={data} size={200} />)
    const buttons = screen.getAllByRole('button')
    expect(buttons.length).toBe(data.length)
    expect(buttons[0]).toHaveAttribute('aria-label', expect.stringContaining('Housing'))
  })

  it('calls onSelect when a segment is clicked', () => {
    const onSelect = vi.fn()
    render(<RadialCategoryChart data={data} size={200} onSelect={onSelect} />)
    const buttons = screen.getAllByRole('button')
    fireEvent.click(buttons[0])
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ name: 'Housing' }))
  })

  it('renders nothing when data is empty', () => {
    const { container } = render(<RadialCategoryChart data={[]} size={200} />)
    expect(container.querySelector('svg')).toBeInTheDocument()
    expect(screen.getByText('0')).toBeInTheDocument()
  })
})
