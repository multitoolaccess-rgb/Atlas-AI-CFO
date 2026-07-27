import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import TimeRangeSelector from '@/components/ui/TimeRangeSelector'

describe('TimeRangeSelector', () => {
  it('renders all 8 preset buttons', () => {
    render(<TimeRangeSelector value="YTD" onChange={vi.fn()} />)
    const buttons = screen.getAllByRole('radio')
    expect(buttons).toHaveLength(8)
  })

  it('marks the active preset with aria-checked=true', () => {
    render(<TimeRangeSelector value="30D" onChange={vi.fn()} />)
    const active = screen.getByRole('radio', { name: '30D' })
    expect(active).toHaveAttribute('aria-checked', 'true')
  })

  it('marks inactive presets with aria-checked=false', () => {
    render(<TimeRangeSelector value="30D" onChange={vi.fn()} />)
    const inactive = screen.getByRole('radio', { name: 'YTD' })
    expect(inactive).toHaveAttribute('aria-checked', 'false')
  })

  it('calls onChange with the selected preset when clicked', () => {
    const onChange = vi.fn()
    render(<TimeRangeSelector value="YTD" onChange={onChange} />)
    fireEvent.click(screen.getByRole('radio', { name: '7D' }))
    expect(onChange).toHaveBeenCalledWith('7D')
  })

  it('has a radiogroup role for accessibility', () => {
    render(<TimeRangeSelector value="YTD" onChange={vi.fn()} />)
    const group = screen.getByRole('radiogroup')
    expect(group).toHaveAttribute('aria-label', 'Time range')
  })

  it('renders the ALL preset', () => {
    render(<TimeRangeSelector value="YTD" onChange={vi.fn()} />)
    expect(screen.getByRole('radio', { name: 'All' })).toBeInTheDocument()
  })
})
