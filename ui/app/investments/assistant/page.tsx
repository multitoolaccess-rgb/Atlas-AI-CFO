'use client'

import { useState } from 'react'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import {
  askInvestmentScout,
  resolveInvestmentAssistantContext,
  type InvestmentAssistantContext,
  type InvestmentAssistantResponse,
  type InvestmentAssistantSelector,
} from '@/lib/investmentAssistant'

type SelectorMode = 'recommendation' | 'committee'

function textValue(value: unknown, fallback = 'Unavailable'): string {
  return typeof value === 'string' && value.trim() ? value : fallback
}

function listValue(value: unknown): string {
  if (!Array.isArray(value) || value.length === 0) return 'Unavailable'
  return value.map((item) => String(item)).join('; ')
}

function selectorFor(mode: SelectorMode, id: string): InvestmentAssistantSelector {
  return mode === 'recommendation' ? { recommendation_id: id } : { committee_finding_id: id }
}

function ContextProjection({ context }: { context: InvestmentAssistantContext }) {
  const recommendation = context.recommendation
  const committee = context.committee

  return (
    <div className="space-y-4">
      {recommendation && (
        <section aria-labelledby="scout-recommendation-heading">
          <h3 id="scout-recommendation-heading" className="font-medium text-primary">Recommendation context</h3>
          <dl className="mt-2 grid gap-3 rounded-lg bg-surface-container p-4 text-sm sm:grid-cols-2">
            <div><dt className="text-tertiary">Security</dt><dd className="mt-1 font-mono text-primary">{textValue(recommendation.security_id)}</dd></div>
            <div><dt className="text-tertiary">Action</dt><dd className="mt-1 text-primary">{textValue(recommendation.recommendation_type)}</dd></div>
            <div><dt className="text-tertiary">Status</dt><dd className="mt-1 text-primary">{textValue(recommendation.status)}</dd></div>
            <div><dt className="text-tertiary">Recommendation as of</dt><dd className="mt-1 text-primary">{textValue(recommendation.recommendation_as_of)}</dd></div>
            <div className="sm:col-span-2"><dt className="text-tertiary">Thesis</dt><dd className="mt-1 leading-6 text-primary">{textValue(recommendation.thesis, textValue(recommendation.rationale))}</dd></div>
            <div><dt className="text-tertiary">Key risks</dt><dd className="mt-1 text-secondary">{listValue(recommendation.key_risks)}</dd></div>
            <div><dt className="text-tertiary">Invalidation</dt><dd className="mt-1 text-secondary">{listValue(recommendation.invalidation_conditions)}</dd></div>
          </dl>
        </section>
      )}

      {committee && (
        <section aria-labelledby="scout-committee-heading">
          <h3 id="scout-committee-heading" className="font-medium text-primary">Committee context</h3>
          <dl className="mt-2 grid gap-3 rounded-lg bg-surface-container p-4 text-sm sm:grid-cols-2">
            <div><dt className="text-tertiary">Security</dt><dd className="mt-1 font-mono text-primary">{textValue(committee.subject_security_id)}</dd></div>
            <div><dt className="text-tertiary">Committee view</dt><dd className="mt-1 text-primary">{textValue(committee.committee_view)}</dd></div>
            <div><dt className="text-tertiary">Analysis as of</dt><dd className="mt-1 text-primary">{textValue(committee.analysis_as_of)}</dd></div>
            <div className="sm:col-span-2"><dt className="text-tertiary">Thesis</dt><dd className="mt-1 leading-6 text-primary">{textValue(committee.thesis)}</dd></div>
            <div><dt className="text-tertiary">Key risks</dt><dd className="mt-1 text-secondary">{listValue(committee.key_risks)}</dd></div>
            <div><dt className="text-tertiary">Uncertainties</dt><dd className="mt-1 text-secondary">{listValue(committee.uncertainties)}</dd></div>
          </dl>
        </section>
      )}
    </div>
  )
}

export default function InvestmentAssistantPage() {
  const [selectorMode, setSelectorMode] = useState<SelectorMode>('recommendation')
  const [contextId, setContextId] = useState('')
  const [context, setContext] = useState<InvestmentAssistantContext | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<InvestmentAssistantResponse | null>(null)

  const loadContext = async () => {
    const value = contextId.trim()
    if (!value || loading) return
    setLoading(true)
    setError(null)
    setAnswer(null)
    try {
      setContext(await resolveInvestmentAssistantContext(selectorFor(selectorMode, value)))
    } catch {
      setContext(null)
      setError('Investment context could not be loaded. No canonical data was changed.')
    } finally {
      setLoading(false)
    }
  }

  const askScout = async () => {
    const text = question.trim()
    const value = contextId.trim()
    if (!text || !value || !context || loading) return
    setLoading(true)
    setError(null)
    setAnswer(null)
    try {
      setAnswer(await askInvestmentScout(selectorFor(selectorMode, value), text))
    } catch {
      setError('Scout is unavailable. No canonical investment state was changed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <PageLayout mobileFullBleed>
      <PageHeader
        title="Investment Scout"
        description="Ask questions about validated investment context. Scout is read-only and cites Atlas-owned data."
        className="mb-6"
      />
      <div className="w-full min-w-0 max-w-full overflow-x-hidden">
        <main className="min-w-0 max-w-full space-y-6 overflow-x-hidden" aria-label="Investment Scout workspace">
          <section className="card min-w-0 max-w-full space-y-4" aria-labelledby="scout-context-heading">
            <div className="min-w-0 max-w-full">
              <h2 id="scout-context-heading" className="text-lg font-semibold text-primary">Choose validated context</h2>
              <p className="mt-1 text-sm text-secondary">Use a persisted recommendation or committee finding ID. Security, discovery, and portfolio selectors are not enabled in this bounded Scout slice.</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-[minmax(0,13rem)_minmax(0,1fr)_auto] sm:items-end">
              <label className="text-sm text-secondary">
                <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-tertiary">Context type</span>
                <select
                  aria-label="Context type"
                  value={selectorMode}
                  onChange={(event) => setSelectorMode(event.target.value as SelectorMode)}
                  className="min-h-11 w-full rounded-lg border border-outline-variant bg-surface px-3 text-primary"
                >
                  <option value="recommendation">Recommendation</option>
                  <option value="committee">Committee finding</option>
                </select>
              </label>
              <label className="text-sm text-secondary">
                <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-tertiary">Persisted context ID</span>
                <input
                  id="investment-context-id"
                  value={contextId}
                  onChange={(event) => setContextId(event.target.value)}
                  onKeyDown={(event) => { if (event.key === 'Enter') void loadContext() }}
                  placeholder={selectorMode === 'recommendation' ? 'investment-recommendation:…' : 'committee:…'}
                  className="min-w-0 w-full rounded-lg border border-outline-variant bg-surface px-3 py-2 text-primary"
                />
              </label>
              <button type="button" onClick={() => void loadContext()} disabled={loading || !contextId.trim()} className="min-h-11 rounded-lg bg-primary px-4 py-2 font-medium text-on-primary disabled:opacity-50">
                {loading ? 'Loading…' : 'Load context'}
              </button>
            </div>
            <p className="max-w-full break-words text-xs text-secondary">Read-only context resolution. Scout cannot create recommendations, decisions, outcomes, or trades.</p>
          </section>

          {error && <div role="alert" className="rounded-lg border border-error/30 bg-error/5 p-4 text-sm text-error">{error}</div>}

          {context && (
            <section className="card min-w-0 max-w-full space-y-5" aria-labelledby="scout-result-heading">
              <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 id="scout-result-heading" className="text-lg font-semibold text-primary">Validated context</h2>
                  <p className="font-mono text-xs text-secondary">{context.context_id}</p>
                </div>
                <span className="rounded-full bg-surface-container px-3 py-1 text-xs font-medium text-secondary">{context.state}</span>
              </div>
              {context.context_as_of && <p className="text-sm text-secondary">As of {new Date(context.context_as_of).toLocaleString()}</p>}
              <ContextProjection context={context} />
              <div>
                <h3 className="font-medium text-primary">Evidence references</h3>
                {context.evidence.length ? (
                  <ul className="mt-2 space-y-2">
                    {context.evidence.map((item) => <li key={String(item.packet_id)} className="rounded-lg border border-outline-variant p-3 text-sm text-secondary"><span className="font-medium text-primary">Evidence packet:</span> <span className="font-mono">{String(item.packet_id)}</span> · server-validated hash {String(item.packet_hash).slice(0, 12)}…</li>)}
                  </ul>
                ) : <p className="mt-2 text-sm text-secondary">No evidence packet is available for this context.</p>}
              </div>
              {!!context.limitations.length && <div role="note" className="rounded-lg bg-warning/10 p-3 text-sm text-secondary"><strong>Limitations:</strong> {context.limitations.join(' ')}</div>}
              <div className="space-y-3 border-t border-outline-variant pt-4" aria-labelledby="scout-question-heading">
                <h3 id="scout-question-heading" className="font-medium text-primary">Ask Scout</h3>
                <label className="sr-only" htmlFor="investment-question">Question</label>
                <textarea id="investment-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="What should I understand about this context?" rows={3} className="w-full rounded-lg border border-outline-variant bg-surface px-3 py-2 text-primary" />
                <button type="button" onClick={() => void askScout()} disabled={loading || !question.trim()} className="min-h-11 rounded-lg bg-primary px-4 py-2 font-medium text-on-primary disabled:opacity-50">{loading ? 'Thinking…' : 'Ask Scout'}</button>
                {answer && <div role="status" className="rounded-lg border border-outline-variant bg-surface-container p-4 text-sm text-primary"><span className="sr-only">Scout response status: </span>{answer.sections.map((section, index) => <div key={`${section.kind}-${index}`} className="mb-3 last:mb-0"><p>{section.text}</p>{section.citations.length > 0 && <p className="mt-1 text-xs text-secondary">Citations: {section.citations.map((citation) => citation.citation_id).join(', ')}</p>}</div>)}<p className="mt-2 text-xs text-secondary">Status: {answer.status}. This response is read-only and grounded only in the selected server-owned context.</p></div>}
              </div>
            </section>
          )}
        </main>
      </div>
    </PageLayout>
  )
}
