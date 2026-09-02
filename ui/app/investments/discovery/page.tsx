'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, ArrowLeft, Check, GitCompareArrows, Search, ShieldCheck, X } from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import { investmentDiscovery, type DiscoveryCandidate, type DiscoveryComparisonResponse, type DiscoveryUniverse } from '@/lib/investmentDiscovery'

const modes: Array<{ value: DiscoveryUniverse; label: string; description: string }> = [
  { value: 'portfolio', label: 'My portfolio', description: 'Owner-scoped securities from current holdings.' },
  { value: 'sp500', label: 'S&P 500', description: 'Bounded current universe from the server-owned symbol list.' },
]

export default function InvestmentDiscoveryPage() {
  const [universe, setUniverse] = useState<DiscoveryUniverse>('portfolio')
  const [query, setQuery] = useState('')
  const [items, setItems] = useState<DiscoveryCandidate[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [comparison, setComparison] = useState<DiscoveryComparisonResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null); setComparison(null)
    try { setItems((await investmentDiscovery.list(universe, query || undefined, 50)).candidates) }
    catch { setError('Discovery is unavailable. No opportunity is shown without a server response.') }
    finally { setLoading(false) }
  }, [universe, query])

  useEffect(() => { void load() }, [load])

  const toggle = (id: string) => setSelected((current) => current.includes(id) ? current.filter((value) => value !== id) : current.length < 10 ? [...current, id] : current)
  const compare = async () => {
    if (selected.length < 2) return
    try { setComparison(await investmentDiscovery.compare(universe, selected, [])) }
    catch { setError('These candidates could not be compared safely.') }
  }

  return <PageLayout>
    <PageHeader eyebrow="Investment intelligence · UI-09" title="Opportunity discovery" description="Explore explicitly bounded universes. Discovery is descriptive and does not create recommendations or execution actions." actions={<Link href="/investments" className="inline-flex min-h-11 items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 text-sm text-secondary"><ArrowLeft className="h-4 w-4" aria-hidden="true" />Command Center</Link>} className="mb-6" />
    <section className="mb-5 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-working)] p-4 text-sm text-secondary"><div className="flex items-start gap-3"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-[var(--accent-primary)]" aria-hidden="true" /><p>Current-only server projection · stable identity ordering · no discovery score. A candidate is not an investment recommendation.</p></div></section>
    <section className="card mb-5 p-4" aria-label="Discovery controls"><div className="grid gap-4 md:grid-cols-[1fr_1fr]"><div><span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-tertiary">Universe</span><div className="flex flex-wrap gap-2">{modes.map((mode) => <button key={mode.value} type="button" onClick={() => { setUniverse(mode.value); setSelected([]) }} className={`min-h-11 rounded-md border px-3 text-sm ${universe === mode.value ? 'border-[var(--accent-primary)] bg-[var(--accent-selection)] text-primary' : 'border-[var(--border-subtle)] text-secondary'}`} aria-pressed={universe === mode.value}>{mode.label}</button>)}</div><p className="mt-2 text-xs text-tertiary">{modes.find((mode) => mode.value === universe)?.description}</p></div><label className="flex min-h-11 items-center gap-2 self-end rounded-md border border-[var(--border-subtle)] px-3"><Search className="h-4 w-4 text-tertiary" aria-hidden="true" /><span className="sr-only">Search discovery candidates</span><input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void load() }} placeholder="Search symbol or reason" className="min-w-0 flex-1 bg-transparent text-sm text-primary outline-none" /></label></div></section>
    {error && <section className="mb-5 card p-5" role="alert"><AlertTriangle className="h-5 w-5 text-[var(--warning-600)]" aria-hidden="true" /><p className="mt-2 text-sm text-secondary">{error}</p><button type="button" onClick={() => void load()} className="btn-secondary mt-4 min-h-11 px-3">Retry</button></section>}
    {loading ? <p className="card p-6 text-sm text-secondary" role="status">Loading server-owned opportunities…</p> : items.length === 0 ? <section className="card p-6"><h2 className="font-semibold text-primary">No candidates in this universe</h2><p className="mt-2 text-sm text-secondary">The selected universe has no currently available candidate projection.</p></section> : <><div className="mb-3 flex items-center justify-between gap-3"><p className="text-sm text-secondary">{items.length} candidate{items.length === 1 ? '' : 's'} · select 2–10 to compare</p><button type="button" disabled={selected.length < 2} onClick={() => void compare()} className="btn-primary inline-flex min-h-11 items-center gap-2 px-3 text-sm disabled:opacity-50"><GitCompareArrows className="h-4 w-4" aria-hidden="true" />Compare selected</button></div><div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">{items.map((item) => <article key={item.candidate_id} className="card p-4"><div className="flex items-start justify-between gap-3"><div><h2 className="font-mono text-lg font-semibold text-primary">{item.security.symbol ?? 'Unnamed security'}</h2><p className="mt-1 text-xs text-tertiary">{item.security.security_id}</p></div><button type="button" onClick={() => toggle(item.candidate_id)} aria-label={`${selected.includes(item.candidate_id) ? 'Remove' : 'Add'} ${item.security.symbol ?? item.candidate_id} from comparison`} className="flex h-9 w-9 items-center justify-center rounded-md border border-[var(--border-subtle)]">{selected.includes(item.candidate_id) ? <Check className="h-4 w-4 text-[var(--success-600)]" aria-hidden="true" /> : <span className="text-tertiary">+</span>}</button></div><p className="mt-4 text-sm text-secondary">{item.reason}</p><dl className="mt-4 space-y-2 text-xs"><div className="flex justify-between gap-3"><dt className="text-tertiary">Status</dt><dd className="text-primary">{item.status}</dd></div><div className="flex justify-between gap-3"><dt className="text-tertiary">As of</dt><dd className="text-primary">{new Date(item.as_of).toLocaleString()}</dd></div><div className="flex justify-between gap-3"><dt className="text-tertiary">Data state</dt><dd className="text-primary">{item.freshness}</dd></div></dl></article>)}</div></>}
    {comparison && <section className="card mt-6 p-5" aria-label="Candidate comparison"><div className="flex items-center justify-between"><h2 className="text-lg font-semibold text-primary">Descriptive comparison</h2><button type="button" onClick={() => setComparison(null)} aria-label="Close comparison"><X className="h-4 w-4" aria-hidden="true" /></button></div><p className="mt-2 text-sm text-secondary">{comparison.comparable ? 'Selected candidates share a comparable projection.' : 'Comparison is limited; incompatible or unavailable data is shown explicitly.'}</p>{comparison.limitations.length > 0 && <ul className="mt-3 list-disc pl-5 text-sm text-secondary">{comparison.limitations.map((item) => <li key={item}>{item}</li>)}</ul>}</section>}
  </PageLayout>
}
