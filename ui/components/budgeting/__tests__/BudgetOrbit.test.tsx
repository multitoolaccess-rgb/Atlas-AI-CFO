import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import BudgetOrbit from '../BudgetOrbit'

describe('BudgetOrbit', () => {
  it('is hidden from assistive technology and contains no values', () => {
    render(<BudgetOrbit />)
    const orbit = screen.getByTestId('budget-orbit')
    expect(orbit).toHaveAttribute('aria-hidden', 'true')
    expect(orbit.textContent).toBe('')
  })
})
