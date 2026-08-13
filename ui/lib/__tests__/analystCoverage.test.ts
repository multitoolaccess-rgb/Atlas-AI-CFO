import { describe, expect, it } from 'vitest'
import { analystCoverageEmptyMessage } from '../analystCoverage'

describe('analystCoverageEmptyMessage', () => {
  it('does not blame Finnhub configuration when the provider responded without consensus', () => {
    expect(
      analystCoverageEmptyMessage({ eligible: 4, covered: 0, requestErrors: 0 }),
    ).toBe(
      'Finnhub responded successfully, but did not publish analyst consensus for these holdings.',
    )
  })

  it('explains partial coverage without implying the whole provider is unavailable', () => {
    expect(
      analystCoverageEmptyMessage({ eligible: 35, covered: 30, requestErrors: 5 }),
    ).toBe(
      'Analyst coverage is partial. Atlas received consensus for 30 of 35 eligible holdings; 5 holdings did not return usable analyst data. Review those holdings or retry later.',
    )
  })

  it('describes an all-request failure without claiming the API key is missing', () => {
    expect(
      analystCoverageEmptyMessage({ eligible: 1, covered: 0, requestErrors: 1 }),
    ).toBe(
      'Analyst coverage could not be retrieved for any of the 1 eligible holding. 1 request did not return usable analyst data. Review holding symbols or retry later.',
    )
  })
})
