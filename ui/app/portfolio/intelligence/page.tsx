'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, ArrowLeft, ChevronDown, Database, ExternalLink, Filter, RefreshCw, ShieldCheck, Wallet } from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import { rulesService, type Account, type DashboardSummary, type Holding } from '@/lib/api'
import { classifyErrorMessage } from '@/lib/errors'

type SortKey = 'value' | 'symbol' | 'account'

function money(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return 'Unavailable'
  return value.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })
}

function quality(holding: Holding) {
  if (!holding.symbol || holding.current_value == null || holding.last_price == null) return 'Incomplete'
  return 'Observed'
}

function Skeleton() {
  return <div className="space-y-4" aria-busy="true" data-testid="portfolio-intelligence-loading"><div className="h-24 animate-pulse rounded-lg bg-[var(--surface-ambient)]" /><div className="h-80 animate-pulse rounded-lg bg-[var(--surface-ambient)]" /></div>
}

export default function PortfolioIntelligencePage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [accountFilter, setAccountFilter] = useState('all')
  const [sort, setSort] = useState<SortKey>('value')
  const [selected, setSelected] = useState<Holding | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [nextSummary, nextAccounts, nextHoldings] = await Promise.all([rulesService.getDashboardSummary(), rulesService.listAccounts(), rulesService.listHoldings()])
      setSummary(nextSummary)
      setAccounts(nextAccounts)
      setHoldings(nextHoldings)
    } catch (cause) {
      setError(classifyErrorMessage(cause))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const accountNames = useMemo(() => new Map(accounts.map((account) => [account.id, account.account_name])), [accounts])
  const filtered = useMemo(() => holdings.filter((holding) => {
    const text = `${holding.symbol ?? ''} ${holding.description ?? ''}`.toLowerCase()
    return (accountFilter === 'all' || String(holding.account_id) === accountFilter) && text.includes(query.toLowerCase())
  }).sort((a, b) => {
    if (sort === 'symbol') return (a.symbol ?? '').localeCompare(b.symbol ?? '')
    if (sort === 'account') return (accountNames.get(a.account_id) ?? '').localeCompare(accountNames.get(b.account_id) ?? '')
    return (b.current_value ?? -Infinity) - (a.current_value ?? -Infinity)
  }), [accountFilter, accountNames, holdings, query, sort])

  const totalValue = summary?.total_balance ?? holdings.reduce((total, holding) => total + (holding.current_value ?? 0), 0)
  const priced = holdings.filter((holding) => holding.current_value != null && holding.last_price != null && holding.symbol)
  const largest = priced.reduce<Holding | null>((current, holding) => !current || (holding.current_value ?? 0) > (current.current_value ?? 0) ? holding : current, null)
  const coverage = holdings.length ? Math.round((priced.length / holdings.length) * 100) : null

  return <PageLayout>
    <PageHeader eyebrow="Portfolio intelligence" title="Portfolio workspace" description="Understand holdings, exposure, concentration, and data quality from the canonical portfolio view." actions={<div className="flex gap-2"><Link href="/portfolio" className="inline-flex min-h-11 items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 text-sm font-medium text-secondary hover:bg-[var(--surface-ambient)]"><ArrowLeft className="h-4 w-4" aria-hidden="true" />Portfolio</Link><button type="button" onClick={() => void load()} className="inline-flex min-h-11 items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 text-sm font-medium text-secondary hover:bg-[var(--surface-ambient)]"><RefreshCw className="h-4 w-4" aria-hidden="true" />Refresh</button></div>} className="mb-4" />

    {loading ? <Skeleton /> : error ? <section className="card p-6" role="alert"><div className="flex items-start gap-3"><AlertTriangle className="h-5 w-5 text-[var(--warning-600)]" aria-hidden="true" /><div><h2 className="font-semibold text-primary">Portfolio data unavailable</h2><p className="mt-2 text-sm text-secondary">{error}</p><button type="button" onClick={() => void load()} className="btn-secondary mt-4 min-h-11 px-3 text-sm">Retry</button></div></div></section> : <>
      <section className="surface-focal card p-4" aria-label="Portfolio context"><div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm"><span className="inline-flex items-center gap-2 font-medium text-primary"><Wallet className="h-4 w-4 text-[var(--accent-primary)]" aria-hidden="true" />All portfolio accounts</span><span className="text-secondary">As of <strong className="text-primary">{summary?.last_sync ? new Date(summary.last_sync).toLocaleString() : 'Unavailable'}</strong></span><span className="text-secondary">Server-owned holdings</span></div></section>
      <section className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Portfolio KPIs"><div className="card p-4"><p className="text-xs text-tertiary">Portfolio value</p><p className="mt-2 font-mono text-xl font-semibold text-primary">{money(totalValue)}</p></div><div className="card p-4"><p className="text-xs text-tertiary">Positions</p><p className="mt-2 font-mono text-xl font-semibold text-primary">{holdings.length}</p></div><div className="card p-4"><p className="text-xs text-tertiary">Largest position</p><p className="mt-2 font-mono text-xl font-semibold text-primary">{largest?.symbol ?? 'Unavailable'}</p><p className="mt-1 text-xs text-secondary">{largest ? money(largest.current_value) : 'No priced position'}</p></div><div className="card p-4"><p className="text-xs text-tertiary">Price coverage</p><p className="mt-2 font-mono text-xl font-semibold text-primary">{coverage == null ? 'Unavailable' : `${coverage}%`}</p><p className="mt-1 text-xs text-secondary">Observed market values</p></div></section>
      <section className="mt-4 grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
        <article className="card p-4"><div className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-[var(--accent-primary)]" aria-hidden="true" /><h2 className="font-semibold text-primary">Concentration view</h2></div><p className="mt-1 text-sm text-secondary">Ranked holdings show where portfolio value is concentrated. This is an observed allocation view, not an automatic recommendation.</p><div className="mt-4 space-y-3">{priced.slice().sort((a, b) => (b.current_value ?? 0) - (a.current_value ?? 0)).slice(0, 5).map((holding) => <div key={holding.id} className="flex items-center justify-between gap-3 text-sm"><span className="font-medium text-primary">{holding.symbol}</span><span className="font-mono text-secondary">{money(holding.current_value)}</span></div>)}{priced.length === 0 && <p className="py-4 text-sm text-secondary">No observed positions are available for concentration analysis.</p>}</div></article>
        <article className="card overflow-hidden"><div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border-subtle)] p-4"><div><h2 className="font-semibold text-primary">Positions</h2><p className="mt-1 text-sm text-secondary">Select a position for its canonical context.</p></div><div className="flex flex-wrap gap-2"><label className="sr-only" htmlFor="holding-search">Search holdings</label><input id="holding-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search symbol" className="min-h-11 w-32 rounded-md border border-[var(--border-subtle)] bg-transparent px-3 text-sm text-primary outline-none focus:border-[var(--accent-primary)]" /><label className="sr-only" htmlFor="account-filter">Filter account</label><select id="account-filter" value={accountFilter} onChange={(event) => setAccountFilter(event.target.value)} className="min-h-11 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-raised)] px-2 text-sm text-primary outline-none focus:border-[var(--accent-primary)]"><option value="all">All accounts</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.account_name}</option>)}</select><label className="sr-only" htmlFor="holding-sort">Sort holdings</label><select id="holding-sort" value={sort} onChange={(event) => setSort(event.target.value as SortKey)} className="min-h-11 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-raised)] px-2 text-sm text-primary outline-none focus:border-[var(--accent-primary)]"><option value="value">Sort value</option><option value="symbol">Sort symbol</option><option value="account">Sort account</option></select></div></div><div className="overflow-x-auto"><table className="w-full min-w-[700px] text-left text-sm"><caption className="sr-only">Canonical portfolio holdings</caption><thead className="sticky top-0 bg-[var(--surface-raised)] text-xs text-tertiary"><tr><th scope="col" className="px-4 py-3 font-medium">Security</th><th scope="col" className="px-4 py-3 font-medium">Account</th><th scope="col" className="px-4 py-3 text-right font-medium">Quantity</th><th scope="col" className="px-4 py-3 text-right font-medium">Market value</th><th scope="col" className="px-4 py-3 font-medium">Data quality</th><th scope="col" className="px-4 py-3 font-medium">Inspect</th></tr></thead><tbody className="divide-y divide-[var(--border-subtle)]">{filtered.map((holding) => <tr key={holding.id} className="hover:bg-[var(--surface-ambient)]"><td className="px-4 py-3"><button type="button" onClick={() => setSelected(holding)} className="min-h-11 text-left font-semibold text-[var(--accent-primary)] focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]">{holding.symbol ?? 'Unresolved security'}</button><p className="text-xs text-tertiary">{holding.type ?? 'Type unavailable'}</p></td><td className="px-4 py-3 text-secondary">{accountNames.get(holding.account_id) ?? 'Account unavailable'}</td><td className="px-4 py-3 text-right font-mono text-secondary">{holding.quantity ?? 'Unavailable'}</td><td className="px-4 py-3 text-right font-mono text-primary">{money(holding.current_value)}</td><td className="px-4 py-3"><span className="rounded-full bg-[var(--surface-ambient)] px-2 py-1 text-xs text-secondary">{quality(holding)}</span></td><td className="px-4 py-3"><button type="button" onClick={() => setSelected(holding)} aria-label={`Inspect ${holding.symbol ?? 'unresolved security'}`} className="min-h-11 rounded-md px-2 text-secondary hover:bg-[var(--surface-ambient)]"><ChevronDown className="h-4 w-4" aria-hidden="true" /></button></td></tr>)}</tbody></table>{filtered.length === 0 && <p className="p-6 text-sm text-secondary">No holdings match the current filters.</p>}</div></article>
      </section>
      <section className="mt-4 card p-4"><div className="flex items-center gap-2"><Database className="h-4 w-4 text-[var(--accent-primary)]" aria-hidden="true" /><h2 className="font-semibold text-primary">Data quality</h2></div><p className="mt-2 text-sm leading-6 text-secondary">{holdings.length - priced.length} of {holdings.length} position{holdings.length === 1 ? '' : 's'} have incomplete market-value coverage. Unknown values remain unknown and are not treated as zero.</p></section>
    </>}
    {selected && <div className="fixed inset-0 z-[70] flex items-end justify-center bg-black/30 p-0 sm:items-center sm:p-6" role="presentation" onClick={() => setSelected(null)}><section role="dialog" aria-modal="true" aria-labelledby="position-detail-title" onClick={(event) => event.stopPropagation()} className="w-full max-w-lg rounded-t-xl bg-[var(--surface-raised)] p-5 shadow-xl sm:rounded-xl"><div className="flex items-start justify-between gap-3"><div><h2 id="position-detail-title" className="text-lg font-semibold text-primary">{selected.symbol ?? 'Unresolved security'}</h2><p className="mt-1 text-sm text-secondary">Canonical position context</p></div><button type="button" onClick={() => setSelected(null)} className="min-h-11 rounded-md px-3 text-sm text-secondary hover:bg-[var(--surface-ambient)]">Close</button></div><dl className="mt-4 grid grid-cols-2 gap-4 text-sm"><div><dt className="text-tertiary">Quantity</dt><dd className="mt-1 font-mono text-primary">{selected.quantity ?? 'Unavailable'}</dd></div><div><dt className="text-tertiary">Market value</dt><dd className="mt-1 font-mono text-primary">{money(selected.current_value)}</dd></div><div><dt className="text-tertiary">Account</dt><dd className="mt-1 text-primary">{accountNames.get(selected.account_id) ?? 'Unavailable'}</dd></div><div><dt className="text-tertiary">Data quality</dt><dd className="mt-1 text-primary">{quality(selected)}</dd></div></dl><Link href="/market-intelligence" className="mt-5 inline-flex min-h-11 items-center gap-2 text-sm font-medium text-[var(--accent-primary)]">View market intelligence <ExternalLink className="h-4 w-4" aria-hidden="true" /></Link></section></div>}
  </PageLayout>
}
