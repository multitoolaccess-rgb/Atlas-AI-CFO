import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import AnalystCoverageStatus from '../AnalystCoverageStatus'

const baseProps = {
  eligible: 35,
  covered: 30,
  requestErrors: 5,
  excluded: 1,
  loaded: true,
  batchError: null,
}

describe('AnalystCoverageStatus', () => {
  it('renders an accessible partial-coverage explanation', () => {
    render(<AnalystCoverageStatus {...baseProps} />)

    const warning = screen.getByTestId('analyst-coverage-warning')
    expect(warning).toHaveAttribute('role', 'status')
    expect(warning).toHaveAttribute('aria-live', 'polite')
    expect(warning).toHaveTextContent(
      'Atlas received consensus for 30 of 35 eligible holdings',
    )
    expect(warning).toHaveTextContent('5 holdings did not return usable analyst data')
    expect(warning).not.toHaveTextContent(/missing an API key|server configuration/i)
  })

  it('announces the in-flight state without showing a failure message', () => {
    render(
      <AnalystCoverageStatus
        {...baseProps}
        covered={0}
        requestErrors={0}
        loaded={false}
      />,
    )

    expect(screen.getByTestId('analyst-coverage-loading')).toHaveTextContent(
      'Loading coverage for 35 stocks…',
    )
    expect(screen.queryByTestId('analyst-coverage-warning')).not.toBeInTheDocument()
  })

  it('renders the all-failed state without inventing a configuration diagnosis', () => {
    render(
      <AnalystCoverageStatus
        {...baseProps}
        covered={0}
        requestErrors={35}
      />,
    )

    const empty = screen.getByTestId('analyst-coverage-empty')
    expect(empty).toHaveAttribute('role', 'status')
    expect(empty).toHaveAttribute('aria-live', 'polite')
    expect(empty).toHaveTextContent('could not be retrieved for any of the 35 eligible holdings')
    expect(empty).toHaveTextContent('did not return usable analyst data')
    expect(empty).not.toHaveTextContent(/missing an API key|server configuration/i)
  })
})
