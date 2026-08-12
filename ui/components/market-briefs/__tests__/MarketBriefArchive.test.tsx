import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import MarketBriefArchive from '../MarketBriefArchive'
import { generateMarketBrief, getMarketBrief, listMarketBriefs } from '@/lib/marketBriefs'

vi.mock('@/lib/marketBriefs', () => ({ listMarketBriefs: vi.fn().mockResolvedValue([]), getMarketBrief: vi.fn(), generateMarketBrief: vi.fn() }))

afterEach(() => { vi.clearAllMocks() })

test('renders an accessible empty archive and generate action', async () => {
  render(<MarketBriefArchive />)
  expect(screen.getByRole('heading', { name: /market intelligence briefs/i })).toBeInTheDocument()
  expect(await screen.findByText(/no market briefs exist yet/i)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /generate brief/i })).toBeInTheDocument()
})

test('generates, selects, and archives a server-composed brief without client financial data', async () => {
  vi.mocked(generateMarketBrief).mockResolvedValue({
    brief_id: 'generated', replayed: false,
    brief: { generated_at: 'now', sections: [{ name: 'earnings', content: ['upcoming: AAPL earnings'], citations: [{ provider: 'synthetic', source_url: 'https://source.test', freshness: 'fresh' }] }], warnings: ['Missing filings'], actions: [{ action: 'Review AAPL', why: 'Review only', goal_linkage: 'None', evidence: ['AAPL'], expected_impact: 'No execution', risks: ['Incomplete'], alternatives: ['Do nothing'], confidence: 'low', approval_requirement: 'explicit_user_approval_required' }] },
  })
  render(<MarketBriefArchive />)
  fireEvent.click(await screen.findByRole('button', { name: /^generate brief$/i }))
  expect(await screen.findByText(/generated and added/i)).toBeInTheDocument()
  expect(screen.getByText(/upcoming: AAPL earnings/i)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /source: synthetic/i })).toHaveAttribute('href', 'https://source.test')
  expect(screen.getByText(/review AAPL/i)).toBeInTheDocument()
  expect(generateMarketBrief).toHaveBeenCalledOnce()
})

test('explains a fail-closed provider configuration response', async () => {
  vi.mocked(generateMarketBrief).mockRejectedValue({ response: { status: 503 } })
  render(<MarketBriefArchive />)
  fireEvent.click(await screen.findByRole('button', { name: /^generate brief$/i }))
  expect(await screen.findByText(/local operator to enable the required server-side configuration/i)).toBeInTheDocument()
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
