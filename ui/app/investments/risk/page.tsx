'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, ArrowLeft, Database, FlaskConical, RefreshCw, ShieldCheck } from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import { getInvestmentPortfolioBaseline, previewInvestmentRiskScenario, type PortfolioBaseline, type RiskMetric, type RiskScenario } from '@/lib/investmentRisk'

function metricLabel(name: string): string {
  return name.replaceAll('_', ' ')
}

function valueLabel(metric: RiskMetric): string {
  if (metric.value === null) return 'Unavailable'
  if (metric.unit === 'percent') return `${metric.value}%`
  if (metric.unit === 'currency') return `${metric.currency ?? 'Unknown currency'} ${metric.value}`
  return metric.value
}

function StateLabel({ state }: { state: string }) {
  return <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-ambient)] px-2 py-1 text-xs font-medium capitalize text-secondary">{state.replaceAll('_', ' ')}</span>
}

function MetricsTable({ metrics, caption }: { metrics: RiskMetric[]; caption: string }) {
  return <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]"><table className="w-full min-w-[42rem] text-left text-sm"><caption className="sr-only">{caption}</caption><thead className="bg-[var(--surface-ambient)] text-xs text-tertiary"><tr><th scope="col" className="px-4 py-3 font-medium">Metric</th><th scope="col" className="px-4 py-3 font-medium">Value</th><th scope="col" className="px-4 py-3 font-medium">State</th><th scope="col" className="px-4 py-3 font-medium">Limitation</th></tr></thead><tbody className="divide-y divide-[var(--border-subtle)]">{metrics.map((metric) => <tr key={metric.name}><th scope="row" className="px-4 py-3 font-medium capitalize text-primary">{metricLabel(metric.name)}</th><td className="px-4 py-3 font-mono text-primary">{valueLabel(metric)}</td><td className="px-4 py-3"><StateLabel state={metric.state} /></td><td className="px-4 py-3 text-secondary">{metric.limitation ?? 'Server-provided metric'}</td></tr>)}</tbody></table></div>
}

function BaselineSummary({ baseline }: { baseline: PortfolioBaseline }) {
  const positionCount = baseline.metrics.find((metric) => metric.name === 'position_count')
  const observedCount = baseline.metrics.find((metric) => metric.name === 'observed_position_count')
  return <>
    <section className="surface-focal card p-5" aria-labelledby="baseline-heading"><div className="flex flex-wrap items-start justify-between gap-4"><div className="flex items-start gap-3"><ShieldCheck className="mt-1 h-5 w-5 shrink-0 text-[var(--accent-primary)]" aria-hidden="true" /><div><p className="text-xs font-semibold uppercase tracking-wide text-tertiary">Server-owned portfolio baseline</p><h2 id="baseline-heading" className="mt-1 text-xl font-semibold text-primary">Current portfolio context</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-secondary">This baseline is current-only. It is not a historical portfolio valuation and does not predict future performance.</p></div></div><span className="rounded-full border border-[var(--border-subtle)] px-3 py-1 text-xs font-semibold capitalize text-secondary">{baseline.capability.replaceAll('_', ' ')}</span></div><div className="mt-5 grid gap-3 sm:grid-cols-3"><div className="card p-4"><p className="text-xs text-tertiary">Total value</p><p className="mt-2 font-mono text-xl font-semibold text-primary">{baseline.total_value === null ? 'Unavailable' : `${baseline.currency ?? 'Unknown'} ${baseline.total_value}`}</p></div><div className="card p-4"><p className="text-xs text-tertiary">Positions</p><p className="mt-2 font-mono text-xl font-semibold text-primary">{positionCount?.value ?? 'Unavailable'}</p></div><div className="card p-4"><p className="text-xs text-tertiary">Observed values</p><p className="mt-2 font-mono text-xl font-semibold text-primary">{observedCount?.value ?? 'Unavailable'}</p></div></div><dl className="mt-5 grid gap-2 text-sm sm:grid-cols-2"><div><dt className="text-tertiary">As of</dt><dd className="text-primary">{new Date(baseline.as_of).toLocaleString()}</dd></div><div><dt className="text-tertiary">Known at</dt><dd className="text-primary">{baseline.as_known_at ? new Date(baseline.as_known_at).toLocaleString() : 'Unavailable'}</dd></div><div><dt className="text-tertiary">Freshness</dt><dd className="text-primary"><StateLabel state={baseline.freshness} /></dd></div><div><dt className="text-tertiary">Completeness</dt><dd className="capitalize text-primary">{baseline.completeness}</dd></div></dl></section>
    <section className="mt-4 card p-5" aria-labelledby="metric-heading"><div className="flex items-center gap-2"><Database className="h-4 w-4 text-[var(--accent-primary)]" aria-hidden="true" /><h2 id="metric-heading" className="font-semibold text-primary">Descriptive portfolio metrics</h2></div><p className="mt-1 text-sm text-secondary">Only server-approved descriptive values are shown. Unsupported portfolio risk methods remain unavailable.</p><div className="mt-4"><MetricsTable metrics={baseline.metrics} caption="Server-owned portfolio baseline metrics" /></div></section>
    <section className="mt-4 card p-5" aria-labelledby="positions-heading"><h2 id="positions-heading" className="font-semibold text-primary">Position coverage</h2><p className="mt-1 text-sm text-secondary">Account names and account identifiers are intentionally omitted from this projection.</p><div className="mt-4 overflow-x-auto rounded-lg border border-[var(--border-subtle)]"><table className="w-full min-w-[44rem] text-left text-sm"><caption className="sr-only">Server-owned portfolio position coverage</caption><thead className="bg-[var(--surface-ambient)] text-xs text-tertiary"><tr><th scope="col" className="px-4 py-3 font-medium">Security</th><th scope="col" className="px-4 py-3 font-medium">Value</th><th scope="col" className="px-4 py-3 font-medium">Value state</th><th scope="col" className="px-4 py-3 font-medium">Identity</th><th scope="col" className="px-4 py-3 font-medium">Source</th></tr></thead><tbody className="divide-y divide-[var(--border-subtle)]">{baseline.positions.map((position) => <tr key={position.position_id}><th scope="row" className="px-4 py-3 font-medium text-primary">{position.security.symbol ?? 'Unresolved security'}</th><td className="px-4 py-3 font-mono text-primary">{position.market_value === null ? 'Unavailable' : `${position.currency ?? 'Unknown'} ${position.market_value}`}</td><td className="px-4 py-3"><StateLabel state={position.market_value_state} /></td><td className="px-4 py-3"><StateLabel state={position.security.state} /></td><td className="px-4 py-3 font-mono text-xs text-tertiary">{position.source_id}</td></tr>)}</tbody></table>{baseline.positions.length === 0 && <p className="p-5 text-sm text-secondary">No active positions are available for the current baseline.</p>}</div></section>
    {baseline.omissions.length > 0 && <section className="mt-4 card p-5" aria-labelledby="limitations-heading"><div className="flex items-start gap-3"><AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-[var(--warning-600)]" aria-hidden="true" /><div><h2 id="limitations-heading" className="font-semibold text-primary">Baseline limitations</h2><ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-secondary">{baseline.omissions.map((item) => <li key={item}>{item.replaceAll('_', ' ')}</li>)}</ul></div></div></section>}
  </>
}

function ScenarioPreview({ baseline, scenario, onScenario }: { baseline: PortfolioBaseline; scenario: RiskScenario | null; onScenario: (scenario: RiskScenario) => void }) {
  const eligible = useMemo(() => baseline.positions.filter((position) => position.market_value_state === 'available' && position.currency === baseline.currency), [baseline])
  const [positionId, setPositionId] = useState<number | ''>(eligible[0]?.position_id ?? '')
  const [delta, setDelta] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (positionId === '' && eligible[0]) setPositionId(eligible[0].position_id)
  }, [eligible, positionId])

  const submit = async () => {
    if (positionId === '' || !delta.trim()) return
    setSubmitting(true); setError(null)
    try { onScenario(await previewInvestmentRiskScenario({ baseline_id: baseline.baseline_id, position_id: positionId, market_value_delta: delta.trim() })) }
    catch { setError('This hypothetical preview is unavailable for the selected baseline or input.') }
    finally { setSubmitting(false) }
  }

  return <section className="mt-4 card p-5" aria-labelledby="scenario-heading"><div className="flex items-start gap-3"><FlaskConical className="mt-1 h-5 w-5 shrink-0 text-[var(--accent-primary)]" aria-hidden="true" /><div><h2 id="scenario-heading" className="font-semibold text-primary">Hypothetical position-value preview</h2><p className="mt-1 text-sm leading-6 text-secondary">Explore a bounded descriptive value change against the server baseline. This is not a prediction, recommendation, allocation instruction, or execution.</p></div></div>{eligible.length === 0 ? <p className="mt-4 rounded-lg border border-dashed border-[var(--border-subtle)] p-4 text-sm text-secondary">A complete single-currency baseline is required before a hypothetical preview is available.</p> : <><div className="mt-5 grid gap-4 md:grid-cols-[1fr_1fr_auto] md:items-end"><label className="text-sm text-secondary"><span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-tertiary">Position</span><select value={positionId} onChange={(event) => setPositionId(event.target.value ? Number(event.target.value) : '')} className="min-h-11 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-raised)] px-3 text-primary"><option value="">Select a position</option>{eligible.map((position) => <option key={position.position_id} value={position.position_id}>{position.security.symbol ?? 'Unresolved'} · {position.position_id}</option>)}</select></label><label className="text-sm text-secondary"><span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-tertiary">Value delta</span><input value={delta} onChange={(event) => setDelta(event.target.value)} inputMode="decimal" placeholder="Example: 25" className="min-h-11 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-raised)] px-3 font-mono text-primary" /></label><button type="button" onClick={() => void submit()} disabled={submitting || positionId === '' || !delta.trim()} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-[var(--accent-primary)] px-4 text-sm font-semibold text-white disabled:opacity-50">{submitting ? 'Previewing…' : 'Preview change'}</button></div>{error && <p className="mt-4 text-sm text-[var(--danger-600)]" role="alert">{error}</p>}{scenario && <div className="mt-5 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-ambient)] p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wide text-tertiary">Server result</p><p className="mt-1 text-sm font-semibold text-primary">Hypothetical analysis only · not a prediction</p></div><StateLabel state={scenario.hypothetical ? 'hypothetical' : 'unavailable'} /></div><div className="mt-4"><MetricsTable metrics={scenario.metrics} caption="Hypothetical portfolio value preview metrics" /></div><p className="mt-4 text-xs leading-5 text-tertiary">As of {new Date(scenario.as_of).toLocaleString()} · evaluated {new Date(scenario.evaluated_at).toLocaleString()} · result {scenario.result_hash.slice(0, 12)}…</p></div>}</>}</section>
}

export default function InvestmentRiskPage() {
  const [baseline, setBaseline] = useState<PortfolioBaseline | null>(null)
  const [scenario, setScenario] = useState<RiskScenario | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setBaseline(await getInvestmentPortfolioBaseline()) }
    catch { setError('Portfolio risk context is unavailable. No risk result is shown without a server-owned baseline.') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { void load() }, [load])

  return <PageLayout><div className="min-w-0 max-w-full overflow-x-hidden" style={{ maxWidth: '100vw' }}><PageHeader eyebrow="Investment intelligence · UI-11" title="Risk and scenario views" description="Review current portfolio coverage and bounded hypothetical value changes from server-owned data." actions={<Link href="/investments" className="inline-flex min-h-11 items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 text-sm text-secondary"><ArrowLeft className="h-4 w-4" aria-hidden="true" />Command Center</Link>} className="mb-6" />{loading ? <section className="card p-6" role="status" aria-busy="true">Loading server-owned portfolio context…</section> : error ? <section className="card p-6" role="alert"><div className="flex items-start gap-3"><AlertTriangle className="mt-0.5 h-5 w-5 text-[var(--warning-600)]" aria-hidden="true" /><div><h2 className="font-semibold text-primary">Portfolio context unavailable</h2><p className="mt-2 text-sm text-secondary">{error}</p><button type="button" onClick={() => void load()} className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 text-sm text-secondary"><RefreshCw className="h-4 w-4" aria-hidden="true" />Retry</button></div></div></section> : baseline && <><BaselineSummary baseline={baseline} /><ScenarioPreview baseline={baseline} scenario={scenario} onScenario={setScenario} /><footer className="mt-5 flex items-start gap-2 text-xs leading-5 text-tertiary"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-[var(--accent-primary)]" aria-hidden="true" /><span>Atlas analyzes and explains. This surface is descriptive, current-only, and does not mutate portfolio state.</span></footer></>}</div></PageLayout>
}
