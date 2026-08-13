import { expect, test } from 'vitest'
import { classifyMarketBriefError } from '../marketBriefs'

test('maps stable provider reason codes to safe actionable copy', () => {
  const result = classifyMarketBriefError({ response: { status: 503, data: { reason_code: 'insufficient_portfolio_coverage' } } })
  expect(result.reasonCode).toBe('insufficient_portfolio_coverage')
  expect(result.title).toMatch(/coverage/i)
  expect(result.recovery).toMatch(/omitted holdings/i)
  expect(result.message).not.toMatch(/provider payload|account|token|secret/i)
})

test('maps authentication status without exposing server details', () => {
  const result = classifyMarketBriefError({ response: { status: 401, data: { detail: 'secret provider exception' } } })
  expect(result.reasonCode).toBe('provider_authentication_failed')
  expect(result.message).not.toContain('secret provider exception')
})

test('maps a network failure to retryable transport guidance', () => {
  const result = classifyMarketBriefError({ message: 'AxiosError with raw provider payload' })
  expect(result.reasonCode).toBe('provider_transport_failure')
  expect(result.retryable).toBe(true)
  expect(result.message).not.toContain('raw provider payload')
})

test('carries bounded omitted symbols from the server response', () => {
  const result = classifyMarketBriefError({
    response: {
      status: 503,
      data: {
        reason_code: 'unsupported_symbol',
        omitted_symbols: ['NON40OJJ2', 'NON40OXLT', 'PENDING ACTIVITY'],
      },
    },
  })
  expect(result.reasonCode).toBe('unsupported_symbol')
  expect(result.omittedSymbols).toEqual(['NON40OJJ2', 'NON40OXLT', 'PENDING ACTIVITY'])
  expect(result.title).toMatch(/addressable/i)
})

test('drops malformed or oversized omitted symbols defensively', () => {
  const result = classifyMarketBriefError({
    response: {
      status: 503,
      data: {
        reason_code: 'unsupported_symbol',
        omitted_symbols: ['AAPL', 42, null, '', 'B', 'C', 'D', 'E', 'F'],
      },
    },
  })
  expect(result.omittedSymbols).toEqual(['AAPL', 'B', 'C', 'D', 'E', 'F'])
})
