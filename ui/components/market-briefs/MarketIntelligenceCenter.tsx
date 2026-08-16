'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import {
  AlertTriangle,
  Archive,
  ArrowRight,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  FileText,
  Landmark,
  LineChart,
  Loader2,
  Newspaper,
  RefreshCw,
  Search,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  WifiOff,
  XCircle,
} from 'lucide-react'
import Button from '@/components/ui/Button'
import Badge from '@/components/ui/Badge'
import Card from '@/components/ui/Card'
import EmptyState from '@/components/ui/EmptyState'
import {
  classifyMarketBriefError,
  fetchMarketPulse,
  generateMarketBrief,
  getMarketBrief,
  listMarketBriefs,
  type BriefIndex,
  type BriefSection,
  type Citation,
  type CoverageSummary,
  type HoldingEvidence,
  type MarketBrief,
  type MarketBriefErrorState,
  type MarketBriefReasonCode,
  type MarketPulseSnapshot,
  type PriceBasis,
} from '@/lib/marketBriefs'

type TabId = 'portfolio' | 'pulse' | 'earnings' | 'scanner' | 'archive'

const TABS: ReadonlyArray<{ id: TabId; label: string; description: string }> = [
  { id: 'portfolio', label: 'My Portfolio', description: 'What changed, why it matters, and what deserves your attention.' },
  { id: 'pulse', label: 'Market Pulse', description: 'Index direction, market-wide headlines, and the bounded scanner.' },
  { id: 'earnings', label: 'Earnings & Events', description: 'Portfolio-linked earnings plus the market earnings calendar.' },
  { id: 'scanner', label: 'S&P 500 Scanner', description: 'Bounded, quota-aware scan of the S&P 500 universe.' },
  { id: 'archive', label: 'Archive', description: 'Immutable saved briefs for later review.' },
]

const SECTION_LABELS: Record<string, string> = {
  executive_summary: 'Executive summary',
  portfolio_changes: 'Portfolio changes',
  material_holding_news: 'Material portfolio news',
  earnings: 'Earnings',
  sec_filings: 'SEC filings',
  catalyst_stream: 'Catalyst stream',
  risks_and_opportunities: 'Risks and opportunities',
  actions_to_review: 'Actions to review',
  sources: 'Sources',
  data_quality: 'Data-quality limitations',
}

const MATERIALITY_LABELS: Record<HoldingEvidence['materiality'], string> = {
  high: 'High impact',
  watch: 'Watch',
  informational: 'Informational',
}

const MATERIALITY_VARIANTS: Record<HoldingEvidence['materiality'], 'danger' | 'warning' | 'info' | 'neutral'> = {
  high: 'danger',
  watch: 'warning',
  informational: 'info',
}

function formatDateTime(value: string | undefined) {
  if (!value) return 'Not available'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function formatDateOnly(value: string | undefined) {
  if (!value) return 'Not available'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date)
}

function basisLabel(basis: PriceBasis | undefined) {
  switch (basis) {
    case 'live': return 'Live quotes'
    case 'prior_close': return 'Prior close'
    case 'unusable': return 'Unusable basis'
    default: return 'Basis unavailable'
  }
}

function reasonLabel(reason: MarketBriefReasonCode) {
  return reason.replaceAll('_', ' ')
}

// Failure reasons that genuinely mean the market-data provider is down or
// misconfigured. Every other failure (coverage below threshold, unsupported
// symbols, stale quotes, currency ambiguity) means the provider responded but
// the portfolio could not be safely covered — the badge must say "Coverage
// limited", not "Provider unavailable".
const PROVIDER_FAILURE_REASONS: ReadonlySet<MarketBriefReasonCode> = new Set([
  'provider_configuration_missing',
  'provider_transport_failure',
  'provider_authentication_failed',
  'provider_rate_limited',
  'invalid_quote',
  'market_brief_generation_unavailable',
])

function isProviderFailureReason(code: MarketBriefReasonCode): boolean {
  return PROVIDER_FAILURE_REASONS.has(code)
}

function coveragePercent(coverage: CoverageSummary | null | undefined) {
  if (!coverage?.coverage_percentage) return 'Not calculated'
  const value = Number(coverage.coverage_percentage) * 100
  return Number.isFinite(value) ? `${Math.round(value)}%` : 'Not calculated'
}

function sectionByName(brief: MarketBrief | null, name: string): BriefSection | undefined {
  return brief?.sections.find(section => section.name === name)
}

function announcementTone(message: string) {
  return message.toLowerCase().includes('unavailable') || message.toLowerCase().includes('failed')
    ? 'border-danger-200 bg-danger-50 text-danger-800'
    : 'border-success-200 bg-success-50 text-success-800'
}

function ErrorPanel({
  error,
  onRetry,
}: {
  error: MarketBriefErrorState
  onRetry?: () => void
}) {
  const Icon = error.reasonCode === 'provider_transport_failure' ? WifiOff : XCircle
  return (
    <div
      className="flex items-start gap-3 rounded-[var(--radius-lg)] border border-danger-200 bg-danger-50 p-4 text-danger-800"
      role="alert"
      aria-live="assertive"
    >
      <Icon className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <h2 className="text-sm font-semibold">{error.title}</h2>
        <p className="mt-1 text-sm leading-relaxed">{error.message}</p>
        {error.omittedSymbols && error.omittedSymbols.length > 0 && (
          <p className="mt-2 text-sm leading-relaxed" data-testid="omitted-symbols">
            <span className="font-medium">Symbols not addressable:</span>{' '}
            {error.omittedSymbols.join(', ')}
          </p>
        )}
        <p className="mt-2 text-sm font-medium">Recovery: {error.recovery}</p>
        {onRetry && (
          <Button
            variant="secondary"
            size="sm"
            className="mt-3 min-h-[44px] border-danger-200 bg-[var(--bg-primary)] text-danger-800 hover:bg-danger-100"
            onClick={onRetry}
            icon={<RefreshCw className="h-4 w-4" aria-hidden="true" />}
          >
            Retry
          </Button>
        )}
      </div>
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4" aria-label="Loading market intelligence" role="status">
      <span className="sr-only">Loading market intelligence</span>
      <div className="skeleton h-7 w-2/3" />
      <div className="skeleton h-4 w-full" />
      <div className="skeleton h-32 w-full rounded-[var(--radius-lg)]" />
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="skeleton h-24 rounded-[var(--radius-lg)]" />
        <div className="skeleton h-24 rounded-[var(--radius-lg)]" />
      </div>
    </div>
  )
}

function EmptySection({ label }: { label: string }) {
  return (
    <div className="rounded-[var(--radius-md)] border border-dashed border-[var(--border-color)] bg-[var(--bg-secondary)] px-4 py-5 text-sm text-[var(--text-secondary)]">
      No source-backed {label.toLowerCase()} were available in this report window.
    </div>
  )
}

function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null
  return (
    <ul className="mt-4 space-y-2 border-t border-[var(--border-subtle)] pt-3" aria-label="Sources and freshness">
      {citations.map((citation, index) => (
        <li key={`${citation.source_url}-${index}`} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[var(--text-secondary)]">
          <a
            href={citation.source_url}
            target="_blank"
            rel="noreferrer"
            className="market-brief-source-link font-semibold text-slate-700 underline decoration-[var(--primary-300)] underline-offset-2 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--primary-500)]"
          >
            {citation.provider} source
          </a>
          <span aria-hidden="true">·</span>
          <span>{citation.freshness === 'fresh' ? 'Fresh retrieval' : citation.freshness === 'stale' ? 'Stale' : 'Freshness unknown'}</span>
          <span aria-hidden="true">·</span>
          <time dateTime={citation.published_at ?? citation.retrieved_at ?? undefined}>
            {citation.published_at ? `Observed ${formatDateTime(citation.published_at)}` : `Retrieved ${formatDateTime(citation.retrieved_at)}`}
          </time>
        </li>
      ))}
    </ul>
  )
}

function SummaryCard({
  label,
  value,
  detail,
  icon: Icon,
  tone = 'neutral',
}: {
  label: string
  value: string
  detail: string
  icon: typeof BarChart3
  tone?: 'neutral' | 'positive' | 'warning' | 'info'
}) {
  const toneClasses = {
    neutral: 'border-[var(--border-subtle)] bg-[var(--surface-color)]',
    positive: 'border-success-200 bg-success-50',
    warning: 'border-warning-200 bg-warning-50',
    info: 'border-primary-200 bg-primary-50',
  }[tone]
  return (
    <Card className={`min-w-0 border shadow-none transition-colors duration-150 hover:border-[var(--primary-300)] ${toneClasses}`} padding="compact">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label-sm text-[var(--text-secondary)]">{label}</p>
          <p className="mt-2 break-words font-mono text-xl font-semibold tabular-nums text-[var(--text-primary)]">{value}</p>
          <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">{detail}</p>
        </div>
        <Icon className="h-5 w-5 shrink-0 text-[var(--primary-600)]" aria-hidden="true" />
      </div>
    </Card>
  )
}

function materialityCounts(brief: MarketBrief | null) {
  const evidence = brief?.holding_evidence ?? []
  return {
    high: evidence.filter(packet => packet.materiality === 'high').length,
    watch: evidence.filter(packet => packet.materiality === 'watch').length,
    informational: evidence.filter(packet => packet.materiality === 'informational').length,
  }
}

function ExecutiveSummary({ brief }: { brief: MarketBrief }) {
  const portfolio = sectionByName(brief, 'portfolio_changes')
  const news = sectionByName(brief, 'material_holding_news')
  const earnings = sectionByName(brief, 'earnings')
  const filings = sectionByName(brief, 'sec_filings')
  const catalyst = sectionByName(brief, 'catalyst_stream')
  const upcoming = earnings?.content.filter(item => item.startsWith('upcoming:') || item.startsWith('today:')).length ?? 0
  const recent = earnings?.content.filter(item => item.startsWith('recent')).length ?? 0
  const counts = materialityCounts(brief)
  const cards = [
    brief.portfolio_daily_change != null && portfolio?.content.length
      ? <SummaryCard key="movement" label="Portfolio movement" value={brief.portfolio_daily_change} detail="Comparable source-backed change" icon={brief.portfolio_daily_change.startsWith('-') ? TrendingDown : TrendingUp} tone={brief.portfolio_daily_change.startsWith('-') ? 'warning' : 'positive'} />
      : null,
    brief.coverage
      ? <SummaryCard key="coverage" label="Portfolio covered" value={coveragePercent(brief.coverage)} detail={`${brief.coverage.covered_holding_count} of ${brief.coverage.eligible_holding_count} eligible holdings · ${brief.coverage.coverage_basis.replace('_', ' ')}`} icon={ShieldCheck} tone={brief.coverage.omitted_holding_count ? 'warning' : 'positive'} />
      : null,
    counts.high + counts.watch > 0 ? <SummaryCard key="catalysts" label="Items to review" value={String(counts.high + counts.watch)} detail={`${counts.high} high impact · ${counts.watch} watch · ${counts.informational} informational`} icon={LineChart} tone="info" /> : null,
    catalyst && catalyst.content.length > 0 ? <SummaryCard key="stream" label="Catalyst stream" value={String(catalyst.content.length)} detail="Ranked evidence rows with sources" icon={BarChart3} tone="info" /> : null,
    upcoming > 0 ? <SummaryCard key="upcoming" label="Upcoming earnings" value={String(upcoming)} detail="Portfolio-linked events in the report window" icon={CalendarDays} tone="info" /> : null,
    recent > 0 ? <SummaryCard key="recent" label="Recent results" value={String(recent)} detail="Portfolio-linked reported results" icon={BarChart3} tone="info" /> : null,
    news && news.content.length > 0 ? <SummaryCard key="news" label="Material news" value={String(news.content.length)} detail="Held-symbol stories with source links" icon={Newspaper} tone="info" /> : null,
    filings && filings.content.length > 0 ? <SummaryCard key="filings" label="SEC filings" value={String(filings.content.length)} detail="Allowlisted portfolio-linked filings" icon={FileText} tone="info" /> : null,
    brief.warnings.length > 0 ? <SummaryCard key="warnings" label="Data-quality warnings" value={String(brief.warnings.length)} detail="Limitations to review before acting" icon={AlertTriangle} tone="warning" /> : null,
  ].filter(Boolean)
  if (cards.length === 0) return null
  return (
    <section aria-labelledby="brief-summary-title" className="mt-8">
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <p className="label-sm text-[var(--text-secondary)]">Evidence snapshot</p>
          <h2 id="brief-summary-title" className="headline-md mt-1 text-[var(--text-primary)]">Today&rsquo;s portfolio brief</h2>
        </div>
        <p className="hidden text-right text-xs text-[var(--text-secondary)] sm:block">Cards appear only when the brief contains supporting evidence.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{cards}</div>
    </section>
  )
}

function CoveragePanel({ coverage }: { coverage: CoverageSummary }) {
  return (
    <section aria-labelledby="coverage-title" className="mt-6 rounded-[var(--radius-lg)] border border-warning-200 bg-warning-50 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warning-700" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="coverage-title" className="text-sm font-semibold text-warning-900">Portfolio coverage</h2>
            <Badge variant="warning" size="sm" className="market-brief-warning !bg-amber-100 !text-amber-900 dark:!bg-amber-900 dark:!text-amber-100">{coveragePercent(coverage)} covered</Badge>
          </div>
          <p className="mt-1 text-sm leading-relaxed text-warning-900">
            {coverage.covered_holding_count} of {coverage.eligible_holding_count} eligible holdings are covered using {coverage.coverage_basis.replace('_', ' ')} coverage. The safe minimum is {Number(coverage.minimum_required_percentage) * 100}%.
          </p>
          {coverage.omissions.length > 0 && (
            <ul className="mt-3 grid gap-2 text-sm text-warning-900 sm:grid-cols-2" aria-label="Omitted holdings and reasons">
              {coverage.omissions.map((omission, index) => (
                <li key={`${omission.symbol}-${omission.evidence_category ?? 'quote'}-${index}`} className="flex items-start gap-2">
                  <CircleHelp className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                  <span><strong>{omission.symbol}</strong> — {omission.evidence_category ? `${omission.evidence_category}: ` : ''}{reasonLabel(omission.reason_code)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  )
}

function BriefSectionView({ section }: { section: BriefSection }) {
  const label = SECTION_LABELS[section.name] ?? section.name.replaceAll('_', ' ')
  return (
    <section aria-labelledby={`brief-section-${section.name}`} className="border-t border-[var(--border-subtle)] pt-6 first:border-t-0 first:pt-0">
      <div className="flex items-start justify-between gap-4">
        <h2 id={`brief-section-${section.name}`} className="headline-sm text-[var(--text-primary)]">{label}</h2>
        {section.content.length > 0 && <span className="text-xs text-[var(--text-secondary)]">{section.content.length} {section.content.length === 1 ? 'item' : 'items'}</span>}
      </div>
      <div className="mt-3">
        {section.content.length > 0 ? (
          <ul className="space-y-2 text-sm leading-relaxed text-[var(--text-primary)]">
            {section.content.map((item, index) => <li key={`${item}-${index}`} className="flex items-start gap-2"><ChevronRight className="mt-1 h-4 w-4 shrink-0 text-[var(--primary-600)]" aria-hidden="true" /><span>{item}</span></li>)}
          </ul>
        ) : <EmptySection label={label} />}
      </div>
      <CitationList citations={section.citations} />
    </section>
  )
}

function ActionsToReview({ actions }: { actions: NonNullable<MarketBrief['actions']> }) {
  if (actions.length === 0) return null
  return (
    <section aria-labelledby="actions-to-review" className="mt-8">
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <p className="label-sm text-[var(--text-secondary)]">User control required</p>
          <h2 id="actions-to-review" className="headline-md mt-1 text-[var(--text-primary)]">Actions to review</h2>
        </div>
        <Badge variant="warning" size="sm" className="market-brief-warning !bg-amber-100 !text-amber-900 dark:!bg-amber-900 dark:!text-amber-100">No execution</Badge>
      </div>
      <div className="space-y-4">
        {actions.map(action => (
          <Card key={action.action} className="border-primary-200 bg-primary-50/60 shadow-none" padding="default">
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-[var(--primary-700)]" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <h3 className="text-base font-semibold text-[var(--text-primary)]">{action.action}</h3>
                <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">{action.why}</p>
                <dl className="mt-4 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
                  <div><dt className="font-semibold text-[var(--text-primary)]">Goal linkage</dt><dd className="mt-1 text-[var(--text-secondary)]">{action.goal_linkage}</dd></div>
                  <div><dt className="font-semibold text-[var(--text-primary)]">Expected impact</dt><dd className="mt-1 text-[var(--text-secondary)]">{action.expected_impact}</dd></div>
                  <div><dt className="font-semibold text-[var(--text-primary)]">Confidence</dt><dd className="mt-1 text-[var(--text-secondary)]">{action.confidence}</dd></div>
                  <div><dt className="font-semibold text-[var(--text-primary)]">Approval</dt><dd className="mt-1 font-semibold text-warning-800">Explicit user approval required</dd></div>
                </dl>
                <div className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
                  <div><h4 className="font-semibold text-[var(--text-primary)]">Evidence</h4><p className="mt-1 text-[var(--text-secondary)]">{action.evidence.join(', ') || 'No comparable position data.'}</p></div>
                  <div><h4 className="font-semibold text-[var(--text-primary)]">Risks</h4><p className="mt-1 text-[var(--text-secondary)]">{action.risks.join(', ')}</p></div>
                  <div><h4 className="font-semibold text-[var(--text-primary)]">Alternatives</h4><p className="mt-1 text-[var(--text-secondary)]">{action.alternatives.join(', ')}</p></div>
                </div>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </section>
  )
}

function priceMovement(packet: HoldingEvidence) {
  const current = packet.quote?.current_price
  const previous = packet.quote?.previous_close
  if (!current || !previous) return null
  const currentNum = Number(current)
  const previousNum = Number(previous)
  if (!Number.isFinite(currentNum) || !Number.isFinite(previousNum) || previousNum <= 0) return null
  const pct = ((currentNum - previousNum) / previousNum) * 100
  return { pct, up: pct >= 0 }
}

function CatalystStream({ evidence }: { evidence: HoldingEvidence[] }) {
  const ranked = useMemo(
    () => [...evidence].sort((a, b) => {
      const order = { high: 0, watch: 1, informational: 2 } as const
      return order[a.materiality] - order[b.materiality] || a.symbol.localeCompare(b.symbol)
    }),
    [evidence],
  )
  if (ranked.length === 0) return null
  return (
    <section aria-labelledby="catalyst-stream-title" className="mt-8">
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <p className="label-sm text-[var(--text-secondary)]">Ranked evidence</p>
          <h2 id="catalyst-stream-title" className="headline-md mt-1 text-[var(--text-primary)]">What could move your holdings</h2>
        </div>
        <p className="hidden text-right text-xs text-[var(--text-secondary)] sm:block">Ranked by materiality from server evidence.</p>
      </div>
      <ul className="space-y-3">
        {ranked.map(packet => {
          const movement = priceMovement(packet)
          const headline = packet.news[0]?.headline ?? packet.materiality_reason ?? 'Evidence available.'
          const newsCount = packet.news.length
          const earningsCount = packet.earnings_events.length + packet.earnings_results.length
          const filingCount = packet.filings.length
          const dividendCount = packet.dividends.length
          const details = [
            packet.news.length > 0 ? `${newsCount} news ${newsCount === 1 ? 'story' : 'stories'}` : null,
            earningsCount > 0 ? `${earningsCount} earnings ${earningsCount === 1 ? 'item' : 'items'}` : null,
            filingCount > 0 ? `${filingCount} filing${filingCount === 1 ? '' : 's'}` : null,
            dividendCount > 0 ? `${dividendCount} dividend ${dividendCount === 1 ? 'event' : 'events'}` : null,
            packet.price_target?.target_mean ? `mean target ${packet.price_target.target_mean}` : null,
          ].filter(Boolean)
          return (
            <li key={packet.symbol}>
              <details className="group rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--surface-color)] shadow-[var(--shadow-1)] transition-colors duration-150 open:border-[var(--primary-300)]">
                <summary className="flex cursor-pointer list-none items-start gap-3 p-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--primary-500)] sm:items-center">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-primary-50 font-mono text-sm font-bold text-[var(--primary-700)]" aria-hidden="true">
                    {packet.symbol.slice(0, 4)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <Badge variant={MATERIALITY_VARIANTS[packet.materiality]} size="sm" className="normal-case tracking-normal">{MATERIALITY_LABELS[packet.materiality]}</Badge>
                      {movement && (
                        <span className={`inline-flex items-center gap-1 font-mono text-xs font-semibold tabular-nums ${movement.up ? 'text-success-700' : 'text-danger-700'}`}>
                          {movement.up ? <TrendingUp className="h-3.5 w-3.5" aria-hidden="true" /> : <TrendingDown className="h-3.5 w-3.5" aria-hidden="true" />}
                          {movement.pct >= 0 ? '+' : ''}{movement.pct.toFixed(2)}%
                        </span>
                      )}
                      <span className="font-mono text-xs text-[var(--text-secondary)]">{packet.symbol}</span>
                    </span>
                    <span className="mt-1 block truncate text-sm font-medium text-[var(--text-primary)] sm:truncate">{headline}</span>
                    <span className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-[var(--text-secondary)]">
                      {details.length > 0 ? <span>{details.join(' · ')}</span> : <span>No additional evidence categories available</span>}
                    </span>
                  </span>
                  <ChevronRight className="h-4 w-4 shrink-0 text-[var(--text-tertiary)] transition-transform duration-150 group-open:rotate-90" aria-hidden="true" />
                </summary>
                <div className="border-t border-[var(--border-subtle)] px-4 pb-4 pt-3">
                  {packet.materiality_reason && (
                    <div className="mb-3 rounded-[var(--radius-md)] bg-[var(--bg-secondary)] p-3 text-sm leading-relaxed text-[var(--text-primary)]">
                      <span className="font-semibold">Why it matters:</span> {packet.materiality_reason}
                    </div>
                  )}
                  <div className="grid gap-4 sm:grid-cols-2">
                    {packet.news.length > 0 && (
                      <div>
                        <h3 className="label-sm text-[var(--text-secondary)]">Company news</h3>
                        <ul className="mt-2 space-y-2">
                          {packet.news.slice(0, 4).map((item, index) => (
                            <li key={`${item.source.source_url}-${index}`} className="text-sm leading-relaxed">
                              <a href={item.source.source_url} target="_blank" rel="noreferrer" className="market-brief-source-link font-medium text-[var(--text-primary)] underline decoration-[var(--primary-300)] underline-offset-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--primary-500)]">
                                {item.headline}
                              </a>
                              <span className="mt-0.5 block text-xs text-[var(--text-secondary)]">{item.publisher ?? item.source.provider} · {item.source.freshness === 'fresh' ? 'Fresh' : 'Stale'}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {packet.earnings_events.length > 0 && (
                      <div>
                        <h3 className="label-sm text-[var(--text-secondary)]">Earnings</h3>
                        <ul className="mt-2 space-y-1.5 text-sm text-[var(--text-primary)]">
                          {packet.earnings_events.slice(0, 3).map((event, index) => (
                            <li key={`${event.event_date}-${index}`} className="flex items-start gap-2"><CalendarDays className="mt-0.5 h-4 w-4 shrink-0 text-[var(--primary-600)]" aria-hidden="true" /><span>{formatDateOnly(event.event_date)}</span></li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {packet.earnings_results.length > 0 && (
                      <div>
                        <h3 className="label-sm text-[var(--text-secondary)]">Reported results</h3>
                        <ul className="mt-2 space-y-1.5 text-sm text-[var(--text-primary)]">
                          {packet.earnings_results.slice(0, 3).map((result, index) => (
                            <li key={`${result.actual}-${index}`} className="flex items-start gap-2">
                              <BarChart3 className="mt-0.5 h-4 w-4 shrink-0 text-[var(--primary-600)]" aria-hidden="true" />
                              <span>Actual {result.actual ?? 'not reported'}{result.estimate ? ` vs estimate ${result.estimate}` : ''}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {packet.filings.length > 0 && (
                      <div>
                        <h3 className="label-sm text-[var(--text-secondary)]">SEC filings</h3>
                        <ul className="mt-2 space-y-1.5 text-sm text-[var(--text-primary)]">
                          {packet.filings.slice(0, 3).map((filing, index) => (
                            <li key={`${filing.accession_number}-${index}`} className="flex items-start gap-2"><FileText className="mt-0.5 h-4 w-4 shrink-0 text-[var(--primary-600)]" aria-hidden="true" /><span>{filing.form} · {formatDateOnly(filing.filing_date)}</span></li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {packet.dividends.length > 0 && (
                      <div>
                        <h3 className="label-sm text-[var(--text-secondary)]">Dividends</h3>
                        <ul className="mt-2 space-y-1.5 text-sm text-[var(--text-primary)]">
                          {packet.dividends.slice(0, 3).map((dividend, index) => (
                            <li key={`${dividend.ex_date ?? dividend.symbol}-${index}`} className="flex items-start gap-2">
                              <Landmark className="mt-0.5 h-4 w-4 shrink-0 text-[var(--primary-600)]" aria-hidden="true" />
                              <span>{dividend.ex_date ? `Ex-date ${formatDateOnly(dividend.ex_date)}` : 'Dividend event'}{dividend.amount ? ` · ${dividend.amount}` : ''}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {packet.recommendations.length > 0 && (
                      <div>
                        <h3 className="label-sm text-[var(--text-secondary)]">Analyst consensus</h3>
                        <p className="mt-2 text-sm text-[var(--text-primary)]">
                          {(() => {
                            const row = packet.recommendations[0]
                            const total = row.strong_buy + row.buy + row.hold + row.sell + row.strong_sell
                            return total > 0 ? `${row.strong_buy + row.buy} of ${total} analysts at buy or strong buy (period ${row.period})` : `No consensus rows for period ${row.period}`
                          })()}
                        </p>
                      </div>
                    )}
                  </div>
                  {packet.news[0] && (
                    <div className="mt-4 border-t border-[var(--border-subtle)] pt-3">
                      <p className="text-xs text-[var(--text-secondary)]">
                        <span className="font-semibold">Source:</span>{' '}
                        <a href={packet.news[0].source.source_url} target="_blank" rel="noreferrer" className="market-brief-source-link font-semibold text-slate-700 underline decoration-[var(--primary-300)] underline-offset-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--primary-500)]">
                          {packet.news[0].source.provider} source
                        </a>{' '}
                        · retrieved {formatDateTime(packet.news[0].source.retrieved_at)}
                      </p>
                    </div>
                  )}
                </div>
              </details>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function EarningsRadar({ brief }: { brief: MarketBrief }) {
  const evidence = brief.holding_evidence ?? []
  const events = evidence.flatMap(packet => packet.earnings_events.map(event => ({ ...event, symbol: packet.symbol })))
  const results = evidence.flatMap(packet => packet.earnings_results.map(result => ({ ...result, symbol: packet.symbol })))
  if (events.length === 0 && results.length === 0) return null
  const today = new Date()
  const upcoming = events.filter(event => new Date(event.event_date) >= today).sort((a, b) => new Date(a.event_date).getTime() - new Date(b.event_date).getTime())
  const reported = results.slice(0, 4)
  return (
    <section aria-labelledby="earnings-radar-title" className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--surface-color)] p-4 shadow-[var(--shadow-1)]">
      <div className="flex items-center gap-2"><CalendarDays className="h-5 w-5 text-[var(--primary-600)]" aria-hidden="true" /><h2 id="earnings-radar-title" className="headline-sm text-[var(--text-primary)]">Earnings radar</h2></div>
      {upcoming.length > 0 && (
        <ul className="mt-3 space-y-2 text-sm">
          {upcoming.slice(0, 4).map((event, index) => (
            <li key={`${event.symbol}-${event.event_date}-${index}`} className="flex items-center justify-between gap-3">
              <span className="font-mono font-semibold text-[var(--text-primary)]">{event.symbol}</span>
              <time dateTime={event.event_date} className="text-xs text-[var(--text-secondary)]">{formatDateOnly(event.event_date)}</time>
            </li>
          ))}
        </ul>
      )}
      {reported.length > 0 && (
        <>
          <h3 className="label-sm mt-4 text-[var(--text-secondary)]">Reported results</h3>
          <ul className="mt-2 space-y-2 text-sm">
            {reported.map((result, index) => (
              <li key={`${result.symbol}-${index}`} className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-mono font-semibold text-[var(--text-primary)]">{result.symbol}</span>
                <span className="text-xs text-[var(--text-secondary)]">{result.estimate ? `Actual ${result.actual ?? 'n/a'} vs est. ${result.estimate}` : `Actual ${result.actual ?? 'n/a'}`}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="mt-3 text-xs leading-relaxed text-[var(--text-secondary)]">Upcoming and reported events from server-owned evidence only.</p>
    </section>
  )
}

function RiskRadar({ brief }: { brief: MarketBrief }) {
  const coverage = brief.coverage
  const availability = brief.evidence_availability ?? []
  const warnings = brief.warnings ?? []
  const risks: Array<{ label: string; detail: string }> = []
  if (coverage && coverage.omitted_holding_count > 0) {
    risks.push({ label: `${coverage.omitted_holding_count} holding${coverage.omitted_holding_count === 1 ? '' : 's'} not covered`, detail: 'Omitted holdings have no trustworthy market evidence in this brief.' })
  }
  const stale = availability.filter(record => record.reason_code === 'live_quote_stale' || record.reason_code === 'prior_close_too_old')
  if (stale.length > 0) {
    risks.push({ label: `${stale.length} stale evidence ${stale.length === 1 ? 'record' : 'records'}`, detail: 'Freshness policy excluded the latest provider observations.' })
  }
  if (warnings.length > 0) {
    risks.push({ label: `${warnings.length} data-quality warning${warnings.length === 1 ? '' : 's'}`, detail: 'Review the limitations panel for the exact boundaries.' })
  }
  if (risks.length === 0) return null
  return (
    <section aria-labelledby="risk-radar-title" className="rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--surface-color)] p-4 shadow-[var(--shadow-1)]">
      <div className="flex items-center gap-2"><AlertTriangle className="h-5 w-5 text-warning-700" aria-hidden="true" /><h2 id="risk-radar-title" className="headline-sm text-[var(--text-primary)]">Portfolio risk radar</h2></div>
      <ul className="mt-3 space-y-3">
        {risks.map((risk, index) => (
          <li key={`${risk.label}-${index}`} className="rounded-[var(--radius-md)] bg-warning-50 p-3 text-sm">
            <p className="font-semibold text-warning-900">{risk.label}</p>
            <p className="mt-1 text-xs leading-relaxed text-warning-900/80">{risk.detail}</p>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs leading-relaxed text-[var(--text-secondary)]">Risk radar reflects evidence availability reported by the server, never client-side guesses.</p>
    </section>
  )
}

function ArchiveList({
  items,
  selectedId,
  onSelect,
}: {
  items: BriefIndex[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  return (
    <nav aria-label="Saved market briefs">
      <ul className="space-y-2">
        {items.map(item => {
          const selected = item.brief_id === selectedId
          return (
            <li key={item.brief_id}>
              <button
                type="button"
                onClick={() => onSelect(item.brief_id)}
                aria-label={`Brief for ${item.report_window || 'latest report'} (${formatDateTime(item.generated_at)})`}
                aria-current={selected ? 'page' : undefined}
                className={`group flex min-h-[72px] w-full items-start gap-3 rounded-[var(--radius-md)] border p-3 text-left transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--primary-500)] ${selected ? 'border-primary-500 bg-primary-50' : 'border-[var(--border-subtle)] bg-[var(--surface-color)] hover:border-primary-300 hover:bg-primary-50/50'}`}
              >
                <Archive className={`mt-0.5 h-4 w-4 shrink-0 ${selected ? 'text-[var(--primary-700)]' : 'text-[var(--text-secondary)]'}`} aria-hidden="true" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold text-[var(--text-primary)]">{item.report_window || 'Latest report'}</span>
                  <time className="mt-1 block text-xs text-[var(--text-secondary)]" dateTime={item.generated_at}>{formatDateTime(item.generated_at)}</time>
                  <span className="mt-2 flex flex-wrap gap-1.5">
                    {item.market_data_basis && item.market_data_basis !== 'unknown' && <span className="rounded-full bg-[var(--slate-100)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]">{basisLabel(item.market_data_basis)}</span>}
                    {item.coverage && <span className="rounded-full bg-[var(--slate-100)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]">{coveragePercent(item.coverage)} covered</span>}
                  </span>
                </span>
                <ChevronRight className={`mt-0.5 h-4 w-4 shrink-0 transition-transform duration-150 ${selected ? 'translate-x-0.5 text-[var(--primary-600)]' : 'text-[var(--text-tertiary)] group-hover:translate-x-0.5'}`} aria-hidden="true" />
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

function PulseIndices({ pulse }: { pulse: MarketPulseSnapshot }) {
  if (pulse.indices.length === 0) return null
  return (
    <section aria-labelledby="pulse-indices-title">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 id="pulse-indices-title" className="headline-sm text-[var(--text-primary)]">Index direction</h2>
        <Badge variant="info" size="sm" className="normal-case tracking-normal">ETF proxies</Badge>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {pulse.indices.map(index => (
          <Card key={index.symbol} className="min-w-0 border-[var(--border-subtle)] shadow-none" padding="compact">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="label-sm text-[var(--text-secondary)]">{index.label}</p>
                <p className="mt-2 break-words font-mono text-xl font-semibold tabular-nums text-[var(--text-primary)]">{index.current_price}</p>
                <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
                  {index.direction === 'unavailable' ? 'Direction unavailable' : index.direction === 'up' ? 'Higher than prior close' : index.direction === 'down' ? 'Lower than prior close' : 'Flat versus prior close'}
                  {index.previous_close ? ` · prior ${index.previous_close}` : ''}
                </p>
              </div>
              {index.direction === 'up' && <TrendingUp className="h-5 w-5 shrink-0 text-success-700" aria-hidden="true" />}
              {index.direction === 'down' && <TrendingDown className="h-5 w-5 shrink-0 text-danger-700" aria-hidden="true" />}
              {index.direction === 'flat' && <BarChart3 className="h-5 w-5 shrink-0 text-[var(--text-secondary)]" aria-hidden="true" />}
              {index.direction === 'unavailable' && <CircleHelp className="h-5 w-5 shrink-0 text-[var(--text-secondary)]" aria-hidden="true" />}
            </div>
          </Card>
        ))}
      </div>
      <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">The free provider cannot quote raw indices; these approved ETF proxies are labeled truthfully and never passed off as the index itself.</p>
    </section>
  )
}

function PulseNews({ pulse }: { pulse: MarketPulseSnapshot }) {
  if (pulse.news.length === 0) return null
  return (
    <section aria-labelledby="pulse-news-title">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 id="pulse-news-title" className="headline-sm text-[var(--text-primary)]">Market-wide headlines</h2>
        <Badge variant="neutral" size="sm" className="normal-case tracking-normal">{pulse.news.length}</Badge>
      </div>
      <ul className="space-y-3">
        {pulse.news.slice(0, 8).map((item, index) => (
          <li key={`${item.source.source_url}-${index}`} className="rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--surface-color)] p-3">
            <a href={item.source.source_url} target="_blank" rel="noreferrer" className="market-brief-source-link text-sm font-medium leading-relaxed text-[var(--text-primary)] underline decoration-[var(--primary-300)] underline-offset-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--primary-500)]">
              {item.headline}
            </a>
            {item.summary && <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">{item.summary}</p>}
            <p className="mt-1 text-xs text-[var(--text-secondary)]">{item.publisher ?? item.source.provider} · {item.source.freshness === 'fresh' ? 'Fresh retrieval' : 'Freshness unknown'}</p>
          </li>
        ))}
      </ul>
    </section>
  )
}

function PulseUnavailable({ pulse }: { pulse: MarketPulseSnapshot }) {
  if (pulse.categories_unavailable.length === 0) return null
  const labels: Record<string, string> = {
    indices: 'Index direction',
    market_news: 'Market-wide headlines',
    earnings_calendar: 'Market earnings calendar',
    scanner: 'S&P 500 scanner',
  }
  return (
    <section aria-labelledby="pulse-unavailable-title" className="rounded-[var(--radius-lg)] border border-warning-200 bg-warning-50 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warning-700" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <h2 id="pulse-unavailable-title" className="text-sm font-semibold text-warning-900">Some market categories are unavailable</h2>
          <p className="mt-1 text-sm leading-relaxed text-warning-900">
            {pulse.categories_unavailable.map(category => labels[category] ?? category.replaceAll('_', ' ')).join(', ')} could not be supplied by the approved free provider right now. Atlas never fabricates missing market data.
          </p>
        </div>
      </div>
    </section>
  )
}

function PulseView({ pulse, onRefresh }: { pulse: MarketPulseSnapshot | null; onRefresh: () => void }) {
  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="label-sm text-[var(--text-secondary)]">Zero-dollar market context</p>
          <h2 className="headline-md mt-1 text-[var(--text-primary)]">Market Pulse</h2>
        </div>
        <Button
          variant="secondary"
          size="sm"
          className="min-h-[44px]"
          onClick={onRefresh}
          icon={<RefreshCw className="h-4 w-4" aria-hidden="true" />}
        >
          Refresh pulse
        </Button>
      </div>
      {pulse && <p className="text-sm text-[var(--text-secondary)]">Server snapshot as of <time dateTime={pulse.generated_at}>{formatDateTime(pulse.generated_at)}</time>. Holdings take priority in the scanner; the sample is bounded to respect provider quotas.</p>}
      {pulse && <PulseUnavailable pulse={pulse} />}
      {pulse && <PulseIndices pulse={pulse} />}
      {pulse && <PulseNews pulse={pulse} />}
      {pulse && pulse.earnings_calendar.length > 0 && (
        <section aria-labelledby="pulse-calendar-title">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 id="pulse-calendar-title" className="headline-sm text-[var(--text-primary)]">Upcoming market earnings</h2>
            <Badge variant="neutral" size="sm" className="normal-case tracking-normal">{pulse.earnings_calendar.length}</Badge>
          </div>
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {pulse.earnings_calendar.slice(0, 12).map((event, index) => (
              <li key={`${event.symbol}-${event.event_date}-${index}`} className="flex items-center justify-between gap-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--surface-color)] px-3 py-2">
                <span className="font-mono text-sm font-semibold text-[var(--text-primary)]">{event.symbol}</span>
                <time dateTime={event.event_date} className="text-xs text-[var(--text-secondary)]">{formatDateOnly(event.event_date)}</time>
              </li>
            ))}
          </ul>
        </section>
      )}
      {pulse && pulse.scanner.length > 0 && (
        <section aria-labelledby="pulse-scanner-title">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 id="pulse-scanner-title" className="headline-sm text-[var(--text-primary)]">Scanner preview</h2>
            <Badge variant="info" size="sm" className="normal-case tracking-normal">{pulse.scanned_symbol_count} of {pulse.total_universe_size}</Badge>
          </div>
          <p className="mb-3 text-sm leading-relaxed text-[var(--text-secondary)]">A bounded sample: portfolio holdings first, then the bundled S&P 500 universe, deduplicated and quota-aware. Open the S&P 500 Scanner tab for the full list.</p>
          <div className="overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--surface-color)]">
            <table className="w-full min-w-[480px] text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--border-subtle)] text-xs uppercase tracking-wide text-[var(--text-secondary)]">
                  <th scope="col" className="px-3 py-2 font-semibold">Symbol</th>
                  <th scope="col" className="px-3 py-2 text-right font-semibold">Price</th>
                  <th scope="col" className="px-3 py-2 text-right font-semibold">Prior close</th>
                  <th scope="col" className="px-3 py-2 text-right font-semibold">Move</th>
                </tr>
              </thead>
              <tbody>
                {pulse.scanner.slice(0, 8).map(quote => {
                  const current = Number(quote.current_price)
                  const previous = Number(quote.previous_close)
                  const pct = previous > 0 && Number.isFinite(current) && Number.isFinite(previous) ? ((current - previous) / previous) * 100 : null
                  return (
                    <tr key={quote.symbol} className="border-b border-[var(--border-subtle)] last:border-b-0">
                      <td className="px-3 py-2 font-mono font-semibold text-[var(--text-primary)]">{quote.symbol}</td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums text-[var(--text-primary)]">{quote.current_price}</td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums text-[var(--text-secondary)]">{quote.previous_close ?? '—'}</td>
                      <td className={`px-3 py-2 text-right font-mono tabular-nums ${pct === null ? 'text-[var(--text-secondary)]' : pct >= 0 ? 'text-success-700' : 'text-danger-700'}`}>{pct === null ? '—' : `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}

function EarningsEventsView({ brief, pulse }: { brief: MarketBrief | null; pulse: MarketPulseSnapshot | null }) {
  const evidence = brief?.holding_evidence ?? []
  const portfolioEvents = evidence.flatMap(packet => packet.earnings_events.map(event => ({ ...event, symbol: packet.symbol })))
  const portfolioResults = evidence.flatMap(packet => packet.earnings_results.map(result => ({ ...result, symbol: packet.symbol })))
  const marketEvents = pulse?.earnings_calendar ?? []
  return (
    <div className="space-y-8">
      <div>
        <p className="label-sm text-[var(--text-secondary)]">Earnings and material events</p>
        <h2 className="headline-md mt-1 text-[var(--text-primary)]">Earnings &amp; Events</h2>
      </div>
      <section aria-labelledby="portfolio-earnings-title">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 id="portfolio-earnings-title" className="headline-sm text-[var(--text-primary)]">Portfolio-linked earnings</h2>
          <Badge variant="info" size="sm" className="normal-case tracking-normal">Your holdings</Badge>
        </div>
        {portfolioEvents.length === 0 && portfolioResults.length === 0 ? (
          <div className="rounded-[var(--radius-md)] border border-dashed border-[var(--border-color)] bg-[var(--bg-secondary)] px-4 py-5 text-sm leading-relaxed text-[var(--text-secondary)]">
            {brief ? 'No portfolio-linked earnings events or reported results were available in the current brief. Generate a fresh brief to refresh the evidence.' : 'Generate a brief first — portfolio-linked earnings come from the server-composed evidence, never from the browser.'}
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {portfolioEvents.map((event, index) => (
              <div key={`${event.symbol}-${event.event_date}-${index}`} className="flex items-center justify-between gap-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--surface-color)] px-3 py-2">
                <span className="font-mono text-sm font-semibold text-[var(--text-primary)]">{event.symbol}</span>
                <time dateTime={event.event_date} className="text-xs text-[var(--text-secondary)]">{formatDateOnly(event.event_date)}</time>
              </div>
            ))}
            {portfolioResults.map((result, index) => (
              <div key={`${result.symbol}-result-${index}`} className="rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--surface-color)] px-3 py-2">
                <span className="font-mono text-sm font-semibold text-[var(--text-primary)]">{result.symbol}</span>
                <p className="mt-1 text-xs text-[var(--text-secondary)]">{result.estimate ? `Actual ${result.actual ?? 'n/a'} vs estimate ${result.estimate}` : `Actual ${result.actual ?? 'n/a'}`}</p>
              </div>
            ))}
          </div>
        )}
      </section>
      <section aria-labelledby="market-calendar-title">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 id="market-calendar-title" className="headline-sm text-[var(--text-primary)]">Market earnings calendar</h2>
          <Badge variant="neutral" size="sm" className="normal-case tracking-normal">Next 14 days</Badge>
        </div>
        {marketEvents.length === 0 ? (
          <div className="rounded-[var(--radius-md)] border border-dashed border-[var(--border-color)] bg-[var(--bg-secondary)] px-4 py-5 text-sm leading-relaxed text-[var(--text-secondary)]">
            {pulse ? 'No market-wide earnings events were returned for the window.' : 'The market earnings calendar was not available from the provider. Open Market Pulse to refresh the server-owned snapshot.'}
          </div>
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {marketEvents.map((event, index) => (
              <li key={`${event.symbol}-${event.event_date}-${index}`} className="flex items-center justify-between gap-3 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--surface-color)] px-3 py-2">
                <span className="font-mono text-sm font-semibold text-[var(--text-primary)]">{event.symbol}</span>
                <time dateTime={event.event_date} className="text-xs text-[var(--text-secondary)]">{formatDateOnly(event.event_date)}</time>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

function ScannerView({ pulse, onRefresh }: { pulse: MarketPulseSnapshot | null; onRefresh: () => void }) {
  const [query, setQuery] = useState('')
  const filtered = useMemo(() => {
    const symbols = pulse?.scanner ?? []
    const needle = query.trim().toUpperCase()
    if (!needle) return symbols
    return symbols.filter(quote => quote.symbol.startsWith(needle) || quote.symbol.includes(needle))
  }, [pulse, query])
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="label-sm text-[var(--text-secondary)]">Bounded, quota-aware coverage</p>
          <h2 className="headline-md mt-1 text-[var(--text-primary)]">S&amp;P 500 Scanner</h2>
        </div>
        <Button
          variant="secondary"
          size="sm"
          className="min-h-[44px]"
          onClick={onRefresh}
          icon={<RefreshCw className="h-4 w-4" aria-hidden="true" />}
        >
          Refresh scan
        </Button>
      </div>
      <div className="rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--surface-color)] px-3 py-2">
        <label htmlFor="scanner-search" className="sr-only">Search scanned symbols</label>
        <div className="flex items-center gap-2">
          <Search className="h-4 w-4 shrink-0 text-[var(--text-secondary)]" aria-hidden="true" />
          <input
            id="scanner-search"
            type="search"
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Filter by symbol, e.g. AAPL"
            className="min-h-[40px] w-full bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:outline-none"
            autoComplete="off"
          />
        </div>
      </div>
      <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
        {pulse
          ? `Scanned ${pulse.scanned_symbol_count} of ${pulse.total_universe_size} universe symbols in this bounded sample. Portfolio holdings are always prioritized; the scan respects provider rate limits and never requests the whole universe at once.`
          : 'The scanner has not been loaded yet. Open Market Pulse or use Refresh scan to fetch the server-owned bounded snapshot.'}
      </p>
      {pulse && pulse.scanner.length === 0 && (
        <div className="rounded-[var(--radius-md)] border border-dashed border-[var(--border-color)] bg-[var(--bg-secondary)] px-4 py-5 text-sm leading-relaxed text-[var(--text-secondary)]">
          The approved provider returned no usable quotes for this scan window. No data is fabricated.
        </div>
      )}
      {filtered.length > 0 && (
        <div className="overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--surface-color)]">
          <table className="w-full min-w-[520px] text-left text-sm">
            <thead>
              <tr className="border-b border-[var(--border-subtle)] text-xs uppercase tracking-wide text-[var(--text-secondary)]">
                <th scope="col" className="px-3 py-2 font-semibold">Symbol</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold">Price</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold">Prior close</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold">Move</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(quote => {
                const current = Number(quote.current_price)
                const previous = Number(quote.previous_close)
                const pct = previous > 0 && Number.isFinite(current) && Number.isFinite(previous) ? ((current - previous) / previous) * 100 : null
                return (
                  <tr key={quote.symbol} className="border-b border-[var(--border-subtle)] last:border-b-0">
                    <td className="px-3 py-2 font-mono font-semibold text-[var(--text-primary)]">{quote.symbol}</td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-[var(--text-primary)]">{quote.current_price}</td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-[var(--text-secondary)]">{quote.previous_close ?? '—'}</td>
                    <td className={`px-3 py-2 text-right font-mono tabular-nums ${pct === null ? 'text-[var(--text-secondary)]' : pct >= 0 ? 'text-success-700' : 'text-danger-700'}`}>{pct === null ? '—' : `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {pulse && filtered.length === 0 && pulse.scanner.length > 0 && (
        <p className="text-sm text-[var(--text-secondary)]">No scanned symbol matches &ldquo;{query}&rdquo;. Try another prefix.</p>
      )}
    </div>
  )
}

export default function MarketIntelligenceCenter() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const queryString = searchParams.toString()
  const requestedTab = new URLSearchParams(queryString).get('view')
  const urlTab: TabId = TABS.some(tab => tab.id === requestedTab) ? requestedTab as TabId : 'portfolio'
  const [items, setItems] = useState<BriefIndex[]>([])
  const [brief, setBrief] = useState<MarketBrief | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabId>(urlTab)
  const [archiveStatus, setArchiveStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [archiveError, setArchiveError] = useState<MarketBriefErrorState | null>(null)
  const [detailStatus, setDetailStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [detailError, setDetailError] = useState<MarketBriefErrorState | null>(null)
  const [generating, setGenerating] = useState(false)
  const [generationError, setGenerationError] = useState<MarketBriefErrorState | null>(null)
  const [announcement, setAnnouncement] = useState('Loading saved market briefs…')
  const [pulse, setPulse] = useState<MarketPulseSnapshot | null>(null)
  const [pulseStatus, setPulseStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [pulseError, setPulseError] = useState<MarketBriefErrorState | null>(null)
  const detailRequest = useRef(0)
  const tabRefs = useRef<Record<TabId, HTMLButtonElement | null>>({
    portfolio: null,
    pulse: null,
    earnings: null,
    scanner: null,
    archive: null,
  })

  useEffect(() => {
    setActiveTab(urlTab)
  }, [urlTab])

  const selectTab = useCallback((tab: TabId) => {
    const params = new URLSearchParams(queryString)
    params.set('view', tab)
    router.replace(`?${params.toString()}`, { scroll: false })
    setActiveTab(tab)
    setAnnouncement(`${TABS.find(entry => entry.id === tab)?.label ?? tab} view selected.`)
  }, [queryString, router])

  const loadArchive = useCallback(async () => {
    setArchiveStatus('loading')
    setArchiveError(null)
    setAnnouncement('Loading saved market briefs…')
    try {
      const nextItems = await listMarketBriefs()
      setItems(nextItems)
      setArchiveStatus('ready')
      setAnnouncement(nextItems.length ? `${nextItems.length} saved market brief${nextItems.length === 1 ? '' : 's'} available.` : 'No saved market briefs yet.')
    } catch (error: unknown) {
      const nextError = classifyMarketBriefError(error)
      setArchiveError(nextError)
      setArchiveStatus('error')
      setAnnouncement(nextError.title)
    }
  }, [])

  useEffect(() => {
    void loadArchive()
  }, [loadArchive])

  const open = useCallback(async (id: string) => {
    const requestId = ++detailRequest.current
    setGenerationError(null)
    setSelectedId(id)
    setBrief(null)
    setDetailError(null)
    setDetailStatus('loading')
    setAnnouncement('Loading the selected market brief…')
    try {
      const nextBrief = await getMarketBrief(id)
      if (requestId !== detailRequest.current) return
      setBrief(nextBrief)
      setDetailStatus('ready')
      setAnnouncement(`Loaded market brief from ${formatDateTime(nextBrief.generated_at)}.`)
    } catch (error: unknown) {
      if (requestId !== detailRequest.current) return
      const nextError = classifyMarketBriefError(error)
      setDetailError(nextError)
      setDetailStatus('error')
      setAnnouncement(nextError.title)
    }
  }, [])

  const generate = useCallback(async () => {
    setGenerating(true)
    setGenerationError(null)
    setAnnouncement('Generating a deterministic market brief from server-owned evidence…')
    try {
      const result = await generateMarketBrief()
      setBrief(result.brief)
      setSelectedId(result.brief_id)
      setDetailStatus('ready')
      selectTab('portfolio')
      setItems(previous => [
        {
          brief_id: result.brief_id,
          report_window: 'latest',
          generated_at: result.brief.generated_at,
          market_data_basis: result.brief.market_data_basis,
          provider_status: result.brief.provider_readiness?.status,
          coverage: result.brief.coverage,
        },
        ...previous.filter(item => item.brief_id !== result.brief_id),
      ])
      const replayMessage = result.replayed
        ? 'This brief was already in your archive; the immutable record was replayed.'
        : 'Market brief generated and added to the archive.'
      setAnnouncement(replayMessage)
    } catch (error: unknown) {
      const nextError = classifyMarketBriefError(error)
      setGenerationError(nextError)
      setAnnouncement(nextError.title)
    } finally {
      setGenerating(false)
    }
  }, [selectTab])

  const loadPulse = useCallback(async () => {
    if (pulseStatus === 'loading') return
    setPulseStatus('loading')
    setPulseError(null)
    try {
      const snapshot = await fetchMarketPulse()
      setPulse(snapshot)
      setPulseStatus('ready')
      setAnnouncement('Market pulse refreshed from server-owned evidence.')
    } catch (error: unknown) {
      const nextError = classifyMarketBriefError(error)
      setPulseError(nextError)
      setPulseStatus('error')
      setAnnouncement(nextError.title)
    }
  }, [pulseStatus])

  const onTabKeyDown = useCallback((event: React.KeyboardEvent<HTMLButtonElement>) => {
    const current = activeTab
    const ids = TABS.map(entry => entry.id)
    const index = ids.indexOf(current)
    if (event.key === 'ArrowRight') {
      event.preventDefault()
      const next = ids[(index + 1) % ids.length]
      selectTab(next)
      tabRefs.current[next]?.focus()
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault()
      const next = ids[(index - 1 + ids.length) % ids.length]
      selectTab(next)
      tabRefs.current[next]?.focus()
    } else if (event.key === 'Home') {
      event.preventDefault()
      selectTab(ids[0])
      tabRefs.current[ids[0]]?.focus()
    } else if (event.key === 'End') {
      event.preventDefault()
      selectTab(ids[ids.length - 1])
      tabRefs.current[ids[ids.length - 1]]?.focus()
    }
  }, [activeTab, selectTab])

  useEffect(() => {
    if ((activeTab === 'pulse' || activeTab === 'earnings' || activeTab === 'scanner') && pulseStatus === 'idle') {
      void loadPulse()
    }
  }, [activeTab, pulseStatus, loadPulse])

  const selectedMetadata = useMemo(() => items.find(item => item.brief_id === selectedId), [items, selectedId])
  const hasArchive = archiveStatus === 'ready' && items.length > 0
  const pageError = generationError ?? (detailStatus === 'error' ? detailError : null)
  const providerStatus = generating
    ? 'checking'
    : generationError
      ? (isProviderFailureReason(generationError.reasonCode) ? 'unavailable' : 'degraded')
      : brief?.provider_readiness?.status ?? 'not_checked'
  const providerStatusLabel = providerStatus === 'checking'
    ? 'Checking market data'
    : providerStatus === 'ready'
      ? 'Provider ready'
      : providerStatus === 'degraded'
        ? 'Coverage limited'
        : providerStatus === 'unavailable'
          ? 'Provider unavailable'
          : 'Provider not checked'
  const providerStatusExplanation = generating
    ? 'Atlas is checking current portfolio coverage and market-data availability.'
    : generationError
      ? generationError.message
      : brief?.provider_readiness?.status === 'ready'
        ? 'Provider readiness was verified by the server for this brief.'
        : brief?.provider_readiness?.status === 'degraded'
          ? 'The server reported limited portfolio coverage for this brief.'
          : brief?.provider_readiness?.status === 'unavailable'
            ? 'The server reported that market-data availability is unavailable for this brief.'
            : 'Generate a brief to verify current portfolio coverage and market-data availability.'

  return (
    <main aria-labelledby="market-intelligence-title" className="min-h-[calc(100vh-6rem)] print:mx-0">
      <div className="mx-auto max-w-[1440px]">
        <header className="flex flex-col gap-6 border-b border-[var(--border-subtle)] pb-7 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="label-sm text-[var(--primary-700)]">Evidence-first market intelligence</p>
            <h1 id="market-intelligence-title" className="display-md mt-2 text-balance text-[var(--text-primary)]">Market Intelligence</h1>
            <p className="mt-3 max-w-2xl text-base leading-relaxed text-[var(--text-secondary)]">What changed, why it matters, and what deserves your attention — from server-owned, source-cited evidence. Review before acting; Atlas never trades on your behalf.</p>
            {brief && <p className="mt-3 text-sm text-[var(--text-secondary)]">Last generated <time dateTime={brief.generated_at} className="font-medium text-[var(--text-primary)]">{formatDateTime(brief.generated_at)}</time></p>}
          </div>
          <div className="flex shrink-0 flex-col items-stretch gap-3 sm:flex-row sm:items-center">
            <div className="min-w-0" aria-label="Market data status">
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  variant={providerStatus === 'ready' ? 'success' : providerStatus === 'degraded' ? 'warning' : providerStatus === 'unavailable' ? 'danger' : 'neutral'}
                  size="md"
                  className={`normal-case tracking-normal ${providerStatus === 'degraded' ? 'market-brief-warning !bg-amber-100 !text-amber-900 dark:!bg-amber-900 dark:!text-amber-100' : ''}`}
                >
                  {providerStatusLabel}
                </Badge>
                {brief?.market_data_basis && brief.market_data_basis !== 'unknown' && <Badge variant={brief.market_data_basis === 'prior_close' ? 'warning' : 'info'} size="md" className={brief.market_data_basis === 'prior_close' ? 'market-brief-warning !bg-amber-100 !text-amber-900 dark:!bg-amber-900 dark:!text-amber-100' : ''}>{basisLabel(brief.market_data_basis)}</Badge>}
              </div>
              <p className="mt-2 max-w-sm text-xs leading-relaxed text-[var(--text-secondary)]">{providerStatusExplanation}</p>
            </div>
            <Button
              type="button"
              onClick={() => void generate()}
              disabled={generating}
              className="min-h-[44px] whitespace-nowrap !bg-[var(--interactive-primary)] !text-[var(--accent-on-primary)] hover:!bg-[var(--interactive-hover)]"
              icon={generating ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />}
            >
              {generating ? 'Generating brief…' : 'Generate brief'}
            </Button>
          </div>
        </header>

        <div role="tablist" aria-label="Market intelligence views" className="mt-6 flex flex-wrap gap-1 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--surface-color)] p-1">
          {TABS.map(tab => {
            const selected = activeTab === tab.id
            return (
              <button
                key={tab.id}
                ref={element => { tabRefs.current[tab.id] = element }}
                type="button"
                role="tab"
                id={`market-tab-${tab.id}`}
                aria-selected={selected}
                aria-controls={`market-panel-${tab.id}`}
                tabIndex={selected ? 0 : -1}
                onClick={() => selectTab(tab.id)}
                onKeyDown={onTabKeyDown}
                className={`min-h-[44px] flex-1 whitespace-nowrap rounded-[var(--radius-md)] px-3 py-2 text-sm font-medium transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--primary-500)] sm:flex-none sm:px-4 ${selected ? 'bg-[var(--interactive-primary)] text-[var(--accent-on-primary)]' : 'text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]'}`}
              >
                {tab.label}
              </button>
            )
          })}
        </div>

        {generationError && <div className="mt-6"><ErrorPanel error={generationError} onRetry={generationError.retryable ? () => void generate() : undefined} /></div>}
        {!generationError && pageError && detailStatus === 'error' && <div className="mt-6"><ErrorPanel error={pageError} onRetry={pageError.retryable && selectedId ? () => void open(selectedId) : undefined} /></div>}
        {archiveError && <div className="mt-6"><ErrorPanel error={archiveError} onRetry={() => void loadArchive()} /></div>}
        {pulseError && (activeTab === 'pulse' || activeTab === 'earnings' || activeTab === 'scanner') && <div className="mt-6"><ErrorPanel error={pulseError} onRetry={() => void loadPulse()} /></div>}
        {announcement && !generationError && !archiveError && !pulseError && detailStatus !== 'error' && announcement !== 'Loading saved market briefs…' && (
          <div className={`mt-6 flex items-center gap-2 rounded-[var(--radius-md)] border px-4 py-3 text-sm ${announcementTone(announcement)}`} role="status" aria-live="polite">
            <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{announcement}</span>
          </div>
        )}

        <div className="mt-8">
          {activeTab === 'portfolio' && (
          <div
            role="tabpanel"
            id="market-panel-portfolio"
            aria-labelledby="market-tab-portfolio"
            tabIndex={0}
          >
            {archiveStatus === 'loading' && !brief ? <LoadingSkeleton /> : (
              <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_21rem] lg:items-start">
                <section aria-labelledby="portfolio-brief-title" className="min-w-0">
                  {!brief && detailStatus === 'idle' && !generating && (
                    <EmptyState
                      focal
                      testId="portfolio-brief-empty"
                      title="Generate your first portfolio brief"
                      description="Atlas composes a deterministic, source-cited brief from server-owned market evidence — current quotes, company news, earnings, and filings for every safely covered holding. Nothing is saved until the server returns a trustworthy brief."
                      icon={<BarChart3 className="h-7 w-7" aria-hidden="true" />}
                      action={
                        <Button
                          type="button"
                          onClick={() => void generate()}
                          aria-label="Generate your first brief"
                          className="min-h-[44px] !bg-[var(--interactive-primary)] !text-[var(--accent-on-primary)] hover:!bg-[var(--interactive-hover)]"
                          icon={<RefreshCw className="h-4 w-4" aria-hidden="true" />}
                        >
                          Generate brief
                        </Button>
                      }
                      guidance={
                        <div className="grid gap-2 text-sm sm:grid-cols-3">
                          <div className="rounded-[var(--radius-md)] bg-[var(--bg-secondary)] p-3">
                            <p className="font-semibold text-[var(--text-primary)]">Coverage is server-verified</p>
                            <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">Holdings the provider cannot price are omitted with reasons — never silently guessed.</p>
                          </div>
                          <div className="rounded-[var(--radius-md)] bg-[var(--bg-secondary)] p-3">
                            <p className="font-semibold text-[var(--text-primary)]">Evidence stays cited</p>
                            <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">Every claim carries a source and freshness so you can verify it.</p>
                          </div>
                          <div className="rounded-[var(--radius-md)] bg-[var(--bg-secondary)] p-3">
                            <p className="font-semibold text-[var(--text-primary)]">Review, never execution</p>
                            <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">Atlas surfaces what to review; it never trades, moves money, or predicts returns.</p>
                          </div>
                        </div>
                      }
                    />
                  )}
                  {generating && (
                    <div className="flex items-start gap-3 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--surface-color)] p-6" role="status" aria-live="polite">
                      <Loader2 className="mt-0.5 h-6 w-6 shrink-0 animate-spin text-[var(--primary-600)]" aria-hidden="true" />
                      <div>
                        <h2 className="headline-sm text-[var(--text-primary)]">Checking market data</h2>
                        <p className="mt-2 max-w-xl text-sm leading-relaxed text-[var(--text-secondary)]">Atlas is assembling quotes, news, earnings, and filings for your holdings. This can take a moment on the server; your browser never sends holdings or provider configuration.</p>
                      </div>
                    </div>
                  )}
                  {detailStatus === 'loading' && <LoadingSkeleton />}
                  {brief && detailStatus === 'ready' && (
                    <article aria-labelledby="portfolio-brief-title">
                      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <p className="label-sm text-[var(--text-secondary)]">Selected briefing</p>
                          <h2 id="portfolio-brief-title" className="headline-lg mt-1 text-balance text-[var(--text-primary)]">Portfolio market review</h2>
                          <time dateTime={brief.as_of ?? brief.generated_at} className="mt-2 block text-sm text-[var(--text-secondary)]">As of {formatDateTime(brief.as_of ?? brief.generated_at)}</time>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {brief.market_data_basis && <Badge variant={brief.market_data_basis === 'prior_close' ? 'warning' : 'info'} className={brief.market_data_basis === 'prior_close' ? 'market-brief-warning !bg-amber-100 !text-amber-900 dark:!bg-amber-900 dark:!text-amber-100' : ''}>{basisLabel(brief.market_data_basis)}</Badge>}
                          {selectedMetadata?.report_window && <Badge variant="neutral">{selectedMetadata.report_window}</Badge>}
                        </div>
                      </div>
                      <ExecutiveSummary brief={brief} />
                      {brief.coverage && brief.coverage.omitted_holding_count > 0 && <CoveragePanel coverage={brief.coverage} />}
                      <CatalystStream evidence={brief.holding_evidence ?? []} />
                      <div className="mt-8 space-y-7 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--surface-color)] p-5 shadow-[var(--shadow-1)] sm:p-7">
                        {brief.sections.filter(section => !['actions_to_review', 'data_quality', 'catalyst_stream'].includes(section.name)).map(section => <BriefSectionView key={section.name} section={section} />)}
                      </div>
                      {brief.warnings.length > 0 && (
                        <section aria-labelledby="data-quality-title" className="mt-8 rounded-[var(--radius-lg)] border border-warning-200 bg-warning-50 p-5 sm:p-7">
                          <div className="flex items-start gap-3">
                            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warning-700" aria-hidden="true" />
                            <div className="min-w-0">
                              <h2 id="data-quality-title" className="headline-sm text-warning-900">Data-quality limitations</h2>
                              <p className="mt-1 text-sm leading-relaxed text-warning-900">These limitations are part of the brief&rsquo;s evidence boundary. The report is not complete portfolio coverage when holdings are omitted.</p>
                              <ul className="mt-4 space-y-2 text-sm text-warning-900">{brief.warnings.map((warning, index) => <li key={`${warning}-${index}`} className="flex items-start gap-2"><span aria-hidden="true">•</span><span>{warning}</span></li>)}</ul>
                            </div>
                          </div>
                        </section>
                      )}
                      <ActionsToReview actions={brief.actions ?? []} />
                    </article>
                  )}
                </section>
                <aside aria-label="Portfolio intelligence rail" className="space-y-4 lg:sticky lg:top-6">
                  {brief && detailStatus === 'ready' && (
                    <>
                      <EarningsRadar brief={brief} />
                      <RiskRadar brief={brief} />
                    </>
                  )}
                </aside>
              </div>
            )}
          </div>
          )}

          {activeTab === 'pulse' && (
          <div
            role="tabpanel"
            id="market-panel-pulse"
            aria-labelledby="market-tab-pulse"
            tabIndex={0}
          >
            {pulseStatus === 'idle' || pulseStatus === 'loading' ? <LoadingSkeleton /> : <PulseView pulse={pulse} onRefresh={() => void loadPulse()} />}
          </div>
          )}

          {activeTab === 'earnings' && (
          <div
            role="tabpanel"
            id="market-panel-earnings"
            aria-labelledby="market-tab-earnings"
            tabIndex={0}
          >
            <EarningsEventsView brief={brief} pulse={pulse} />
          </div>
          )}

          {activeTab === 'scanner' && (
          <div
            role="tabpanel"
            id="market-panel-scanner"
            aria-labelledby="market-tab-scanner"
            tabIndex={0}
          >
            <ScannerView pulse={pulse} onRefresh={() => void loadPulse()} />
          </div>
          )}

          {activeTab === 'archive' && (
          <div
            role="tabpanel"
            id="market-panel-archive"
            aria-labelledby="market-tab-archive"
            tabIndex={0}
          >
            <div className="grid gap-8 lg:grid-cols-[21rem_minmax(0,1fr)] lg:items-start">
              <aside aria-labelledby="archive-title">
                <Card className="border-[var(--border-subtle)] shadow-none" padding="compact">
                  <div className="flex items-start justify-between gap-3 border-b border-[var(--border-subtle)] pb-4">
                    <div>
                      <div className="flex items-center gap-2"><Archive className="h-5 w-5 text-[var(--primary-600)]" aria-hidden="true" /><h2 id="archive-title" className="headline-sm text-[var(--text-primary)]">Saved briefs</h2></div>
                      <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">Immutable reports stay available for review.</p>
                    </div>
                    {hasArchive && <span className="rounded-full bg-[var(--slate-100)] px-2 py-1 text-xs font-semibold text-[var(--text-secondary)]">{items.length}</span>}
                  </div>
                  <div className="pt-4">
                    {archiveStatus === 'loading' && <div className="space-y-2" role="status"><span className="sr-only">Loading saved briefs</span><div className="skeleton h-16 rounded-[var(--radius-md)]" /><div className="skeleton h-16 rounded-[var(--radius-md)]" /></div>}
                    {archiveStatus === 'ready' && items.length === 0 && <div className="rounded-[var(--radius-md)] bg-[var(--bg-secondary)] p-4 text-sm leading-relaxed text-[var(--text-secondary)]"><p className="font-semibold text-[var(--text-primary)]">No saved briefs yet.</p><p className="mt-2">Generate a brief on the My Portfolio tab; the immutable result will appear here.</p></div>}
                    {archiveStatus === 'ready' && items.length > 0 && <ArchiveList items={items} selectedId={selectedId} onSelect={id => void open(id)} />}
                  </div>
                </Card>
                <p className="mt-3 text-xs leading-relaxed text-[var(--text-secondary)]">Selecting a saved brief opens it in My Portfolio. Market data basis and coverage are server-reported.</p>
              </aside>
              <section aria-labelledby="archive-detail-title" className="min-w-0">
                {detailStatus === 'loading' && <LoadingSkeleton />}
                {brief && detailStatus === 'ready' && (
                  <article aria-labelledby="archive-detail-title">
                    <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                      <Archive className="h-4 w-4" aria-hidden="true" />
                      <span>Archived brief · <time dateTime={brief.generated_at}>{formatDateTime(brief.generated_at)}</time></span>
                    </div>
                    <ExecutiveSummary brief={brief} />
                    {brief.coverage && brief.coverage.omitted_holding_count > 0 && <CoveragePanel coverage={brief.coverage} />}
                    <div className="mt-6 space-y-7 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--surface-color)] p-5 shadow-[var(--shadow-1)] sm:p-7">
                      {brief.sections.filter(section => !['actions_to_review', 'data_quality'].includes(section.name)).map(section => <BriefSectionView key={section.name} section={section} />)}
                    </div>
                    {brief.warnings.length > 0 && (
                      <section aria-labelledby="archive-data-quality-title" className="mt-6 rounded-[var(--radius-lg)] border border-warning-200 bg-warning-50 p-5">
                        <div className="flex items-start gap-3">
                          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warning-700" aria-hidden="true" />
                          <div className="min-w-0">
                            <h2 id="archive-data-quality-title" className="headline-sm text-warning-900">Data-quality limitations</h2>
                            <ul className="mt-3 space-y-2 text-sm text-warning-900">{brief.warnings.map((warning, index) => <li key={`${warning}-${index}`} className="flex items-start gap-2"><span aria-hidden="true">•</span><span>{warning}</span></li>)}</ul>
                          </div>
                        </div>
                      </section>
                    )}
                  </article>
                )}
                {!brief && detailStatus === 'idle' && (
                  <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-color)] bg-[var(--bg-secondary)] px-6 py-10 text-center">
                    <Archive className="mx-auto h-8 w-8 text-[var(--text-tertiary)]" aria-hidden="true" />
                    <h2 id="archive-detail-title" className="headline-md mt-4 text-[var(--text-primary)]">Choose a saved brief</h2>
                    <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-[var(--text-secondary)]">Select an entry on the left to replay its immutable evidence, sources, and limitations.</p>
                  </div>
                )}
              </section>
            </div>
          </div>
          )}
        </div>
      </div>
    </main>
  )
}
