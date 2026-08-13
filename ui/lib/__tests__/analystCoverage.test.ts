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

  it('does not say “any of the N” when only some requests failed', () => {
    // Regression: the user's portfolio reported "8 eligible holdings, 1
    // request did not return usable data" — the old copy claimed ALL 8
    // failed. With 1 error + 7 no-consensus results, the message must
    // not contradict its own count.
    expect(
      analystCoverageEmptyMessage({ eligible: 8, covered: 0, requestErrors: 1 }),
    ).toBe(
      'Analyst coverage could not be retrieved for 1 holding of 8 eligible holdings; the remaining 7 holdings returned no published consensus. Review holding symbols or retry later.',
    )
  })
})
