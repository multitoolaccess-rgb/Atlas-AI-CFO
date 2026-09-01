'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, ArrowLeft, BarChart3, BookOpen, Database, ExternalLink, LineChart, RefreshCw, ShieldCheck, Wallet } from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'
import PageHeader from '@/components/ui/PageHeader'
import { rulesService, type Account, type Holding } from '@/lib/api'
import { classifyErrorMessage } from '@/lib/errors'

function money(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return 'Unavailable'
  return value.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })
}

function dateTime(value: string | null | undefined) {
  if (!value) return 'Unavailable'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

function UnavailableLens({ title, detail }: { title: string; detail: string }) {
  return <section className="card border-dashed p-4" aria-labelledby={`${title}-title`}><div className="flex items-start gap-3"><Database className="mt-0.5 h-4 w-4 shrink-0 text-[var(--accent-primary)]" aria-hidden="true" /><div><h2 id={`${title}-title`} className="font-semibold text-primary">{title}</h2><p className="mt-1 text-sm leading-6 text-secondary">{detail}</p><p className="mt-2 text-xs text-tertiary">Unavailable from the current canonical read model.</p></div></div></section>
}

export default function SecurityResearchPage({ params }: { params: { securityId: string } }) {
  const requestedId = decodeURIComponent(params.securityId)
  const symbol = requestedId.match(/^sec:[^-]+-(.+)$/i)?.[1]?.toUpperCase() ?? requestedId.replace(/^sec:/i, '').toUpperCase()
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [analyst, setAnalyst] = useState<Awaited<ReturnType<typeof rulesService.getAnalystRatings>> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [analystError, setAnalystError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setAnalystError(null)
    try {
      const [nextHoldings, nextAccounts] = await Promise.all([rulesService.listHoldings(), rulesService.listAccounts()])
      setHoldings(nextHoldings)
      setAccounts(nextAccounts)
      try {
        setAnalyst(await rulesService.getAnalystRatings(symbol))
      } catch (cause) {
        setAnalyst(null)
        setAnalystError(classifyErrorMessage(cause))
      }
    } catch (cause) {
      setError(classifyErrorMessage(cause))
    } finally {
      setLoading(false)
    }
  }, [symbol])

  useEffect(() => { void load() }, [load])

  const positions = useMemo(() => holdings.filter((holding) => holding.symbol?.toUpperCase() === symbol), [holdings, symbol])
  const accountNames = useMemo(() => new Map(accounts.map((account) => [account.id, account.account_name])), [accounts])
  const totalValue = positions.reduce((sum, position) => sum + (position.live_value ?? position.current_value ?? 0), 0)
  const latest = positions.find((position) => position.live_price != null) ?? positions.find((position) => position.last_price != null) ?? positions[0]
  const latestAccountSync = latest ? accounts.find((account) => account.id === latest.account_id)?.last_sync : null
  const portfolioTotal = holdings.reduce((sum, holding) => sum + (holding.live_value ?? holding.current_value ?? 0), 0)
  const weight = positions.length > 0 && portfolioTotal > 0 ? `${((totalValue / portfolioTotal) * 100).toFixed(2)}%` : 'Unavailable'

  return <PageLayout>
    <PageHeader eyebrow="Security research" title={symbol || 'Security'} description="A read-only research context assembled from Atlas-owned data." actions={<div className="flex gap-2"><Link href="/portfolio/intelligence" className="inline-flex min-h-11 items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 text-sm font-medium text-secondary hover:bg-[var(--surface-ambient)]"><ArrowLeft className="h-4 w-4" aria-hidden="true" />Portfolio intelligence</Link><button type="button" onClick={() => void load()} className="inline-flex min-h-11 items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 text-sm font-medium text-secondary hover:bg-[var(--surface-ambient)]"><RefreshCw className="h-4 w-4" aria-hidden="true" />Refresh</button></div>} className="mb-4" />
    {loading ? <div className="space-y-4" aria-busy="true" role="status"><span className="sr-only">Loading security research</span><div className="h-28 animate-pulse rounded-lg bg-[var(--surface-ambient)]" /><div className="h-48 animate-pulse rounded-lg bg-[var(--surface-ambient)]" /></div> : error ? <section className="card p-6" role="alert"><div className="flex items-start gap-3"><AlertTriangle className="h-5 w-5 text-[var(--warning-600)]" aria-hidden="true" /><div><h2 className="font-semibold text-primary">Security research unavailable</h2><p className="mt-2 text-sm text-secondary">{error}</p><button type="button" onClick={() => void load()} className="btn-secondary mt-4 min-h-11 px-3 text-sm">Retry</button></div></div></section> : <>
      <section className="surface-focal card p-4" aria-label="Security identity"><div className="flex flex-wrap items-start gap-x-8 gap-y-4"><div><p className="text-xs text-tertiary">Canonical security reference</p><p className="mt-1 font-mono text-sm text-primary">{requestedId || 'Unavailable'}</p></div><div><p className="text-xs text-tertiary">Ticker alias</p><p className="mt-1 font-mono text-lg font-semibold text-primary">{symbol || 'Unavailable'}</p></div><div><p className="text-xs text-tertiary">Research as of</p><p className="mt-1 text-sm text-primary">{dateTime(latestAccountSync)}</p></div><div><p className="text-xs text-tertiary">Data state</p><p className="mt-1 text-sm font-medium text-secondary">{latest ? 'Observed holding context' : 'Not currently held'}</p></div></div></section>
      <section className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Security snapshot"><div className="card p-4"><p className="text-xs text-tertiary">Most recent price</p><p className="mt-2 font-mono text-xl font-semibold text-primary">{money(latest?.live_price ?? latest?.last_price)}</p><p className="mt-1 text-xs text-secondary">Server-owned holding data</p></div><div className="card p-4"><p className="text-xs text-tertiary">Portfolio value</p><p className="mt-2 font-mono text-xl font-semibold text-primary">{positions.length ? money(totalValue) : 'Not held'}</p><p className="mt-1 text-xs text-secondary">Across matching positions</p></div><div className="card p-4"><p className="text-xs text-tertiary">Portfolio weight</p><p className="mt-2 font-mono text-xl font-semibold text-primary">{weight}</p><p className="mt-1 text-xs text-secondary">Observed holding value</p></div><div className="card p-4"><p className="text-xs text-tertiary">Instrument type</p><p className="mt-2 text-xl font-semibold text-primary">{latest?.type ?? 'Unavailable'}</p><p className="mt-1 text-xs text-secondary">Canonical holding label</p></div></section>
      <section className="mt-4 grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
        <article className="card overflow-hidden"><div className="border-b border-[var(--border-subtle)] p-4"><div className="flex items-center gap-2"><Wallet className="h-4 w-4 text-[var(--accent-primary)]" aria-hidden="true" /><h2 className="font-semibold text-primary">Portfolio context</h2></div><p className="mt-1 text-sm text-secondary">Position-level context remains separate from public research.</p></div>{positions.length ? <div className="overflow-x-auto"><table className="w-full min-w-[560px] text-left text-sm"><caption className="sr-only">Portfolio positions for {symbol}</caption><thead className="bg-[var(--surface-ambient)] text-xs text-tertiary"><tr><th scope="col" className="px-4 py-3 font-medium">Account</th><th scope="col" className="px-4 py-3 text-right font-medium">Quantity</th><th scope="col" className="px-4 py-3 text-right font-medium">Value</th><th scope="col" className="px-4 py-3 font-medium">Quality</th></tr></thead><tbody className="divide-y divide-[var(--border-subtle)]">{positions.map((position) => <tr key={position.id}><td className="px-4 py-3 text-primary">{accountNames.get(position.account_id) ?? 'Account unavailable'}</td><td className="px-4 py-3 text-right font-mono text-secondary">{position.quantity ?? 'Unavailable'}</td><td className="px-4 py-3 text-right font-mono text-primary">{money(position.live_value ?? position.current_value)}</td><td className="px-4 py-3 text-secondary">{position.last_price == null ? 'Incomplete' : 'Observed'}</td></tr>)}</tbody></table></div> : <div className="p-5 text-sm text-secondary">Not currently held. Portfolio-specific fields are intentionally unavailable.</div>}</article>
        <article className="card p-4"><div className="flex items-center gap-2"><BarChart3 className="h-4 w-4 text-[var(--accent-primary)]" aria-hidden="true" /><h2 className="font-semibold text-primary">Analyst context</h2></div>{analystError ? <p className="mt-3 text-sm text-secondary">Analyst coverage unavailable. {analystError}</p> : analyst ? <div className="mt-4 space-y-3 text-sm"><div className="flex justify-between gap-3"><span className="text-secondary">Latest period</span><span className="font-mono text-primary">{analyst.recommendation_trends[0]?.period ?? 'Unavailable'}</span></div><div className="flex justify-between gap-3"><span className="text-secondary">Buy consensus</span><span className="font-mono text-primary">{analyst.recommendation_trends[0] ? analyst.recommendation_trends[0].strongBuy + analyst.recommendation_trends[0].buy : 'Unavailable'}</span></div><div className="flex justify-between gap-3"><span className="text-secondary">Hold consensus</span><span className="font-mono text-primary">{analyst.recommendation_trends[0]?.hold ?? 'Unavailable'}</span></div><div className="flex justify-between gap-3"><span className="text-secondary">Sell consensus</span><span className="font-mono text-primary">{analyst.recommendation_trends[0] ? analyst.recommendation_trends[0].sell + analyst.recommendation_trends[0].strongSell : 'Unavailable'}</span></div>{analyst.price_target && <div className="border-t border-[var(--border-subtle)] pt-3"><span className="text-secondary">Mean price target</span><p className="mt-1 font-mono text-lg text-primary">{money(analyst.price_target.targetMean)}</p></div>}</div> : <p className="mt-3 text-sm text-secondary">Analyst context is unavailable for this security.</p>}</article>
      </section>
      <section className="mt-4 grid gap-4 md:grid-cols-2"><UnavailableLens title="Fundamental research" detail="Revenue, profitability, balance-sheet facts, periods, and as-known-at timestamps require the INV-04 security projection." /><UnavailableLens title="Technical research" detail="Canonical SMA, RSI, volatility, adjustment basis, and history state require the INV-05 projection." /><UnavailableLens title="Quant research" detail="Returns, drawdown, Sharpe, beta, benchmark identity, and methodology require the INV-07 projection." /><UnavailableLens title="Macro and committee context" detail="Security-linked macro observations and committee findings are not exposed by the current frontend read model." /></section>
      <section className="mt-4 card p-4"><div className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-[var(--accent-primary)]" aria-hidden="true" /><h2 className="font-semibold text-primary">Research trust boundary</h2></div><p className="mt-2 text-sm leading-6 text-secondary">This workspace renders server-owned observations and clearly marks unavailable research. It does not calculate indicators, create a recommendation, infer a score, or change portfolio state.</p><div className="mt-3 flex flex-wrap gap-3"><Link href="/investments/brief" className="inline-flex min-h-11 items-center gap-2 text-sm font-medium text-[var(--accent-primary)]">Open Daily Brief <ExternalLink className="h-4 w-4" aria-hidden="true" /></Link><Link href="/market-intelligence" className="inline-flex min-h-11 items-center gap-2 text-sm font-medium text-[var(--accent-primary)]">Open Market Intelligence <LineChart className="h-4 w-4" aria-hidden="true" /></Link></div></section>
    </>}
  </PageLayout>
}
