'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, ArrowLeft, BookOpen, ChevronDown, Clock3, Database, ExternalLink, Filter, RefreshCw, ShieldCheck, TrendingDown, TrendingUp } from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import { classifyMarketBriefError, generateMarketBrief, type ActionToReview, type BriefSection, type MarketBrief } from '@/lib/marketBriefs'

function formatDate(value?: string | null) {
  if (!value) return 'Unavailable'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Unavailable' : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function QualityBadge({ label }: { label: string }) {
  const tone = label.toLowerCase().includes('fresh') || label.toLowerCase().includes('ready') ? 'bg-[var(--success-50)] text-[var(--success-700)]' : label.toLowerCase().includes('stale') || label.toLowerCase().includes('partial') ? 'bg-[var(--warning-50)] text-[var(--warning-700)]' : 'bg-[var(--surface-ambient)] text-secondary'
  return <span className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${tone}`}>{label}</span>
}

function Section({ section, onEvidence }: { section: BriefSection; onEvidence: (section: BriefSection) => void }) {
  return <article className="border-b border-[var(--border-subtle)] py-4 last:border-b-0" data-testid={`brief-section-${section.name.toLowerCase().replaceAll(' ', '-')}`}>
    <div className="flex items-start justify-between gap-3"><h3 className="font-semibold text-primary">{section.name}</h3>{section.citations.length > 0 && <button type="button" onClick={() => onEvidence(section)} className="inline-flex min-h-11 shrink-0 items-center gap-1 rounded-md px-2 text-sm font-medium text-[var(--accent-primary)] hover:bg-[var(--accent-selection)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]">Evidence <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" /></button>}</div>
    <ul className="mt-2 space-y-2 text-sm leading-6 text-secondary">{section.content.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
    {section.citations.length > 0 && <p className="mt-3 text-xs text-tertiary">{section.citations.length} source reference{section.citations.length === 1 ? '' : 's'} available</p>}
  </article>
}

function ActionRow({ action, index, onSelect }: { action: ActionToReview; index: number; onSelect: (action: ActionToReview) => void }) {
  return <button type="button" onClick={() => onSelect(action)} className="grid w-full grid-cols-[minmax(5rem,0.8fr)_minmax(0,2fr)_auto] items-center gap-3 border-b border-[var(--border-subtle)] px-3 py-3 text-left transition-colors hover:bg-[var(--surface-ambient)] focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--accent-primary)]" data-testid={`brief-action-${index}`}><span className="font-mono text-sm font-semibold text-primary">{action.action}</span><span className="min-w-0 text-sm text-secondary">{action.why}</span><span className="text-xs text-tertiary">Review</span></button>
}

function Skeleton() {
  return <div className="space-y-4" aria-busy="true" data-testid="brief-loading"><div className="h-28 animate-pulse rounded-lg bg-[var(--surface-ambient)]" /><div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]"><div className="h-72 animate-pulse rounded-lg bg-[var(--surface-ambient)]" /><div className="h-72 animate-pulse rounded-lg bg-[var(--surface-ambient)]" /></div></div>
}

export default function DailyInvestmentBriefPage() {
  const [brief, setBrief] = useState<MarketBrief | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [errorRecovery, setErrorRecovery] = useState<string | null>(null)
  const [selectedSection, setSelectedSection] = useState<BriefSection | null>(null)
  const [selectedAction, setSelectedAction] = useState<ActionToReview | null>(null)
  const [actionFilter, setActionFilter] = useState('all')

  const loadBrief = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await generateMarketBrief()
      setBrief(result.brief)
    } catch (cause) {
      const state = classifyMarketBriefError(cause)
      setError(state.message)
      setErrorRecovery(state.recovery)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadBrief() }, [])

  const actions = useMemo(() => {
    const source = brief?.actions ?? []
    return actionFilter === 'all' ? source : source.filter((item) => item.action.toLowerCase() === actionFilter)
  }, [brief?.actions, actionFilter])

  if (loading) return <PageLayout><PageHeader eyebrow="Investment intelligence" title="Daily Investment Brief" description="Preparing a server-owned, evidence-backed brief." className="mb-6" /><Skeleton /></PageLayout>

  if (error || !brief) return <PageLayout><PageHeader eyebrow="Investment intelligence" title="Daily Investment Brief" description="No report is shown unless Atlas can return a server-owned brief." className="mb-6" /><section className="card p-6" role="alert" data-testid="brief-error"><div className="flex items-start gap-3"><AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-[var(--warning-600)]" aria-hidden="true" /><div><h2 className="font-semibold text-primary">Investment Brief unavailable</h2><p className="mt-2 text-sm leading-6 text-secondary">{error ?? 'No investment report has been generated for this period.'}</p>{errorRecovery && <p className="mt-2 text-sm text-tertiary">{errorRecovery}</p>}<button type="button" onClick={() => void loadBrief()} className="btn-secondary mt-4 inline-flex min-h-11 items-center gap-2 px-3 text-sm"><RefreshCw className="h-4 w-4" aria-hidden="true" />Retry brief</button></div></div></section></PageLayout>

  return <PageLayout>
    <PageHeader eyebrow="Investment intelligence" title="Daily Investment Brief" description="A structured morning review of portfolio context, market evidence, and items that need human attention." actions={<Link href="/investments" className="inline-flex min-h-11 items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 text-sm font-medium text-secondary hover:bg-[var(--surface-ambient)]"><ArrowLeft className="h-4 w-4" aria-hidden="true" />Command Center</Link>} className="mb-4" />

    <section className="surface-focal card mb-4 p-4" aria-label="Brief context"><div className="flex flex-wrap items-center gap-x-5 gap-y-3 text-sm"><span className="inline-flex items-center gap-2 font-medium text-primary"><BookOpen className="h-4 w-4 text-[var(--accent-primary)]" aria-hidden="true" />Daily brief</span><span className="text-secondary">As of <strong className="font-medium text-primary">{formatDate(brief.as_of)}</strong></span><span className="text-secondary">Generated <strong className="font-medium text-primary">{formatDate(brief.generated_at)}</strong></span><QualityBadge label={brief.provider_readiness?.status ?? brief.market_data_basis ?? 'Quality unknown'} /></div></section>

    {brief.warnings.length > 0 && <section className="mb-4 rounded-lg border border-[var(--warning-200)] bg-[var(--warning-50)] p-4" role="status" data-testid="brief-warnings"><div className="flex items-start gap-3"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--warning-700)]" aria-hidden="true" /><div><h2 className="font-semibold text-[var(--warning-900)]">Data limitations</h2><ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-[var(--warning-900)]">{brief.warnings.map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}</ul></div></div></section>}

    <section className="grid gap-4 lg:grid-cols-[1.25fr_0.75fr]" aria-label="What matters today">
      <article className="card p-4"><div className="flex items-center justify-between gap-3"><div><h2 className="text-lg font-semibold text-primary">What matters today</h2><p className="mt-1 text-sm text-secondary">Server-authored brief sections, ordered for review.</p></div><Database className="h-5 w-5 text-[var(--accent-primary)]" aria-hidden="true" /></div><div className="mt-3">{brief.sections.length ? brief.sections.map((section) => <Section key={section.name} section={section} onEvidence={setSelectedSection} />) : <p className="py-6 text-sm text-secondary">No structured sections are available for this period.</p>}</div></article>
      <aside className="space-y-4"><article className="card p-4"><div className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-[var(--success-600)]" aria-hidden="true" /><h2 className="font-semibold text-primary">Coverage and freshness</h2></div><dl className="mt-4 space-y-3 text-sm">{brief.coverage && <><div className="flex justify-between gap-4"><dt className="text-secondary">Eligible holdings</dt><dd className="font-mono text-primary">{brief.coverage.eligible_holding_count}</dd></div><div className="flex justify-between gap-4"><dt className="text-secondary">Covered holdings</dt><dd className="font-mono text-primary">{brief.coverage.covered_holding_count}</dd></div><div className="flex justify-between gap-4"><dt className="text-secondary">Coverage basis</dt><dd className="text-primary">{brief.coverage.coverage_basis.replaceAll('_', ' ')}</dd></div></>}</dl><p className="mt-4 border-t border-[var(--border-subtle)] pt-3 text-xs leading-5 text-tertiary">Coverage describes what the server could address. It does not imply that unavailable data is zero or current.</p></article><article className="card p-4"><h2 className="font-semibold text-primary">Portfolio context</h2><p className="mt-2 text-sm leading-6 text-secondary">{brief.portfolio_daily_change ? `Reported daily change: ${brief.portfolio_daily_change}` : 'Portfolio movement is unavailable in this brief.'}</p><Link href="/portfolio" className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-[var(--accent-primary)]">Open Portfolio <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" /></Link></article></aside>
    </section>

    <section className="card mt-4 overflow-hidden" aria-labelledby="review-heading"><div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border-subtle)] p-4"><div><h2 id="review-heading" className="text-lg font-semibold text-primary">Human review queue</h2><p className="mt-1 text-sm text-secondary">Analytical actions from the server. Review does not execute anything.</p></div><label className="inline-flex min-h-11 items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 text-sm text-secondary"><Filter className="h-4 w-4" aria-hidden="true" /><span className="sr-only">Filter review actions</span><select value={actionFilter} onChange={(event) => setActionFilter(event.target.value)} className="bg-transparent text-primary outline-none"><option value="all">All actions</option>{Array.from(new Set((brief.actions ?? []).map((item) => item.action.toLowerCase()))).map((action) => <option key={action} value={action}>{action.toUpperCase()}</option>)}</select></label></div>{actions.length ? actions.map((action, index) => <ActionRow key={`${action.action}-${index}`} action={action} index={index} onSelect={setSelectedAction} />) : <p className="p-5 text-sm text-secondary">No review items are available for this brief.</p>}</section>

    {(selectedSection || selectedAction) && <div className="fixed inset-0 z-[70] flex items-end justify-center bg-black/30 p-0 sm:items-center sm:p-6" role="presentation" onClick={() => { setSelectedSection(null); setSelectedAction(null) }}><section role="dialog" aria-modal="true" aria-labelledby="detail-title" className="max-h-[85dvh] w-full max-w-2xl overflow-y-auto rounded-t-xl bg-[var(--surface-raised)] p-5 shadow-xl sm:rounded-xl" onClick={(event) => event.stopPropagation()}><div className="flex items-start justify-between gap-4"><div><h2 id="detail-title" className="text-lg font-semibold text-primary">{selectedSection ? 'Evidence detail' : 'Review detail'}</h2><p className="mt-1 text-sm text-secondary">{selectedSection?.name ?? selectedAction?.action}</p></div><button type="button" onClick={() => { setSelectedSection(null); setSelectedAction(null) }} className="min-h-11 rounded-md px-3 text-sm text-secondary hover:bg-[var(--surface-ambient)] focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]">Close</button></div>{selectedSection ? <div className="mt-4 space-y-3">{selectedSection.citations.map((citation, index) => <div key={`${citation.source_url}-${index}`} className="rounded-lg border border-[var(--border-subtle)] p-3 text-sm"><p className="font-medium text-primary">{citation.provider}</p><p className="mt-1 text-secondary">Freshness: {citation.freshness}</p><p className="mt-1 text-xs text-tertiary">Retrieved {formatDate(citation.retrieved_at)}{citation.published_at ? ` · Published ${formatDate(citation.published_at)}` : ''}</p><a href={citation.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex min-h-11 items-center gap-1 text-[var(--accent-primary)]">Open source <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" /></a></div>)}</div> : <div className="mt-4 space-y-3 text-sm"><p className="leading-6 text-secondary">{selectedAction?.why}</p><p className="text-secondary">Evidence: {selectedAction?.evidence.length ? selectedAction.evidence.join(', ') : 'Unavailable'}</p><p className="text-secondary">Risks: {selectedAction?.risks.length ? selectedAction.risks.join(', ') : 'None returned'}</p><p className="text-xs leading-5 text-tertiary">This is analytical context for human review. Atlas does not place orders or change portfolio state.</p></div>}</section></div>}
  </PageLayout>
}
