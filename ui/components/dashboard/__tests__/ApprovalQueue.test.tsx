/**
 * ApprovalQueue — unit tests for Phase 4 recommendation approval workflow.
 *
 * Covers: rendering, approve/deny/dismiss actions, pending/all filter toggle,
 * loading state, empty state, error handling, expand/collapse, and priority badges.
 */
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import ApprovalQueue from '@/components/dashboard/ApprovalQueue'
import { rulesService, type RecommendationLogItem } from '@/lib/api'

// Mock the API service
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual('@/lib/api')
  return {
    ...actual,
    rulesService: {
      listRecommendations: vi.fn(),
      takeRecommendationAction: vi.fn(),
      getRecommendationStats: vi.fn(),
    },
  }
})

const mockPendingItem: RecommendationLogItem = {
  id: 1,
  user_id: 1,
  title: 'Boost Your Savings Rate',
  description: 'Your savings rate is below 10%. Consider reducing discretionary spending.',
  priority: 'high',
  status: 'pending',
  category: 'savings',
  impact: 'Could save $200/month',
  metadata_json: null,
  created_at: new Date(Date.now() - 3600000).toISOString(),
  resolved_at: null,
  resolved_by: null,
}

const mockPendingItem2: RecommendationLogItem = {
  id: 2,
  user_id: 1,
  title: 'Spending Nearing Income',
  description: 'Your expenses are over 90% of income.',
  priority: 'medium',
  status: 'pending',
  category: 'spending',
  impact: 'Risk of negative savings',
  metadata_json: null,
  created_at: new Date(Date.now() - 7200000).toISOString(),
  resolved_at: null,
  resolved_by: null,
}

const mockResolvedItem: RecommendationLogItem = {
  id: 3,
  user_id: 1,
  title: 'Emergency Fund Goal',
  description: 'You are 80% towards your emergency fund goal.',
  priority: 'low',
  status: 'approved',
  category: 'goal',
  impact: null,
  metadata_json: null,
  created_at: new Date(Date.now() - 86400000).toISOString(),
  resolved_at: new Date(Date.now() - 3600000).toISOString(),
  resolved_by: 'user',
}

describe('ApprovalQueue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(rulesService.listRecommendations as Mock).mockResolvedValue({
      items: [mockPendingItem, mockPendingItem2],
      total: 3,
      pending_count: 2,
    })
    ;(rulesService.getRecommendationStats as Mock).mockResolvedValue({
      total: 3,
      pending: 2,
      approved: 1,
      denied: 0,
      dismissed: 0,
    })
    ;(rulesService.takeRecommendationAction as Mock).mockResolvedValue(mockResolvedItem)
  })

  it('renders the approval queue header with pending count', async () => {
    render(<ApprovalQueue />)
    await waitFor(() => {
      expect(screen.getByText('Approval Queue')).toBeInTheDocument()
    })
    expect(screen.getByText(/2 pending recommendation/)).toBeInTheDocument()
  })

  it('renders pending items on mount', async () => {
    render(<ApprovalQueue />)
    await waitFor(() => {
      expect(screen.getByText('Boost Your Savings Rate')).toBeInTheDocument()
      expect(screen.getByText('Spending Nearing Income')).toBeInTheDocument()
    })
  })

  it('shows priority badges on items', async () => {
    render(<ApprovalQueue />)
    await waitFor(() => {
      expect(screen.getByTestId('approval-queue-priority-1')).toHaveTextContent('high')
      expect(screen.getByTestId('approval-queue-priority-2')).toHaveTextContent('medium')
    })
  })

  it('shows impact text when available', async () => {
    render(<ApprovalQueue />)
    await waitFor(() => {
      expect(screen.getByText(/Could save \$200\/month/)).toBeInTheDocument()
    })
  })

  it('calls takeRecommendationAction with "approve" when Approve is clicked', async () => {
    render(<ApprovalQueue />)
    await waitFor(() => {
      expect(screen.getByTestId('approval-queue-approve-1')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('approval-queue-approve-1'))
    await waitFor(() => {
      expect(rulesService.takeRecommendationAction).toHaveBeenCalledWith(1, 'approve')
    })
  })

  it('calls takeRecommendationAction with "deny" when Deny is clicked', async () => {
    render(<ApprovalQueue />)
    await waitFor(() => {
      expect(screen.getByTestId('approval-queue-deny-1')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('approval-queue-deny-1'))
    await waitFor(() => {
      expect(rulesService.takeRecommendationAction).toHaveBeenCalledWith(1, 'deny')
    })
  })

  it('calls takeRecommendationAction with "dismiss" when Dismiss is clicked', async () => {
    render(<ApprovalQueue />)
    await waitFor(() => {
      expect(screen.getByTestId('approval-queue-dismiss-1')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('approval-queue-dismiss-1'))
    await waitFor(() => {
      expect(rulesService.takeRecommendationAction).toHaveBeenCalledWith(1, 'dismiss')
    })
  })

  it('removes item from list after action in pending filter mode', async () => {
    render(<ApprovalQueue />)
    await waitFor(() => {
      expect(screen.getByText('Boost Your Savings Rate')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('approval-queue-approve-1'))
    await waitFor(() => {
      expect(screen.queryByText('Boost Your Savings Rate')).not.toBeInTheDocument()
      expect(screen.getByText('Spending Nearing Income')).toBeInTheDocument()
    })
  })

  it('shows empty state when no pending items', async () => {
    ;(rulesService.listRecommendations as Mock).mockResolvedValue({
      items: [],
      total: 0,
      pending_count: 0,
    })
    ;(rulesService.getRecommendationStats as Mock).mockResolvedValue({
      total: 0,
      pending: 0,
      approved: 0,
      denied: 0,
      dismissed: 0,
    })
    render(<ApprovalQueue />)
    await waitFor(() => {
      expect(screen.getByTestId('approval-queue-empty')).toBeInTheDocument()
      expect(screen.getByText(/All caught up/)).toBeInTheDocument()
    })
  })

  it('shows loading state initially', () => {
    ;(rulesService.listRecommendations as Mock).mockReturnValue(new Promise(() => {}))
    render(<ApprovalQueue />)
    expect(screen.getByText(/Loading recommendations/)).toBeInTheDocument()
  })

  it('shows error when API call fails', async () => {
    ;(rulesService.listRecommendations as Mock).mockRejectedValue({
      response: { data: { detail: 'Server unavailable' } },
    })
    render(<ApprovalQueue />)
    await waitFor(() => {
      expect(screen.getByTestId('approval-queue-error')).toHaveTextContent('Server unavailable')
    })
  })

  it('toggles between pending and all filter', async () => {
    ;(rulesService.listRecommendations as Mock)
      .mockResolvedValueOnce({
        items: [mockPendingItem, mockPendingItem2],
        total: 3,
        pending_count: 2,
      })
      .mockResolvedValueOnce({
        items: [mockPendingItem, mockPendingItem2, mockResolvedItem],
        total: 3,
        pending_count: 2,
      })

    render(<ApprovalQueue />)
    await waitFor(() => {
      expect(screen.getByTestId('approval-queue-filter-toggle')).toHaveTextContent('Show all')
    })
    fireEvent.click(screen.getByTestId('approval-queue-filter-toggle'))
    await waitFor(() => {
      expect(screen.getByTestId('approval-queue-filter-toggle')).toHaveTextContent('Pending only')
    })
  })

  it('collapses and expands content', async () => {
    render(<ApprovalQueue />)
    await waitFor(() => {
      expect(screen.getByText('Boost Your Savings Rate')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByTestId('approval-queue-toggle'))
    expect(screen.queryByText('Boost Your Savings Rate')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('approval-queue-toggle'))
    await waitFor(() => {
      expect(screen.getByText('Boost Your Savings Rate')).toBeInTheDocument()
    })
  })

  it('uses pre-fetched items when provided as props', () => {
    render(
      <ApprovalQueue
        items={[mockPendingItem]}
        pendingCount={1}
        loading={false}
      />,
    )
    expect(screen.getByText('Boost Your Savings Rate')).toBeInTheDocument()
    expect(rulesService.listRecommendations).not.toHaveBeenCalled()
  })

  it('renders the correct number of items', async () => {
    render(<ApprovalQueue />)
    await waitFor(() => {
      expect(screen.getByTestId('approval-queue-item-1')).toBeInTheDocument()
      expect(screen.getByTestId('approval-queue-item-2')).toBeInTheDocument()
    })
  })
})
