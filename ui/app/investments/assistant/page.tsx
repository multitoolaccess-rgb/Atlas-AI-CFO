'use client'

import { useState } from 'react'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import { resolveInvestmentAssistantContext, askInvestmentScout, type InvestmentAssistantContext, type InvestmentAssistantResponse } from '@/lib/investmentAssistant'
export default function InvestmentAssistantPage() {
  const [securityId, setSecurityId] = useState('')
  const [context, setContext] = useState<InvestmentAssistantContext | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<InvestmentAssistantResponse | null>(null)

  const loadContext = async () => {
    const value = securityId.trim()
    if (!value || loading) return
    setLoading(true)
    setError(null)
    try {
      setContext(await resolveInvestmentAssistantContext({ security_id: value }))
    } catch {
      setContext(null)
      setError('Investment context could not be loaded. No canonical data was changed.')
    } finally {
      setLoading(false)
    }
  }

  const askScout = async () => {
    const text = question.trim()
    if (!text || !context || loading) return
    setLoading(true)
    setError(null)
    setAnswer(null)
    try {
      setAnswer(await askInvestmentScout({ security_id: securityId.trim() }, text))
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
      />      <div className="w-full min-w-0 max-w-full overflow-x-hidden">
      <main className="min-w-0 max-w-full space-y-6 overflow-x-hidden" aria-label="Investment Scout workspace">
        <section className="card min-w-0 max-w-full space-y-4" aria-labelledby="scout-context-heading">
              <div className="min-w-0 max-w-full">
                <h2 id="scout-context-heading" className="text-lg font-semibold text-primary">Choose context</h2>

            <p className="mt-1 text-sm text-secondary">Enter a canonical security identifier. Tickers are not treated as authority.</p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <label className="sr-only" htmlFor="investment-security-id">Security ID</label>
            <input
              id="investment-security-id"
              value={securityId}
              onChange={(event) => setSecurityId(event.target.value)}
              onKeyDown={(event) => { if (event.key === 'Enter') void loadContext() }}
              placeholder="sec:example"
              className="min-w-0 flex-1 rounded-lg border border-outline-variant bg-surface px-3 py-2 text-primary"
            />
            <button type="button" onClick={() => void loadContext()} disabled={loading || !securityId.trim()} className="rounded-lg bg-primary px-4 py-2 font-medium text-on-primary disabled:opacity-50">
              {loading ? 'Loading…' : 'Load context'}
            </button>
          </div>              <p className="max-w-full break-words text-xs text-secondary">Read-only context resolution. Scout cannot create recommendations, decisions, outcomes, or trades.</p>

        </section>

        {error && <div role="alert" className="rounded-lg border border-error/30 bg-error/5 p-4 text-sm text-error">{error}</div>}

        {context && (
          <section className="card min-w-0 max-w-full space-y-5" aria-labelledby="scout-result-heading">              <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">

              <div>
                <h2 id="scout-result-heading" className="text-lg font-semibold text-primary">Validated context</h2>
                <p className="text-sm text-secondary">{context.context_id}</p>
              </div>
              <span className="rounded-full bg-surface-container px-3 py-1 text-xs font-medium text-secondary">{context.state}</span>
            </div>
            {context.context_as_of && <p className="text-sm text-secondary">As of {new Date(context.context_as_of).toLocaleString()}</p>}
            {context.recommendation && <div className="min-w-0"><h3 className="font-medium text-primary">Recommendation</h3><pre className="mt-2 max-h-72 max-w-full overflow-auto whitespace-pre-wrap break-words rounded-lg bg-surface-container p-3 text-xs text-secondary">{JSON.stringify(context.recommendation, null, 2)}</pre></div>}
            {context.committee && <div className="min-w-0"><h3 className="font-medium text-primary">Committee context</h3><pre className="mt-2 max-h-72 max-w-full overflow-auto whitespace-pre-wrap break-words rounded-lg bg-surface-container p-3 text-xs text-secondary">{JSON.stringify(context.committee, null, 2)}</pre></div>}
            <div><h3 className="font-medium text-primary">Evidence references</h3>{context.evidence.length ? <ul className="mt-2 space-y-2">{context.evidence.map((item) => <li key={String(item.packet_id)} className="rounded-lg border border-outline-variant p-3 text-sm text-secondary">{String(item.packet_id)} · {String(item.packet_hash)} · Atlas validated</li>)}</ul> : <p className="mt-2 text-sm text-secondary">No evidence packet is available for this context.</p>}</div>
            {!!context.limitations.length && <div role="note" className="rounded-lg bg-warning/10 p-3 text-sm text-secondary"><strong>Limitations:</strong> {context.limitations.join(' ')}</div>}
            <div className="space-y-3 border-t border-outline-variant pt-4" aria-labelledby="scout-question-heading">
              <h3 id="scout-question-heading" className="font-medium text-primary">Ask Scout</h3>
              <label className="sr-only" htmlFor="investment-question">Question</label>
              <textarea id="investment-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="What should I understand about this context?" rows={3} className="w-full rounded-lg border border-outline-variant bg-surface px-3 py-2 text-primary" />
              <button type="button" onClick={() => void askScout()} disabled={loading || !question.trim()} className="rounded-lg bg-primary px-4 py-2 font-medium text-on-primary disabled:opacity-50">{loading ? 'Thinking…' : 'Ask Scout'}</button>
              {answer && <div role="status" className="rounded-lg border border-outline-variant bg-surface-container p-4 text-sm text-primary"><span className="sr-only">Scout response status: </span>{answer.sections.map((section, index) => <div key={`${section.kind}-${index}`} className="mb-3 last:mb-0"><p>{section.text}</p>{section.citations.length > 0 && <p className="mt-1 text-xs text-secondary">Citations: {section.citations.map((citation) => citation.citation_id).join(', ')}</p>}</div>)}<p className="mt-2 text-xs text-secondary">Status: {answer.status}. This response is read-only and grounded only in the selected server-owned context.</p></div>}
            </div>
          </section>
        )}
      </main>
      </div>
    </PageLayout>
  )
}
