'use client'

import { useEffect, useRef, useState } from 'react'
import { generateMarketBrief, getMarketBrief, listMarketBriefs, type BriefIndex, type MarketBrief } from '@/lib/marketBriefs'

export default function MarketBriefArchive() {
  const [items, setItems] = useState<BriefIndex[]>([])
  const [brief, setBrief] = useState<MarketBrief | null>(null)
  const [message, setMessage] = useState('Loading brief archive…')
  const [generating, setGenerating] = useState(false)
  const detailRequest = useRef(0)
  useEffect(() => { listMarketBriefs().then(setItems).then(() => setMessage('')).catch(() => setMessage('Brief archive is unavailable.')) }, [])
  async function open(id: string) {
    const requestId = ++detailRequest.current
    setBrief(null)
    setMessage('Loading brief…')
    try {
      const nextBrief = await getMarketBrief(id)
      if (requestId === detailRequest.current) {
        setBrief(nextBrief)
        setMessage('')
      }
    } catch {
      if (requestId === detailRequest.current) setMessage('Brief is unavailable.')
    }
  }
  async function generate() {
    setGenerating(true)
    setMessage('Generating a deterministic market brief…')
    try {
      const result = await generateMarketBrief()
      setBrief(result.brief)
      setItems(previous => {
        const next = { brief_id: result.brief_id, report_window: 'latest', generated_at: result.brief.generated_at }
        return [next, ...previous.filter(item => item.brief_id !== result.brief_id)]
      })
      setMessage(result.replayed ? 'Existing brief replayed from the archive.' : 'Market brief generated and added to the archive.')
    } catch (error: unknown) {
      const status = (error as { response?: { status?: number } }).response?.status
      setMessage(status === 503 ? 'Brief generation is unavailable. Ask your local operator to enable the required server-side configuration.' : 'Brief generation failed. No market data was saved.')
    } finally {
      setGenerating(false)
    }
  }
  return <main aria-labelledby="market-brief-title" className="print:mx-0">
    <h1 id="market-brief-title">Market intelligence briefs</h1>
    {message && <p role="status">{message}</p>}
    <section aria-labelledby="market-brief-archive-title">
      <div className="flex flex-wrap items-center gap-3"><h2 id="market-brief-archive-title">Archive</h2><button type="button" onClick={generate} disabled={generating} aria-describedby="market-brief-generation-help">{generating ? 'Generating brief…' : 'Generate brief'}</button></div>
      <p id="market-brief-generation-help">Generates a review-only brief from your server-side portfolio and approved provider configuration.</p>
      {items.length === 0 && !message.startsWith('Loading') ? <div role="status"><p>No market briefs exist yet.</p><p>Generate a brief when your local operator has enabled the required server-side flags and provider configuration.</p></div> : <nav aria-label="Brief archive"><ul>{items.map(item => <li key={item.brief_id}><button onClick={() => open(item.brief_id)}>Brief for {item.report_window} ({item.generated_at})</button></li>)}</ul></nav>}
    </section>
    {brief && <article aria-label="Brief detail">
      <p>As of {brief.generated_at}</p>
      {brief.sections.map(section => <section key={section.name} aria-labelledby={`brief-${section.name}`}><h2 id={`brief-${section.name}`}>{section.name.replaceAll('_', ' ')}</h2><ul>{section.content.map((text, index) => <li key={`${text}-${index}`}>{text}</li>)}</ul>{section.citations.map(citation => <p key={citation.source_url}><a href={citation.source_url}>Source: {citation.provider}</a> <span>({citation.freshness})</span></p>)}</section>)}
      {brief.warnings.length > 0 && <aside aria-label="Data quality warnings"><h2>Data quality</h2><ul>{brief.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul></aside>}
      {(brief.actions ?? []).length > 0 && <section aria-labelledby="actions-to-review"><h2 id="actions-to-review">Actions to review</h2>{brief.actions?.map(action => <article key={action.action}><h3>{action.action}</h3><p>{action.why}</p><dl><dt>Goal linkage</dt><dd>{action.goal_linkage}</dd><dt>Expected impact</dt><dd>{action.expected_impact}</dd><dt>Confidence</dt><dd>{action.confidence}</dd><dt>Approval</dt><dd>{action.approval_requirement}</dd></dl><p>Evidence: {action.evidence.join(', ') || 'No comparable position data.'}</p><p>Risks: {action.risks.join(', ')}</p><p>Alternatives: {action.alternatives.join(', ')}</p></article>)}</section>}
    </article>}
  </main>
}
