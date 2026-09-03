'use client'

import { useEffect } from 'react'
import Link from 'next/link'
import { ArrowRight, BookOpen, CircleAlert, Database, Search, ShieldCheck } from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'

const surfaces = [
  {
    title: 'Daily Investment Brief',
    description: 'A structured, point-in-time review of portfolio, market, committee, and recommendation context.',
    href: '/investments/brief',
    icon: BookOpen,
    status: 'Available',
  },
  {
    title: 'Portfolio intelligence',
    description: 'Open the canonical holdings and exposure view without duplicating portfolio calculations.',
    href: '/portfolio',
    icon: Database,
    status: 'Available',
  },
  {
    title: 'Research workspace',
    description: 'Review normalized market intelligence while deeper security research surfaces are assembled.',
    href: '/market-intelligence',
    icon: Search,
    status: 'Available',
  },
  {
    title: 'Recommendation review',
    description: 'Review canonical recommendations, bounded evidence, and record a human decision without execution.',
    href: '/investments/recommendations',
    icon: ShieldCheck,
    status: 'Available',
  },
  {
    title: 'Opportunity discovery',
    description: 'Explore separate portfolio and bounded S&P 500 universes with explicit freshness and provenance.',
    href: '/investments/discovery',
    icon: Search,
    status: 'Available',
  },
  {
    title: 'Risk and scenario views',
    description: 'Review current-only portfolio coverage and bounded hypothetical value changes without mutation.',
    href: '/investments/risk',
    icon: ShieldCheck,
    status: 'Available',
  },
]

export default function InvestmentsPage() {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes((event.target as HTMLElement)?.tagName ?? '')) {
        event.preventDefault()
        document.getElementById('investment-surface-search')?.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <PageLayout>
      <PageHeader
        eyebrow="Investment intelligence"
        title="Command Center"
        description="A focused entry point for Atlas investment analysis. Every surface remains read-only, evidence-first, and explicitly as-of."
        actions={<span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-working)] px-3 py-1.5 text-xs font-medium text-secondary">UI-02 · route contract</span>}
        className="mb-6"
      />

      <section className="surface-focal card p-5 sm:p-6" aria-labelledby="command-center-heading">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <div className="flex items-center gap-2 text-[var(--accent-primary)]">
              <ShieldCheck className="h-5 w-5" aria-hidden="true" />
              <span className="text-sm font-semibold">Human-controlled analysis</span>
            </div>
            <h2 id="command-center-heading" className="mt-3 text-2xl font-semibold tracking-tight text-primary sm:text-3xl">Start with the signal, then follow the evidence.</h2>
            <p className="mt-3 max-w-xl text-sm leading-6 text-secondary">This workspace establishes the investment navigation boundary. It does not invent prices, recommendations, outcomes, or portfolio state.</p>
          </div>
          <label className="flex w-full max-w-sm items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-working)] px-3 py-2.5 focus-within:border-[var(--accent-primary)] focus-within:ring-2 focus-within:ring-[var(--accent-selection)]">
            <Search className="h-4 w-4 shrink-0 text-tertiary" aria-hidden="true" />
            <span className="sr-only">Find an investment surface</span>
            <input id="investment-surface-search" type="search" placeholder="Find a surface…" className="min-w-0 flex-1 bg-transparent text-sm text-primary outline-none placeholder:text-tertiary" />
            <kbd className="hidden rounded border border-[var(--border-subtle)] px-1.5 py-0.5 font-mono text-[11px] text-tertiary sm:inline">/</kbd>
          </label>
        </div>
      </section>

      <section className="mt-6" aria-labelledby="surfaces-heading">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div><h2 id="surfaces-heading" className="text-lg font-semibold text-primary">Investment surfaces</h2><p className="mt-1 text-sm text-secondary">Choose a canonical Atlas view. Availability is explicit.</p></div>
          <span className="hidden text-xs text-tertiary sm:inline">Tab to navigate · Enter to open</span>
        </div>
        <div className="grid gap-3 lg:grid-cols-3">
          {surfaces.map(({ title, description, href, icon: Icon, status }) => (
            <Link key={title} href={href} className="group card-interactive flex min-h-44 flex-col p-5" aria-label={`${title} — ${status}`}>
              <div className="flex items-start justify-between gap-3"><span className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-ambient)] text-[var(--accent-primary)]"><Icon className="h-4 w-4" aria-hidden="true" /></span><span className={`rounded-full px-2 py-1 text-[11px] font-medium ${status === 'Available' ? 'bg-[var(--success-50)] text-[var(--success-700)]' : 'bg-[var(--warning-50)] text-[var(--warning-700)]'}`}>{status}</span></div>
              <div className="mt-auto pt-8"><h3 className="font-semibold text-primary">{title}</h3><p className="mt-1 text-sm leading-5 text-secondary">{description}</p><span className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-[var(--accent-primary)]">Open surface <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden="true" /></span></div>
            </Link>
          ))}
        </div>
      </section>

      <section className="mt-6 grid gap-3 md:grid-cols-2" aria-label="Investment workspace boundaries">
        <div className="card p-5"><div className="flex items-center gap-2"><CircleAlert className="h-4 w-4 text-[var(--warning-600)]" aria-hidden="true" /><h2 className="font-semibold text-primary">Evidence and freshness stay visible</h2></div><p className="mt-2 text-sm leading-6 text-secondary">Future investment views will show source, as-of, known-at, and data-quality context rather than presenting historical information as live.</p></div>
        <div className="card p-5"><div className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-[var(--success-600)]" aria-hidden="true" /><h2 className="font-semibold text-primary">No execution actions</h2></div><p className="mt-2 text-sm leading-6 text-secondary">Atlas can analyze and report. Decisions remain human-owned; this route contains no trading, broker, order, or rebalance workflow.</p></div>
      </section>
    </PageLayout>
  )
}
