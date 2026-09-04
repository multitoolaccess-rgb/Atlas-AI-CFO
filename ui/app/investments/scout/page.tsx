'use client'

import { useEffect, useState } from 'react'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import {
  getInvestmentScoutRun,
  listInvestmentScoutRuns,
  researchInvestmentSecurity,
  type ScoutResearchResult,
  type ScoutRunSummary,
  type ScoutSelector,
} from '@/lib/investmentScout'

type SelectorMode = 'recommendation' | 'committee' | 'security'

function selectorFor(mode: SelectorMode, id: string): ScoutSelector {
  if (mode === 'recommendation') return { recommendation_id: id }
  if (mode === 'committee') return { committee_finding_id: id }
  return { security_id: id }
}

function formatDate(value: string | null): string {
  if (!value) return 'Unavailable'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? 'Unavailable' : parsed.toLocaleString()
}

function StateBadge({ state }: { state: ScoutResearchResult['state'] }) {
  return <span className="rounded-full bg-surface-container px-3 py-1 text-xs font-semibold uppercase tracking-wide text-secondary">{state}</span>
}

export default function InvestmentScoutResearchPage() {
  const [mode, setMode] = useState<SelectorMode>('security')
  const [id, setId] = useState('')
  const [question, setQuestion] = useState('What changed recently for this investment?')
  const [result, setResult] = useState<ScoutResearchResult | null>(null)
  const [history, setHistory] = useState<ScoutRunSummary[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function loadHistory() {
    setHistoryLoading(true)
    try {
      setHistory(await listInvestmentScoutRuns())
    } catch {
      // History is supplementary; preserve the research form if it is
      // unavailable or the provider-backed feature is disabled.
      setHistory([])
    } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => {
    void loadHistory()
  }, [])

  async function submit() {
    const selectorId = id.trim()
    const prompt = question.trim()
    if (!selectorId || !prompt || loading) return
    setLoading(true)
    setError(null)
    try {
      setResult(await researchInvestmentSecurity(selectorFor(mode, selectorId), prompt))
      await loadHistory()
    } catch {
      setResult(null)
      setError('Scout research is unavailable. No investment state was changed.')
    } finally {
      setLoading(false)
    }
  }

  async function openHistory(runId: string) {
    setError(null)
    try {
      setResult(await getInvestmentScoutRun(runId))
    } catch {
      setError('This saved Scout run is unavailable. No investment state was changed.')
    }
  }

  return (
    <PageLayout mobileFullBleed>
      <PageHeader
        title="Investment Context Scout"
        description="Review bounded, server-retrieved context for one canonical investment. External content is untrusted data, not instructions."
        className="mb-6"
      />
      <main className="min-w-0 max-w-full space-y-6 overflow-x-hidden" aria-label="Investment Context Scout">
        <section className="card min-w-0 space-y-4" aria-labelledby="scout-research-form-heading">
          <div>
            <h2 id="scout-research-form-heading" className="text-lg font-semibold text-primary">Run current-context research</h2>
            <p className="mt-1 text-sm text-secondary">Use a canonical recommendation, committee finding, or an owner-authorized held security. Arbitrary URLs and general web search are not accepted.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-[minmax(0,13rem)_minmax(0,1fr)]">
            <label className="text-sm text-secondary">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-tertiary">Context type</span>
              <select aria-label="Context type" value={mode} onChange={(event) => setMode(event.target.value as SelectorMode)} className="min-h-11 w-full rounded-lg border border-outline-variant bg-surface px-3 text-primary">
                <option value="security">Held security</option>
                <option value="recommendation">Recommendation</option>
                <option value="committee">Committee finding</option>
              </select>
            </label>
            <label className="text-sm text-secondary">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-tertiary">Canonical ID</span>
              <input value={id} onChange={(event) => setId(event.target.value)} className="min-h-11 w-full min-w-0 rounded-lg border border-outline-variant bg-surface px-3 py-2 text-primary" placeholder="sec:… or investment-recommendation:…" />
            </label>
          </div>
          <label className="block text-sm text-secondary">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-tertiary">Research question</span>
            <textarea value={question} onChange={(event) => setQuestion(event.target.value)} rows={3} maxLength={500} className="w-full rounded-lg border border-outline-variant bg-surface px-3 py-2 text-primary" />
          </label>
          <button type="button" onClick={() => void submit()} disabled={loading || !id.trim() || !question.trim()} className="min-h-11 rounded-lg bg-primary px-4 py-2 font-medium text-on-primary disabled:opacity-50">{loading ? 'Researching…' : 'Research context'}</button>
          <p className="text-xs text-secondary">Read-only analysis only. Scout cannot create recommendations, decisions, outcomes, orders, trades, transfers, or portfolio changes.</p>
        </section>

        {loading && <p role="status" className="rounded-lg bg-surface-container p-4 text-sm text-secondary">Retrieving bounded sources…</p>}
        {error && <div role="alert" className="rounded-lg border border-error/30 bg-error/5 p-4 text-sm text-error">{error}</div>}

        <section className="card min-w-0 space-y-4" aria-labelledby="scout-history-heading">
          <div>
            <h2 id="scout-history-heading" className="text-lg font-semibold text-primary">Saved Scout runs</h2>
            <p className="mt-1 text-sm text-secondary">Owner-scoped immutable research history. Loading a run only reads its stored projection.</p>
          </div>
          {historyLoading ? <p role="status" className="text-sm text-secondary">Loading saved runs…</p> : history.length ? <ul className="space-y-2">{history.map((run) => <li key={run.run_id} className="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-lg border border-outline-variant p-3"><div className="min-w-0"><p className="font-mono text-sm text-primary">{run.symbol} · {run.state}</p><p className="break-all text-xs text-secondary">{run.run_id} · {run.source_count} source{run.source_count === 1 ? '' : 's'} · {formatDate(run.as_of)}</p></div><button type="button" onClick={() => void openHistory(run.run_id)} className="min-h-10 rounded-lg border border-outline-variant px-3 text-sm text-primary">Open run</button></li>)}</ul> : <p className="text-sm text-secondary">No saved Scout runs are available for this owner.</p>}
        </section>

        {result && (
          <section className="card min-w-0 space-y-6" aria-labelledby="scout-research-result-heading">
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <h2 id="scout-research-result-heading" className="text-lg font-semibold text-primary">Research result</h2>
                <p className="break-all font-mono text-xs text-secondary">{result.run_id}</p>
              </div>
              <StateBadge state={result.state} />
            </div>
            <div className="grid gap-3 rounded-lg bg-surface-container p-4 text-sm sm:grid-cols-2">
              <div><dt className="text-tertiary">Canonical security</dt><dd className="mt-1 break-all font-mono text-primary">{result.security.security.security_id}</dd></div>
              <div><dt className="text-tertiary">Symbol alias</dt><dd className="mt-1 font-mono text-primary">{result.security.symbol}</dd></div>
              <div><dt className="text-tertiary">Research as of</dt><dd className="mt-1 text-primary">{formatDate(result.as_of)}</dd></div>
              <div><dt className="text-tertiary">Known at</dt><dd className="mt-1 text-primary">{formatDate(result.as_known_at)}</dd></div>
            </div>
            <div className="rounded-lg border border-warning/30 bg-warning/10 p-4 text-sm text-secondary"><strong className="text-primary">Current-context research only.</strong> This is not a historical reconstruction, forecast, recommendation, guarantee, or execution instruction.</div>

            <div>
              <h3 className="font-medium text-primary">Claims and evidence</h3>
              {result.claims.length ? (
                <div className="mt-3 overflow-x-auto rounded-lg border border-outline-variant">
                  <table className="min-w-full text-left text-sm">
                    <caption className="sr-only">Scout claims, evidence, and source references</caption>
                    <thead className="bg-surface-container text-xs uppercase tracking-wide text-tertiary"><tr><th scope="col" className="px-3 py-2">Type</th><th scope="col" className="px-3 py-2">Claim</th><th scope="col" className="px-3 py-2">Evidence</th><th scope="col" className="px-3 py-2">Sources</th></tr></thead>
                    <tbody>{result.claims.map((claim) => <tr key={claim.claim_id} className="border-t border-outline-variant align-top"><td className="px-3 py-3 text-secondary">{claim.kind}</td><td className="max-w-xl px-3 py-3 text-primary">{claim.text}</td><td className="px-3 py-3 font-mono text-xs text-secondary">{claim.evidence_ids.length ? claim.evidence_ids.join(', ') : 'Unavailable'}</td><td className="px-3 py-3 font-mono text-xs text-secondary">{claim.source_ids.length ? claim.source_ids.join(', ') : 'Unavailable'}</td></tr>)}</tbody>
                  </table>
                </div>
              ) : <p className="mt-2 text-sm text-secondary">No source-backed claims were available.</p>}
            </div>

            <div>
              <h3 className="font-medium text-primary">Evidence snapshots</h3>
              {result.evidence.length ? <ul className="mt-3 space-y-2">{result.evidence.map((item) => <li key={item.evidence_id} className="rounded-lg border border-outline-variant p-3 text-xs text-secondary"><p className="font-mono text-primary">{item.evidence_id}</p><p className="mt-1">Source: <span className="font-mono">{item.source_id}</span> · retrieved {formatDate(item.retrieved_at)}</p><p className="mt-1">{item.summary}</p></li>)}</ul> : <p className="mt-2 text-sm text-secondary">No evidence snapshots were available.</p>}
            </div>

            <div>
              <h3 className="font-medium text-primary">Retrieved sources</h3>
              {result.sources.length ? <ul className="mt-3 space-y-3">{result.sources.map((source) => <li key={source.source_id} className="rounded-lg border border-outline-variant p-4 text-sm"><a href={source.source_url} target="_blank" rel="noreferrer" className="font-medium text-primary underline underline-offset-2">{source.title}</a><p className="mt-1 text-secondary">{source.publisher || source.provider} · {source.source_type} · published {formatDate(source.publication_at)} · retrieved {formatDate(source.retrieved_at)}</p>{source.excerpt && <p className="mt-2 text-secondary">{source.excerpt}</p>}<p className="mt-2 break-all font-mono text-xs text-tertiary">Source hash: {source.source_hash}</p></li>)}</ul> : <p className="mt-2 text-sm text-secondary">No sources were retrieved.</p>}
            </div>

            {(result.limitations.length > 0 || result.warnings.length > 0) && <div role="note" className="rounded-lg bg-surface-container p-4 text-sm text-secondary"><h3 className="font-medium text-primary">Limitations and warnings</h3><ul className="mt-2 list-disc space-y-1 pl-5">{[...result.limitations, ...result.warnings].map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></div>}
            <div className="grid gap-3 border-t border-outline-variant pt-4 text-xs text-secondary sm:grid-cols-2"><p>Methodology: <span className="font-mono">{result.methodology_version}</span></p><p>Calculation: <span className="font-mono">{result.calculation_version}</span></p><p>Hypothetical: {String(result.hypothetical)}</p><p>Predictive: {String(result.predictive)}</p></div>
          </section>
        )}
      </main>
    </PageLayout>
  )
}
