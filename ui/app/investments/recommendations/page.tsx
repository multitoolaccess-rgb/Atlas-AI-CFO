'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, ArrowLeft, Check, Clock3, ShieldCheck, X } from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import EvidenceDrawer, { type EvidenceRecord } from '@/components/investments/EvidenceDrawer'
import { investmentPersistence, type InvestmentCommitteeResponse, type InvestmentDecision, type InvestmentDecisionType, type InvestmentEvidencePacket, type InvestmentOutcome, type InvestmentRecommendation } from '@/lib/investmentPersistence'

const decisions: Array<{ type: InvestmentDecisionType; label: string; icon: typeof Check }> = [
  { type: 'accept', label: 'Accept for review', icon: Check }, { type: 'reject', label: 'Reject', icon: X }, { type: 'defer', label: 'Defer', icon: Clock3 },
]

function listValue(value: unknown): string { return Array.isArray(value) ? value.join(', ') : value == null ? 'Unavailable' : String(value) }

export default function InvestmentRecommendationsPage() {
  const [items, setItems] = useState<InvestmentRecommendation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [evidence, setEvidence] = useState<InvestmentEvidencePacket | null>(null)
  const [committee, setCommittee] = useState<Record<string, InvestmentCommitteeResponse | null>>({})
  const [decisionHistory, setDecisionHistory] = useState<Record<string, InvestmentDecision[]>>({})
  const [outcomes, setOutcomes] = useState<Record<string, InvestmentOutcome[]>>({})

  const load = useCallback(async () => { setLoading(true); setError(null); try { setItems((await investmentPersistence.listRecommendations({ lifecycle: 'active' })).items) } catch { setError('Investment recommendations are unavailable. No recommendation is shown without a server response.') } finally { setLoading(false) } }, [])
  useEffect(() => { void load() }, [load])

  const loadContext = async (item: InvestmentRecommendation) => {
    const committeeId = typeof item.committee_finding_id === 'string' ? item.committee_finding_id : null
    const [committeeResult, decisionsResult, outcomesResult] = await Promise.allSettled([
      committeeId ? investmentPersistence.getCommitteeFinding(committeeId) : Promise.resolve(null),
      investmentPersistence.listDecisions(item.recommendation_id),
      investmentPersistence.listOutcomes(item.recommendation_id),
    ])
    setCommittee((previous) => ({ ...previous, [item.recommendation_id]: committeeResult.status === 'fulfilled' ? committeeResult.value : null }))
    setDecisionHistory((previous) => ({ ...previous, [item.recommendation_id]: decisionsResult.status === 'fulfilled' ? decisionsResult.value.items : [] }))
    setOutcomes((previous) => ({ ...previous, [item.recommendation_id]: outcomesResult.status === 'fulfilled' ? outcomesResult.value.items : [] }))
  }

  const decide = async (recommendation: InvestmentRecommendation, type: InvestmentDecisionType) => {
    setBusy(recommendation.recommendation_id); setNotice(null)
    try {
      const key = typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`
      const result = await investmentPersistence.recordDecision(recommendation.recommendation_id, { decision_type: type }, recommendation.recommendation_hash, key)
      await loadContext(recommendation)
      setNotice(result.replayed ? 'The existing decision was safely replayed.' : 'Decision recorded. Atlas did not execute anything.')
    } catch { setNotice('The decision could not be recorded. The recommendation may be stale; reload and review it again.') }
    finally { setBusy(null) }
  }

  return <PageLayout>
    <PageHeader eyebrow="Investment intelligence" title="Recommendation review" description="Review server-owned recommendations, committee context, evidence, risks, decisions, and outcomes before recording a human decision." actions={<Link href="/investments" className="inline-flex min-h-11 items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 text-sm text-secondary"><ArrowLeft className="h-4 w-4" aria-hidden="true" />Command Center</Link>} className="mb-6" />
    <section className="mb-5 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-working)] p-4 text-sm text-secondary"><div className="flex items-start gap-3"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-[var(--accent-primary)]" aria-hidden="true" /><p>These controls append a human decision only. They do not place orders, move money, mutate holdings, or rebalance a portfolio.</p></div></section>
    {notice && <p className="mb-4 rounded-lg border border-[var(--success-200)] bg-[var(--success-50)] p-4 text-sm text-[var(--success-800)]" role="status">{notice}</p>}
    {loading ? <p className="card p-6 text-sm text-secondary" role="status">Loading server-owned recommendations…</p> : error ? <section className="card p-6" role="alert"><AlertTriangle className="h-5 w-5 text-[var(--warning-600)]" aria-hidden="true" /><p className="mt-2 text-sm text-secondary">{error}</p><button type="button" onClick={() => void load()} className="btn-secondary mt-4 min-h-11 px-3">Retry</button></section> : items.length === 0 ? <section className="card p-6"><h2 className="font-semibold text-primary">No active recommendations</h2><p className="mt-2 text-sm text-secondary">Atlas has no active recommendation available for human review.</p></section> : <div className="space-y-4">{items.map((item) => { const id = item.recommendation_id; const history = decisionHistory[id] ?? []; const outcomeItems = outcomes[id] ?? []; const committeeItem = committee[id]; return <article key={id} className="card p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-mono text-xs text-tertiary">{item.security_id} · as of {String(item.recommendation_as_of ?? 'Unavailable')}</p><h2 className="mt-1 text-xl font-semibold text-primary">{item.recommendation_type}</h2></div><span className="rounded-full bg-[var(--success-50)] px-3 py-1 text-xs font-medium text-[var(--success-700)]">{item.status}</span></div><p className="mt-4 text-sm leading-6 text-secondary">{String(item.thesis ?? item.rationale ?? 'Thesis unavailable')}</p><dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-tertiary">Conviction</dt><dd className="mt-1 text-primary">{String(item.conviction ?? 'Unavailable')}</dd></div><div><dt className="text-tertiary">Review at</dt><dd className="mt-1 text-primary">{String(item.review_after ?? 'Unavailable')}</dd></div><div><dt className="text-tertiary">Risks</dt><dd className="mt-1 text-secondary">{listValue(item.risks)}</dd></div><div><dt className="text-tertiary">Invalidation</dt><dd className="mt-1 text-secondary">{listValue(item.invalidation_conditions)}</dd></div></dl><section className="mt-5 grid gap-3 border-t border-[var(--border-subtle)] pt-4 md:grid-cols-3"><div className="rounded-lg bg-[var(--surface-working)] p-3"><h3 className="text-sm font-semibold text-primary">Committee context</h3>{committeeItem ? <><p className="mt-2 text-sm text-secondary">{String(committeeItem.finding.thesis ?? 'Thesis unavailable')}</p><p className="mt-2 text-xs text-tertiary">Uncertainty: {String(committeeItem.finding.uncertainty ?? 'Unavailable')}</p><p className="mt-1 text-xs text-tertiary">Dissent: {listValue(committeeItem.finding.dissent)}</p></> : <p className="mt-2 text-sm text-secondary">Load context to view the linked committee finding.</p>}</div><div className="rounded-lg bg-[var(--surface-working)] p-3"><h3 className="text-sm font-semibold text-primary">Decision history</h3>{history.length ? <ul className="mt-2 space-y-2 text-xs text-secondary">{history.map((decision) => <li key={decision.decision_id}><span className="font-medium text-primary">{decision.decision_type}</span> · {new Date(decision.decision_timestamp).toLocaleString()}<br />{decision.rationale ?? 'No rationale recorded'}</li>)}</ul> : <p className="mt-2 text-sm text-secondary">No human decisions recorded.</p>}</div><div className="rounded-lg bg-[var(--surface-working)] p-3"><h3 className="text-sm font-semibold text-primary">Outcome history</h3>{outcomeItems.length ? <ul className="mt-2 space-y-2 text-xs text-secondary">{outcomeItems.map((outcome) => <li key={outcome.outcome_id}><span className="font-medium text-primary">{String(outcome.outcome_state ?? outcome.status ?? 'Evaluated')}</span> · {new Date(outcome.evaluation_as_of).toLocaleString()}<br />Hash: <span className="font-mono">{outcome.outcome_hash.slice(0, 12)}…</span></li>)}</ul> : <p className="mt-2 text-sm text-secondary">No outcomes available.</p>}</div></section><div className="mt-5 flex flex-wrap gap-2"><button type="button" onClick={async () => { try { setEvidence(await investmentPersistence.getEvidence(id)) } catch { setNotice('Evidence is unavailable for this recommendation.') } }} className="btn-secondary min-h-11 px-3 text-sm">Review evidence</button><button type="button" onClick={() => void loadContext(item)} className="btn-secondary min-h-11 px-3 text-sm">Load committee and history</button>{decisions.map(({ type, label, icon: Icon }) => <button key={type} type="button" disabled={busy === id} onClick={() => void decide(item, type)} className={type === 'accept' ? 'btn-primary inline-flex min-h-11 items-center gap-2 px-3 text-sm' : 'btn-secondary inline-flex min-h-11 items-center gap-2 px-3 text-sm'}><Icon className="h-4 w-4" aria-hidden="true" />{label}</button>)}</div></article> })}</div>}
    {evidence && <EvidenceDrawer open title="Recommendation evidence" evidence={evidence.items.map((item): EvidenceRecord => ({ id: item.evidence_id, label: item.category, category: item.category, value: item.numeric_value, state: 'observed', sourceReference: typeof item.reference.source_reference === 'string' ? item.reference.source_reference : null, methodology: typeof item.reference.methodology === 'string' ? item.reference.methodology : null, calculationVersion: typeof item.reference.calculation_version === 'string' ? item.reference.calculation_version : null }))} onClose={() => setEvidence(null)} />}
  </PageLayout>
}
