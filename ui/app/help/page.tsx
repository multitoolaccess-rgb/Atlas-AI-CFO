'use client'

import { useState } from 'react'
import { ChevronDown, ChevronRight, HelpCircle, BookOpen, ArrowRight } from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'

const FAQ = [
  {
    q: 'Where should I start?',
    a: 'Mission Control is the cross-domain starting point. Use Money for cash flow and planning, Wealth for balances and portfolios, Intelligence for decisions, market evidence, and scenarios, and System for data connections, preferences, and help.',
  },
  {
    q: 'How do I add source data?',
    a: 'Open Data Connections. Accounts lets you add or review account records; Imports accepts supported CSV, Excel, PDF, OFX, and QFX statement files. Atlas shows an honest empty, partial, stale, or unavailable state when a source does not provide enough evidence.',
  },
  {
    q: 'What does a recommendation or scenario mean?',
    a: 'A recommendation is review-only guidance linked to its available evidence, assumptions, risks, and confidence. Accepting a decision does not execute it or prove that it succeeded. Scenario Lab is bounded what-if analysis and does not make probability, tax, optimization, or execution claims.',
  },
  {
    q: 'Why is market information unavailable or stale?',
    a: 'Market Intelligence fails closed when provider readiness, freshness, mapping, citations, or privacy requirements are not satisfied. Use the recovery guidance on the page and try again later; Atlas does not fabricate quotes, filings, earnings, news, or citations.',
  },
  {
    q: 'How do appearance and profiles work?',
    a: 'Settings controls Light, Dark, or System mode and the Indigo Intelligence, Vermilion Energy, or Ion Future accent profile. Profiles change presentation only; gains, losses, warnings, and critical states retain their financial meaning.',
  },
  {
    q: 'What are Atlas data limitations?',
    a: 'Atlas is a personal, pre-production application. Source coverage, currency authority, provider availability, and historical completeness can be limited. Review the source, freshness, and limitation labels before relying on any summary; missing evidence is not treated as zero.',
  },
]

const DESTINATIONS = [
  ['Mission Control', '/', 'Priority signals and next actions'],
  ['Money', '/cash-flow', 'Cash flow and planning'],
  ['Wealth', '/wealth', 'Balance sheet, assets, debts, and universe'],
  ['Intelligence', '/decisions', 'Decisions, market context, and scenarios'],
  ['System', '/data-connections', 'Connections, settings, and support'],
] as const

export default function HelpPage() {
  const [openIndex, setOpenIndex] = useState<number | null>(0)

  return (
    <PageLayout>
      <PageHeader
        eyebrow="System"
        title="Help"
        description="A concise guide to Atlas navigation, source evidence, limitations, and recovery."
        className="mb-6"
      />

      <section className="card p-6 mb-6" aria-labelledby="help-navigation-title" data-testid="help-navigation">
        <div className="flex items-center gap-2 mb-4">
          <ArrowRight className="w-5 h-5 text-primary" aria-hidden="true" />
          <h2 id="help-navigation-title" className="headline-md text-primary">Atlas structure</h2>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5">
          {DESTINATIONS.map(([label, href, description]) => (
            <a key={href} href={href} className="rounded-[var(--radius-md)] border border-[var(--border-subtle)] p-4 hover:border-accent-border hover:bg-surface-selected focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-focus">
              <span className="block text-sm font-semibold text-primary">{label}</span>
              <span className="mt-1 block text-xs leading-relaxed text-secondary">{description}</span>
            </a>
          ))}
        </div>
      </section>

      <section className="card p-6 mb-6" data-testid="help-faq" aria-labelledby="help-faq-title">
        <div className="flex items-center gap-2 mb-4">
          <BookOpen className="w-5 h-5 text-primary" aria-hidden="true" />
          <h2 id="help-faq-title" className="headline-md text-primary">Frequently asked questions</h2>
        </div>
        <ul className="space-y-2">
          {FAQ.map((item, i) => {
            const open = openIndex === i
            return (
              <li key={item.q} className="border-b border-outline-variant/20 last:border-b-0">
                <button
                  type="button"
                  onClick={() => setOpenIndex(open ? null : i)}
                  className="w-full flex items-center justify-between gap-4 py-3 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                  aria-expanded={open}
                  aria-controls={`faq-panel-${i}`}
                  id={`help-question-${i}`}
                >
                  <span className="body-md font-semibold text-primary">{item.q}</span>
                  {open ? <ChevronDown className="w-4 h-4 text-on-surface-variant shrink-0" aria-hidden="true" /> : <ChevronRight className="w-4 h-4 text-on-surface-variant shrink-0" aria-hidden="true" />}
                </button>
                <div id={`faq-panel-${i}`} role="region" aria-labelledby={`help-question-${i}`} hidden={!open}>
                  <p className="body-md text-secondary pb-3">{item.a}</p>
                </div>
              </li>
            )
          })}
        </ul>
      </section>

      <section className="card p-6" aria-labelledby="help-recovery-title">
        <div className="flex items-center gap-2 mb-2">
          <HelpCircle className="w-5 h-5 text-primary" aria-hidden="true" />
          <h2 id="help-recovery-title" className="headline-md text-primary">Recovery and privacy</h2>
        </div>
        <p className="body-md text-secondary">If a service is unavailable, use the page&apos;s Retry action, confirm the source or provider status, and return when the source is ready. Never paste credentials, raw account numbers, or sensitive evidence into support requests.</p>
        <p className="body-md text-secondary mt-3">Default-off capabilities remain off until their documented server-owned conditions are met. Scout is available from the global header and <a className="text-accent-primary hover:underline" href="/assistant">the fallback route</a>; it does not gain financial execution authority.</p>
      </section>
    </PageLayout>
  )
}
