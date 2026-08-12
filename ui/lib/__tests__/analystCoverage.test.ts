import { describe, expect, it } from 'vitest'
import { analystCoverageEmptyMessage } from '../analystCoverage'

describe('analystCoverageEmptyMessage', () => {
  it('does not blame Finnhub configuration when the provider responded without consensus', () => {
    expect(analystCoverageEmptyMessage(0)).toBe(
      'Finnhub responded successfully, but did not publish analyst consensus for these holdings.',
    )
  })

  it('gives configuration and connectivity guidance when requests failed', () => {
    expect(analystCoverageEmptyMessage(1)).toBe(
      'Analyst coverage could not be retrieved for one or more holdings. Check the provider connection and server configuration.',
    )
  })
})
