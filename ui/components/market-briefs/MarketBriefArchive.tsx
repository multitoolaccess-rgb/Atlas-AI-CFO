'use client'

import { useEffect, useRef, useState } from 'react'
import { getMarketBrief, listMarketBriefs, type BriefIndex, type MarketBrief } from '@/lib/marketBriefs'

export default function MarketBriefArchive() {
  const [items, setItems] = useState<BriefIndex[]>([])
  const [brief, setBrief] = useState<MarketBrief | null>(null)
  const [message, setMessage] = useState('Loading brief archive…')
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
  return <main aria-labelledby="market-brief-title" className="print:mx-0">
    <h1 id="market-brief-title">Market intelligence briefs</h1>
    {message && <p role="status">{message}</p>}
    <nav aria-label="Brief archive"><ul>{items.map(item => <li key={item.brief_id}><button onClick={() => open(item.brief_id)}>Brief for {item.report_window}</button></li>)}</ul></nav>
    {brief && <article aria-label="Brief detail">
      <p>As of {brief.generated_at}</p>
      {brief.sections.map(section => <section key={section.name} aria-labelledby={`brief-${section.name}`}><h2 id={`brief-${section.name}`}>{section.name.replaceAll('_', ' ')}</h2><ul>{section.content.map((text, index) => <li key={`${text}-${index}`}>{text}</li>)}</ul>{section.citations.map(citation => <p key={citation.source_url}><a href={citation.source_url}>Source: {citation.provider}</a> <span>({citation.freshness})</span></p>)}</section>)}
      {brief.warnings.length > 0 && <aside aria-label="Data quality warnings"><h2>Data quality</h2><ul>{brief.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul></aside>}
    </article>}
  </main>
}
