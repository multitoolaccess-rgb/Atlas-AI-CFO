'use client'

import { useEffect, useRef } from 'react'
import { ExternalLink, FileText, X } from 'lucide-react'
import type { Citation } from '@/lib/marketBriefs'

export type EvidenceState = 'observed' | 'derived' | 'estimated' | 'stale' | 'missing' | 'unknown' | 'insufficient_history' | 'unavailable'

export interface EvidenceRecord {
  id: string
  label: string
  category?: string
  value?: string | null
  period?: string | null
  asOf?: string | null
  asKnownAt?: string | null
  retrievedAt?: string | null
  state: EvidenceState
  source?: Citation | null
  methodology?: string | null
  calculationVersion?: string | null
  sourceReference?: string | null
}

export interface EvidenceDrawerProps {
  open: boolean
  title?: string
  evidence: EvidenceRecord[]
  onClose: () => void
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) return 'Unavailable'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

function stateLabel(state: EvidenceState) {
  return state.replaceAll('_', ' ')
}

export default function EvidenceDrawer({ open, title = 'Evidence and provenance', evidence, onClose }: EvidenceDrawerProps) {
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    closeRef.current?.focus()
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose, open])

  if (!open) return null

  return <div className="fixed inset-0 z-50 flex justify-end bg-black/30" role="presentation" onClick={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <aside role="dialog" aria-modal="true" aria-labelledby="evidence-drawer-title" className="h-full w-full max-w-xl overflow-y-auto bg-[var(--bg-primary)] shadow-[var(--shadow-5)]">
      <div className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4"><div className="flex items-center gap-2"><FileText className="h-5 w-5 text-[var(--accent-primary)]" aria-hidden="true" /><h2 id="evidence-drawer-title" className="font-semibold text-primary">{title}</h2></div><button ref={closeRef} type="button" onClick={onClose} aria-label="Close evidence" className="min-h-11 min-w-11 rounded-md text-secondary hover:bg-[var(--surface-ambient)] focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"><X className="mx-auto h-4 w-4" aria-hidden="true" /></button></div>
      <div className="p-4"><p className="text-sm leading-6 text-secondary">Evidence is shown as supplied by the server. Timestamps and data states are preserved; unavailable provenance is not inferred.</p>{evidence.length === 0 ? <div className="mt-4 rounded-md border border-dashed border-[var(--border-subtle)] p-4 text-sm text-secondary">No evidence is available for this claim.</div> : <div className="mt-4 space-y-4">{evidence.map((item) => <article key={item.id} className="rounded-lg border border-[var(--border-subtle)] p-4"><div className="flex items-start justify-between gap-3"><div><h3 className="font-medium text-primary">{item.label}</h3>{item.category && <p className="mt-1 text-xs text-secondary">Category: {item.category}</p>}</div><span className="rounded-full bg-[var(--surface-ambient)] px-2 py-1 text-xs font-medium text-secondary">{stateLabel(item.state)}</span></div>{item.value != null && <p className="mt-3 font-mono text-lg text-primary">{item.value}</p>}<dl className="mt-3 grid gap-3 text-xs sm:grid-cols-2"><div><dt className="text-tertiary">Period</dt><dd className="mt-1 text-secondary">{item.period ?? 'Unavailable'}</dd></div><div><dt className="text-tertiary">As of</dt><dd className="mt-1 text-secondary">{formatTimestamp(item.asOf)}</dd></div><div><dt className="text-tertiary">Known at</dt><dd className="mt-1 text-secondary">{formatTimestamp(item.asKnownAt)}</dd></div><div><dt className="text-tertiary">Retrieved</dt><dd className="mt-1 text-secondary">{formatTimestamp(item.retrievedAt ?? item.source?.retrieved_at)}</dd></div></dl>{item.source && <div className="mt-3 border-t border-[var(--border-subtle)] pt-3 text-xs"><p className="text-secondary">Source: <span className="font-medium text-primary">{item.source.provider}</span> · {item.source.freshness}</p><a href={item.source.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex min-h-11 items-center gap-2 font-medium text-[var(--accent-primary)] underline underline-offset-2">Open source <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" /></a></div>}<details className="mt-3"><summary className="cursor-pointer text-xs font-medium text-secondary focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]">Technical provenance</summary><dl className="mt-3 grid gap-3 rounded-md bg-[var(--surface-ambient)] p-3 text-xs sm:grid-cols-2"><div><dt className="text-tertiary">Evidence ID</dt><dd className="mt-1 break-all font-mono text-secondary">{item.id}</dd></div><div><dt className="text-tertiary">Source reference</dt><dd className="mt-1 break-all font-mono text-secondary">{item.sourceReference ?? 'Unavailable'}</dd></div><div><dt className="text-tertiary">Methodology</dt><dd className="mt-1 font-mono text-secondary">{item.methodology ?? 'Unavailable'}</dd></div><div><dt className="text-tertiary">Calculation version</dt><dd className="mt-1 font-mono text-secondary">{item.calculationVersion ?? 'Unavailable'}</dd></div></dl></details></article>)}</div>}</div>
    </aside>
  </div>
}
