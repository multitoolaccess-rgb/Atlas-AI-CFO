import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import MarketBriefArchive from '../MarketBriefArchive'
import { getMarketBrief, listMarketBriefs } from '@/lib/marketBriefs'

vi.mock('@/lib/marketBriefs', () => ({ listMarketBriefs: vi.fn().mockResolvedValue([]), getMarketBrief: vi.fn() }))

afterEach(() => { vi.clearAllMocks() })

test('renders an accessible archive landmark', async () => {
  render(<MarketBriefArchive />)
  expect(screen.getByRole('heading', { name: /market intelligence briefs/i })).toBeInTheDocument()
  expect(await screen.findByRole('navigation', { name: /brief archive/i })).toBeInTheDocument()
})

test('clears a prior brief when a later selection fails', async () => {
  vi.mocked(listMarketBriefs).mockResolvedValue([{ brief_id: 'one', report_window: 'one', generated_at: 'now' }, { brief_id: 'two', report_window: 'two', generated_at: 'now' }])
  vi.mocked(getMarketBrief).mockResolvedValueOnce({ generated_at: 'one', sections: [], warnings: [] }).mockRejectedValueOnce(new Error('nope'))
  render(<MarketBriefArchive />)
  fireEvent.click(await screen.findByRole('button', { name: /brief for one/i }))
  expect(await screen.findByText(/as of one/i)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /brief for two/i }))
  expect(screen.queryByText(/as of one/i)).not.toBeInTheDocument()
  expect(await screen.findByText(/brief is unavailable/i)).toBeInTheDocument()
})

test('ignores a stale detail response after a newer selection', async () => {
  let firstResolve!: (value: any) => void
  let secondResolve!: (value: any) => void
  vi.mocked(listMarketBriefs).mockResolvedValue([{ brief_id: 'one', report_window: 'one', generated_at: 'now' }, { brief_id: 'two', report_window: 'two', generated_at: 'now' }])
  vi.mocked(getMarketBrief).mockImplementationOnce(() => new Promise(resolve => { firstResolve = resolve })).mockImplementationOnce(() => new Promise(resolve => { secondResolve = resolve }))
  render(<MarketBriefArchive />)
  fireEvent.click(await screen.findByRole('button', { name: /brief for one/i }))
  fireEvent.click(screen.getByRole('button', { name: /brief for two/i }))
  secondResolve({ generated_at: 'two', sections: [], warnings: [] })
  expect(await screen.findByText(/as of two/i)).toBeInTheDocument()
  firstResolve({ generated_at: 'one', sections: [], warnings: [] })
  await waitFor(() => expect(screen.queryByText(/as of one/i)).not.toBeInTheDocument())
})
