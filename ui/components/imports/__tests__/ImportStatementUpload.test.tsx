'use client'

/**
 * Vitest test for Phase 9 ImportStatementUpload 2-step inline confirm.
 *
 * This is THE thing preventing accidental data loss from the DELETE
 * endpoint -- if a future contributor copy-pastes the row component and
 * drops the confirm gate, the BE silently loses all transactions in the
 * selected batch. The test pins that gate exists and behaves correctly.
 *
 * Test strategy:
 *   - render the component with ONE mocked batch (id=99) via the
 *     mocked rulesService.listBatches().
 *   - click the row's Delete button -> inline Confirm/Cancel row
 *     appears; the gate is the safety.
 *   - click Cancel -> confirm row hides, rulesService.deleteBatch was
 *     NOT called.
 *   - click Delete again, then Confirm -> rulesService.deleteBatch
 *     was called exactly once with the right batch id, AND the blast-
 *     radius copy "Delete 5 transactions?" is in the confirm row.
 *
 * Mocking: Vitest HOISTS `vi.mock(...)` above all top-level imports
 * and variable declarations. Reading module-scope `let`/`const` from
 * within the factory hits a Temporal Dead Zone ("Cannot access X
 * before initialization"). ``vi.hoisted`` registers the factory to
 * ALSO be hoisted, so the mock fns exist before the mock factory runs.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'

// REGISTER the mock fns FIRST (above imports) so the `vi.mock` factory
// below can safely close over them.
const { listBatches, listAccounts, deleteBatch } = vi.hoisted(() => {
  const listBatches = vi.fn().mockResolvedValue([
    {
      id: 99,
      filename: 'sample.csv',
      file_type: 'csv',
      record_count: 5,
      account_id: 1,
      saved_transactions: 5,
      created_at: '2025-06-30T12:00:00Z',
      processed_at: '2025-06-30T12:00:00Z',
    },
  ])
  const listAccounts = vi.fn().mockResolvedValue([])
  const deleteBatch = vi.fn().mockResolvedValue(undefined)
  return { listBatches, listAccounts, deleteBatch }
})

vi.mock('@/lib/api', () => ({
  rulesService: {
    listBatches: () => listBatches(),
    listAccounts: () => listAccounts(),
    listBatchTransactions: vi.fn().mockResolvedValue([]),
    // Forward the id arg through to the spied mock so
    // ``expect(deleteBatch).toHaveBeenCalledWith(99)`` works. The
    // pre-Phase-11.5 factory swallowed the arg — every Delete-confirm
    // test recorded ``deleteBatch([])`` and ``toHaveBeenCalledWith(99)``
    // failed on the second assertion. Same forwarding shape for the
    // other API mocks for symmetry.
    deleteBatch: (id: number | string) => deleteBatch(id),
    uploadStatement: vi.fn(),
  },
}))

// Now import the component -- it sees the mocked rulesService.
import ImportStatementUpload from '../ImportStatementUpload'

describe('ImportStatementUpload 2-step confirm pattern', () => {
  beforeEach(() => {
    listBatches.mockClear()
    listAccounts.mockClear()
    deleteBatch.mockClear()
    listBatches.mockResolvedValue([
      {
        id: 99,
        filename: 'sample.csv',
        file_type: 'csv',
        record_count: 5,
        account_id: 1,
        saved_transactions: 5,
        created_at: '2025-06-30T12:00:00Z',
        processed_at: '2025-06-30T12:00:00Z',
      },
    ])
    deleteBatch.mockResolvedValue(undefined)
  })

  it('renders the import history with sample batch', async () => {
    render(<ImportStatementUpload accounts={[]} />)
    // Async listBatches -> wait for row to mount.
    await waitFor(() => {
      expect(screen.getByTestId('import-history-row-99')).toBeInTheDocument()
    })
    expect(screen.getByText('sample.csv')).toBeInTheDocument()
  })

  it('clicking Delete opens the inline confirm, Cancel does NOT call deleteBatch', async () => {
    render(<ImportStatementUpload accounts={[]} />)
    await waitFor(() => screen.getByTestId('import-history-row-99'))

    // Initial state: Delete button visible, no Confirm/Cancel.
    const deleteBtn = screen.getByTestId('import-history-delete-99')
    expect(deleteBtn).toBeInTheDocument()
    expect(screen.queryByTestId('import-history-confirm-99')).toBeNull()

    // 1. Click Delete -> inline confirm row appears.
    fireEvent.click(deleteBtn)
    await waitFor(() => {
      expect(screen.getByTestId('import-history-confirm-99')).toBeInTheDocument()
    })

    // 2. Click Cancel -> confirm row hides, deleteBatch NOT called.
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(screen.queryByTestId('import-history-confirm-99')).toBeNull()
    expect(deleteBatch).not.toHaveBeenCalled()
  })

  it('clicking Delete then Confirm DOES call deleteBatch with right id', async () => {
    render(<ImportStatementUpload accounts={[]} />)
    await waitFor(() => screen.getByTestId('import-history-row-99'))

    // 1. Click Delete -> confirm row.
    fireEvent.click(screen.getByTestId('import-history-delete-99'))
    await waitFor(() => screen.getByTestId('import-history-confirm-99'))

    // 2. Click Confirm -> deleteBatch called with 99.
    const confirmBtn = screen.getByTestId('import-history-confirm-delete-99')
    expect(confirmBtn).toBeInTheDocument()
    fireEvent.click(confirmBtn)

    await waitFor(() => {
      expect(deleteBatch).toHaveBeenCalledTimes(1)
      expect(deleteBatch).toHaveBeenCalledWith(99)
    })
  })

  it('confirm gate is the safety: clicking Delete + Cancel does not destroy data', async () => {
    // Regression guard for the original "no option to delete imported
    // files" bug. If a future contributor drops the Confirm UI and
    // wires onClick={() => onConfirmDelete(b.id)} directly, the Cancel
    // branch would silently bypass the safety.
    render(<ImportStatementUpload accounts={[]} />)
    await waitFor(() => screen.getByTestId('import-history-row-99'))

    fireEvent.click(screen.getByTestId('import-history-delete-99'))
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

    // Critically: even though we hit Delete, the API was NOT called
    // because Cancel aborted before Confirm.
    expect(deleteBatch).not.toHaveBeenCalled()
  })

  it('respects the 5-transaction blast-radius copy', async () => {
    render(<ImportStatementUpload accounts={[]} />)
    await waitFor(() => screen.getByTestId('import-history-row-99'))
    fireEvent.click(screen.getByTestId('import-history-delete-99'))
    await waitFor(() => screen.getByTestId('import-history-confirm-99'))
    // The confirm row includes "Delete 5 transactions?" copy so the
    // user sees the exact blast radius before they click.
    expect(screen.getByText(/delete 5 transactions/i)).toBeInTheDocument()
  })
})
