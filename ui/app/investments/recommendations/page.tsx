'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, ArrowLeft, Check, Clock3, ShieldCheck, X } from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import EvidenceDrawer, { type EvidenceRecord } from '@/components/investments/EvidenceDrawer'
import { investmentPersistence, type InvestmentDecisionType, type InvestmentEvidencePacket, type InvestmentRecommendation } from '@/lib/investmentPersistence'

const decisions: Array<{ type: InvestmentDecisionType; label: string; icon: typeof Check }> = [
  { type: 'accept', label: 'Accept for review', icon: Check },
  { type: 'reject', label: 'Reject', icon: X },
  { type: 'defer', label: 'Defer', icon: Clock3 },
]

export default function InvestmentRecommendationsPage() {
  const [items, setItems] = useState<InvestmentRecommendation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [evidence, setEvidence] = useState<InvestmentEvidencePacket | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setItems((await investmentPersistence.listRecommendations({ lifecycle: 'active' })).items) }
    catch { setError('Investment recommendations are unavailable. No recommendation is shown without a server response.') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { void load() }, [load])

  const decide = async (recommendation: InvestmentRecommendation, type: InvestmentDecisionType) => {
    setBusy(recommendation.recommendation_id); setNotice(null)
    try {
      const key = typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`
      const result = await investmentPersistence.recordDecision(recommendation.recommendation_id, { decision_type: type }, recommendation.recommendation_hash, key)
      setNotice(result.replayed ? 'The existing decision was safely replayed.' : 'Decision recorded. Atlas did not execute anything.')
    } catch { setNotice('The decision could not be recorded. The recommendation may be stale; reload and review it again.') }
    finally { setBusy(null) }
  }

  return <PageLayout>
    <PageHeader eyebrow="Investment intelligence" title="Recommendation review" description="Review server-owned investment recommendations, evidence, risks, and lifecycle before recording a human decision." actions={<Link href="/investments" className="inline-flex min-h-11 items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 text-sm text-secondary"><ArrowLeft className="h-4 w-4" aria-hidden="true" />Command Center</Link>} className="mb-6" />
    <section className="mb-5 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-working)] p-4 text-sm text-secondary"><div className="flex items-start gap-3"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-[var(--accent-primary)]" aria-hidden="true" /><p>These controls append a human decision only. They do not place orders, move money, mutate holdings, or rebalance a portfolio.</p></div></section>
    {notice && <p className="mb-4 rounded-lg border border-[var(--success-200)] bg-[var(--success-50)] p-4 text-sm text-[var(--success-800)]" role="status">{notice}</p>}
    {loading ? <p className="card p-6 text-sm text-secondary" role="status">Loading server-owned recommendations…</p> : error ? <section className="card p-6" role="alert"><AlertTriangle className="h-5 w-5 text-[var(--warning-600)]" aria-hidden="true" /><p className="mt-2 text-sm text-secondary">{error}</p><button type="button" onClick={() => void load()} className="btn-secondary mt-4 min-h-11 px-3">Retry</button></section> : items.length === 0 ? <section className="card p-6"><h2 className="font-semibold text-primary">No active recommendations</h2><p className="mt-2 text-sm text-secondary">Atlas has no active recommendation available for human review.</p></section> : <div className="space-y-4">{items.map((item) => <article key={item.recommendation_id} className="card p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-mono text-xs text-tertiary">{item.security_id} · as of {String(item.recommendation_as_of ?? 'Unavailable')}</p><h2 className="mt-1 text-xl font-semibold text-primary">{item.recommendation_type}</h2></div><span className="rounded-full bg-[var(--success-50)] px-3 py-1 text-xs font-medium text-[var(--success-700)]">{item.status}</span></div><p className="mt-4 text-sm leading-6 text-secondary">{String(item.thesis ?? item.rationale ?? 'Thesis unavailable')}</p><dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-tertiary">Conviction</dt><dd className="mt-1 text-primary">{String(item.conviction ?? 'Unavailable')}</dd></div><div><dt className="text-tertiary">Review at</dt><dd className="mt-1 text-primary">{String(item.review_after ?? 'Unavailable')}</dd></div><div><dt className="text-tertiary">Risks</dt><dd className="mt-1 text-secondary">{Array.isArray(item.risks) ? item.risks.join(', ') : 'Unavailable'}</dd></div><div><dt className="text-tertiary">Invalidation</dt><dd className="mt-1 text-secondary">{Array.isArray(item.invalidation_conditions) ? item.invalidation_conditions.join(', ') : 'Unavailable'}</dd></div></dl><div className="mt-5 flex flex-wrap gap-2 border-t border-[var(--border-subtle)] pt-4"><button type="button" onClick={async () => { try { setEvidence(await investmentPersistence.getEvidence(item.recommendation_id)) } catch { setNotice('Evidence is unavailable for this recommendation.') } }} className="btn-secondary min-h-11 px-3 text-sm">Review evidence</button>{decisions.map(({ type, label, icon: Icon }) => <button key={type} type="button" disabled={busy === item.recommendation_id} onClick={() => void decide(item, type)} className={type === 'accept' ? 'btn-primary inline-flex min-h-11 items-center gap-2 px-3 text-sm' : 'btn-secondary inline-flex min-h-11 items-center gap-2 px-3 text-sm'}><Icon className="h-4 w-4" aria-hidden="true" />{label}</button>)}</div></article>)}</div>}
    {evidence && <EvidenceDrawer open title="Recommendation evidence" evidence={evidence.items.map((item): EvidenceRecord => ({ id: item.evidence_id, label: item.category, category: item.category, value: item.numeric_value, state: 'observed', sourceReference: typeof item.reference.source_reference === 'string' ? item.reference.source_reference : null, methodology: typeof item.reference.methodology === 'string' ? item.reference.methodology : null, calculationVersion: typeof item.reference.calculation_version === 'string' ? item.reference.calculation_version : null }))} onClose={() => setEvidence(null)} />}
  </PageLayout>
}
