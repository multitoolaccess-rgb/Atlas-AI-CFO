import { render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import MarketBriefArchive from '../MarketBriefArchive'

vi.mock('@/lib/marketBriefs', () => ({ listMarketBriefs: vi.fn().mockResolvedValue([]), getMarketBrief: vi.fn() }))

test('renders an accessible archive landmark', async () => {
  render(<MarketBriefArchive />)
  expect(screen.getByRole('heading', { name: /market intelligence briefs/i })).toBeInTheDocument()
  expect(await screen.findByRole('navigation', { name: /brief archive/i })).toBeInTheDocument()
})
