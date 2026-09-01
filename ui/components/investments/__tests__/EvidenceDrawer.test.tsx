import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import EvidenceDrawer, { type EvidenceRecord } from '@/components/investments/EvidenceDrawer'

const evidence: EvidenceRecord[] = [{
  id: 'fact:revenue:2025',
  label: 'Revenue',
  category: 'fundamental',
  value: '$100M',
  period: 'FY2025',
  asOf: '2026-02-01T00:00:00Z',
  asKnownAt: '2026-02-02T00:00:00Z',
  retrievedAt: '2026-02-03T00:00:00Z',
  state: 'observed',
  source: { provider: 'SEC', source_url: 'https://example.com/source', freshness: 'fresh', retrieved_at: '2026-02-03T00:00:00Z' },
  methodology: 'fundamental-research/v1',
  calculationVersion: 'facts/v1',
  sourceReference: 'accession-123',
}]

describe('EvidenceDrawer UI-07', () => {
  it('renders evidence, timestamps, source, and technical provenance', () => {
    render(<EvidenceDrawer open evidence={evidence} onClose={vi.fn()} />)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Revenue')).toBeInTheDocument()
    expect(screen.getByText('$100M')).toBeInTheDocument()
    expect(screen.getByText('FY2025')).toBeInTheDocument()
    expect(screen.getByText('SEC')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Technical provenance'))
    expect(screen.getByText('fact:revenue:2025')).toBeInTheDocument()
    expect(screen.getByText('fundamental-research/v1')).toBeInTheDocument()
  })

  it('preserves explicit stale and unavailable states', () => {
    render(<EvidenceDrawer open evidence={[{ id: 'unknown:1', label: 'Technical signal', state: 'unavailable' }]} onClose={vi.fn()} />)
    expect(screen.getByText('unavailable')).toBeInTheDocument()
    expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0)
  })

  it('supports Escape dismissal and honest empty state', () => {
    const onClose = vi.fn()
    const { rerender } = render(<EvidenceDrawer open evidence={[]} onClose={onClose} />)
    expect(screen.getByText('No evidence is available for this claim.')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
    rerender(<EvidenceDrawer open={false} evidence={[]} onClose={onClose} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('does not contain execution controls', () => {
    render(<EvidenceDrawer open evidence={evidence} onClose={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /buy|sell|execute|trade|order|rebalance/i })).not.toBeInTheDocument()
  })
})
