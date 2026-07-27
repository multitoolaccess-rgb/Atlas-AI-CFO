'use client'

/**
 * Vitest test for the Phase 9 Analyst Insights section.
 *
 * Tests:
 *   - renders the static recommendations on mount (no fetch on mount).
 *   - clicking "Load ratings" fetches via getAnalystRatings.
 *   - the input is uppercased before the API call (cache-friendly).
 *   - the recommendation breakdown + price target render on success.
 *   - a backend 502 surfaces a friendly retry banner (no stack trace).
 *
 * Mocking strategy mirrors ImportStatementUpload.test.tsx:
 *   - vi.mock is hoisted above ALL top-level declarations including
 *     `const getAnalystRatings = vi.fn()`.
 *   - vi.hoisted registers a factory to ALSO be hoisted so the mock
 *     function exists before the vi.mock factory closes over it.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'

// REGISTER first so vi.mock can safely close over the same reference.
const { getAnalystRatings } = vi.hoisted(() => ({
  getAnalystRatings: vi.fn(),
}))

const { rulesServiceModule } = vi.hoisted(() => ({
  rulesServiceModule: {
    listAccounts: vi.fn().mockResolvedValue([]),
    listBatches: vi.fn().mockResolvedValue([]),
    getAnalystRatings: (...args: unknown[]) => getAnalystRatings(...args),
    // PageLayout's bootstrap useEffect calls getProfile() once at
    // mount for the header avatar. Provide a resolved stub.
    getProfile: vi
      .fn()
      .mockResolvedValue({ id: 1, email: 'alex@test.com', full_name: 'Alex' }),
  },
}))

vi.mock('@/lib/api', () => ({
  rulesService: rulesServiceModule,
}))

import RecommendationsPage from '../page'

describe('Recommendations Page -- Analyst Insights section', () => {
  beforeEach(() => {
    getAnalystRatings.mockReset()
  })

  it('renders static recommendations on mount', () => {
    render(<RecommendationsPage />)
    expect(screen.getByText(/AI Recommendations/i)).toBeInTheDocument()
    // At least one of the static cards is visible.
    expect(screen.getByText(/Rebalance emerging markets/i)).toBeInTheDocument()
  })

  it('does NOT call the API until the user clicks Load', () => {
    render(<RecommendationsPage />)
    expect(getAnalystRatings).not.toHaveBeenCalled()
  })

  it('uppercases the ticker before calling the API', async () => {
    getAnalystRatings.mockResolvedValueOnce({
      symbol: 'AAPL',
      recommendation_trends: [
        { period: '2025-05', strongBuy: 12, buy: 18, hold: 7, sell: 1, strongSell: 0 },
      ],
      price_target: { targetMean: 232.1, targetMedian: 230, targetHigh: 280, targetLow: 165 },
    })

    render(<RecommendationsPage />)
    const tickerInput = screen.getByTestId('analyst-ticker-input')
    fireEvent.change(tickerInput, { target: { value: 'aapl' } })

    const loadBtn = screen.getByTestId('analyst-load-btn')
    fireEvent.click(loadBtn)

    await waitFor(() => {
      expect(getAnalystRatings).toHaveBeenCalledWith('aapl')
    })

    // The display reflects the uppercased symbol.
    await waitFor(() => {
      expect(screen.getByTestId('analyst-symbol').textContent).toContain('AAPL')
    })
  })

  it('renders the recommendation breakdown + price target on success', async () => {
    getAnalystRatings.mockResolvedValueOnce({
      symbol: 'AAPL',
      recommendation_trends: [
        { period: '2025-05', strongBuy: 12, buy: 18, hold: 7, sell: 1, strongSell: 0 },
        { period: '2025-04', strongBuy: 10, buy: 16, hold: 9, sell: 1, strongSell: 0 },
      ],
      price_target: { targetMean: 232.1, targetMedian: 230, targetHigh: 280, targetLow: 165 },
    })

    render(<RecommendationsPage />)
    fireEvent.change(screen.getByTestId('analyst-ticker-input'), {
      target: { value: 'AAPL' },
    })
    fireEvent.click(screen.getByTestId('analyst-load-btn'))

    await waitFor(() => {
      // Aggregate: latest-month totals = 12+18+7+1+0 (buy=30, hold=7, sell=1).
      expect(screen.getByTestId('analyst-total-buy').textContent).toContain('30')
      expect(screen.getByTestId('analyst-total-hold').textContent).toContain('7')
      expect(screen.getByTestId('analyst-total-sell').textContent).toContain('1')
      expect(screen.getByTestId('analyst-price-target').textContent).toContain('232')
    })
  })

  it('surfaces a friendly retry banner on backend 502', async () => {
    getAnalystRatings.mockRejectedValueOnce({
      response: { status: 502, data: { detail: 'Finnhub upstream returned HTTP 500.' } },
      message: 'Request failed',
    })

    render(<RecommendationsPage />)
    fireEvent.change(screen.getByTestId('analyst-ticker-input'), {
      target: { value: 'AAPL' },
    })
    fireEvent.click(screen.getByTestId('analyst-load-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('analyst-error')).toBeInTheDocument()
    })
  })
})
