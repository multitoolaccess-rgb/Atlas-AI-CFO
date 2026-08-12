'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  Archive,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  FileText,
  Loader2,
  Newspaper,
  RefreshCw,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  WifiOff,
  XCircle,
} from 'lucide-react'
import Button from '@/components/ui/Button'
import Badge from '@/components/ui/Badge'
import Card from '@/components/ui/Card'
import {
  classifyMarketBriefError,
  generateMarketBrief,
  getMarketBrief,
  listMarketBriefs,
  type BriefIndex,
  type BriefSection,
  type Citation,
  type CoverageSummary,
  type MarketBrief,
  type MarketBriefErrorState,
  type MarketBriefReasonCode,
  type PriceBasis,
} from '@/lib/marketBriefs'

const SECTION_LABELS: Record<string, string> = {
  executive_summary: 'Executive summary',
  portfolio_changes: 'Portfolio changes',
  material_holding_news: 'Material portfolio news',
  earnings: 'Earnings',
  sec_filings: 'SEC filings',
  risks_and_opportunities: 'Risks and opportunities',
  actions_to_review: 'Actions to review',
  sources: 'Sources',
  data_quality: 'Data-quality limitations',
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
    <div className="space-y-4" aria-label="Loading market brief" role="status">
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

function ExecutiveSummary({ brief }: { brief: MarketBrief }) {
  const portfolio = sectionByName(brief, 'portfolio_changes')
  const news = sectionByName(brief, 'material_holding_news')
  const earnings = sectionByName(brief, 'earnings')
  const filings = sectionByName(brief, 'sec_filings')
  const upcoming = earnings?.content.filter(item => item.startsWith('upcoming:') || item.startsWith('today:')).length ?? 0
  const recent = earnings?.content.filter(item => item.startsWith('recent')).length ?? 0
  const cards = [
    brief.portfolio_daily_change != null && portfolio?.content.length
      ? <SummaryCard key="movement" label="Portfolio movement" value={brief.portfolio_daily_change} detail="Comparable source-backed change" icon={brief.portfolio_daily_change.startsWith('-') ? TrendingDown : TrendingUp} tone={brief.portfolio_daily_change.startsWith('-') ? 'warning' : 'positive'} />
      : null,
    brief.coverage
      ? <SummaryCard key="coverage" label="Portfolio covered" value={coveragePercent(brief.coverage)} detail={`${brief.coverage.covered_holding_count} of ${brief.coverage.eligible_holding_count} eligible holdings · ${brief.coverage.coverage_basis.replace('_', ' ')}`} icon={ShieldCheck} tone={brief.coverage.omitted_holding_count ? 'warning' : 'positive'} />
      : null,
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
          <h2 id="brief-summary-title" className="headline-md mt-1 text-[var(--text-primary)]">What changed in this brief</h2>
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
                <li key={`${omission.symbol}-${omission.reason_code}-${index}`} className="flex items-start gap-2">
                  <CircleHelp className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                  <span><strong>{omission.symbol}</strong> — {reasonLabel(omission.reason_code)}</span>
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

export default function MarketBriefArchive() {
  const [items, setItems] = useState<BriefIndex[]>([])
  const [brief, setBrief] = useState<MarketBrief | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [archiveStatus, setArchiveStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [archiveError, setArchiveError] = useState<MarketBriefErrorState | null>(null)
  const [detailStatus, setDetailStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [detailError, setDetailError] = useState<MarketBriefErrorState | null>(null)
  const [generating, setGenerating] = useState(false)
  const [generationError, setGenerationError] = useState<MarketBriefErrorState | null>(null)
  const [announcement, setAnnouncement] = useState('Loading saved market briefs…')
  const detailRequest = useRef(0)

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
  }, [])

  const selectedMetadata = useMemo(() => items.find(item => item.brief_id === selectedId), [items, selectedId])
  const hasArchive = archiveStatus === 'ready' && items.length > 0
  const pageError = generationError ?? (detailStatus === 'error' ? detailError : null)

  return (
    <main aria-labelledby="market-brief-title" className="min-h-[calc(100vh-6rem)] print:mx-0">
      <div className="mx-auto max-w-[1440px]">
        <header className="flex flex-col gap-6 border-b border-[var(--border-subtle)] pb-7 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="label-sm text-[var(--primary-700)]">Evidence-first market context</p>
            <h1 id="market-brief-title" className="display-md mt-2 text-balance text-[var(--text-primary)]">Market Intelligence Briefs</h1>
            <p className="mt-3 max-w-2xl text-base leading-relaxed text-[var(--text-secondary)]">A deterministic, source-cited briefing for your active portfolio. Review the evidence and limitations before deciding what deserves your attention.</p>
            {brief && <p className="mt-3 text-sm text-[var(--text-secondary)]">Last generated <time dateTime={brief.generated_at} className="font-medium text-[var(--text-primary)]">{formatDateTime(brief.generated_at)}</time></p>}
          </div>
          <div className="flex shrink-0 flex-col items-stretch gap-3 sm:flex-row sm:items-center">
            <div className="flex flex-wrap items-center gap-2" aria-label="Market data status">
              <Badge
                variant={brief?.provider_readiness?.status === 'ready' ? 'success' : brief?.provider_readiness?.status === 'degraded' ? 'warning' : 'neutral'}
                size="md"
                className={brief?.provider_readiness?.status === 'degraded' ? 'market-brief-warning !bg-amber-100 !text-amber-900 dark:!bg-amber-900 dark:!text-amber-100' : ''}
              >
                {brief?.provider_readiness?.status === 'ready' ? 'Provider ready' : brief?.provider_readiness?.status === 'degraded' ? 'Coverage limited' : 'Provider status unknown'}
              </Badge>
              {brief?.market_data_basis && brief.market_data_basis !== 'unknown' && <Badge variant={brief.market_data_basis === 'prior_close' ? 'warning' : 'info'} size="md" className={brief.market_data_basis === 'prior_close' ? 'market-brief-warning !bg-amber-100 !text-amber-900 dark:!bg-amber-900 dark:!text-amber-100' : ''}>{basisLabel(brief.market_data_basis)}</Badge>}
            </div>
            <Button
              type="button"
              onClick={() => void generate()}
              disabled={generating}
              className="min-h-[44px] whitespace-nowrap !bg-[var(--interactive-primary)] !text-[var(--text-on-brand)] hover:!bg-[var(--interactive-hover)]"
              icon={generating ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />}
            >
              {generating ? 'Generating brief…' : 'Generate brief'}
            </Button>
          </div>
        </header>

        {generationError && <div className="mt-6"><ErrorPanel error={generationError} onRetry={generationError.retryable ? () => void generate() : undefined} /></div>}
        {!generationError && pageError && detailStatus === 'error' && <div className="mt-6"><ErrorPanel error={pageError} onRetry={pageError.retryable && selectedId ? () => void open(selectedId) : undefined} /></div>}
        {archiveError && <div className="mt-6"><ErrorPanel error={archiveError} onRetry={() => void loadArchive()} /></div>}
        {announcement && !generationError && !archiveError && detailStatus !== 'error' && announcement !== 'Loading saved market briefs…' && (
          <div className={`mt-6 flex items-center gap-2 rounded-[var(--radius-md)] border px-4 py-3 text-sm ${announcementTone(announcement)}`} role="status" aria-live="polite">
            <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{announcement}</span>
          </div>
        )}

        {archiveStatus === 'loading' && !brief ? <div className="mt-8"><LoadingSkeleton /></div> : (
          <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_21rem] lg:items-start">
            <section aria-labelledby="brief-detail-title" className="min-w-0 lg:order-1">
              {!brief && detailStatus === 'idle' && (
                <Card className="border-[var(--border-subtle)] shadow-none" padding="large">
                  <div className="flex flex-col items-center text-center">
                    <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary-50 text-[var(--primary-700)]"><BarChart3 className="h-7 w-7" aria-hidden="true" /></div>
                    <h2 id="brief-detail-title" className="headline-md mt-5 text-[var(--text-primary)]">Choose a saved brief or generate a new one</h2>
                    <p className="mt-3 max-w-xl text-sm leading-relaxed text-[var(--text-secondary)]">Atlas keeps each generated brief immutable. Start with a new server-composed report or select an archive entry to review its sources, coverage, and limitations.</p>
                  </div>
                </Card>
              )}
              {detailStatus === 'loading' && <LoadingSkeleton />}
              {brief && detailStatus === 'ready' && (
                <article aria-labelledby="brief-detail-title">
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="label-sm text-[var(--text-secondary)]">Selected briefing</p>
                      <h2 id="brief-detail-title" className="headline-lg mt-1 text-balance text-[var(--text-primary)]">Portfolio market review</h2>
                      <time dateTime={brief.as_of ?? brief.generated_at} className="mt-2 block text-sm text-[var(--text-secondary)]">As of {formatDateTime(brief.as_of ?? brief.generated_at)}</time>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {brief.market_data_basis && <Badge variant={brief.market_data_basis === 'prior_close' ? 'warning' : 'info'} className={brief.market_data_basis === 'prior_close' ? 'market-brief-warning !bg-amber-100 !text-amber-900 dark:!bg-amber-900 dark:!text-amber-100' : ''}>{basisLabel(brief.market_data_basis)}</Badge>}
                      {selectedMetadata?.report_window && <Badge variant="neutral">{selectedMetadata.report_window}</Badge>}
                    </div>
                  </div>
                  <ExecutiveSummary brief={brief} />
                  {brief.coverage && brief.coverage.omitted_holding_count > 0 && <CoveragePanel coverage={brief.coverage} />}
                  <div className="mt-8 space-y-7 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] bg-[var(--surface-color)] p-5 shadow-[var(--shadow-1)] sm:p-7">
                    {brief.sections.filter(section => !['actions_to_review', 'data_quality'].includes(section.name)).map(section => <BriefSectionView key={section.name} section={section} />)}
                  </div>
                  {brief.warnings.length > 0 && (
                    <section aria-labelledby="data-quality-title" className="mt-8 rounded-[var(--radius-lg)] border border-warning-200 bg-warning-50 p-5 sm:p-7">
                      <div className="flex items-start gap-3">
                        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warning-700" aria-hidden="true" />
                        <div className="min-w-0">
                          <h2 id="data-quality-title" className="headline-sm text-warning-900">Data-quality limitations</h2>
                          <p className="mt-1 text-sm leading-relaxed text-warning-900">These limitations are part of the brief’s evidence boundary. The report is not complete portfolio coverage when holdings are omitted.</p>
                          <ul className="mt-4 space-y-2 text-sm text-warning-900">{brief.warnings.map((warning, index) => <li key={`${warning}-${index}`} className="flex items-start gap-2"><span aria-hidden="true">•</span><span>{warning}</span></li>)}</ul>
                        </div>
                      </div>
                    </section>
                  )}
                  <ActionsToReview actions={brief.actions ?? []} />
                </article>
              )}
            </section>

            <aside aria-labelledby="archive-title" className="lg:order-2 lg:sticky lg:top-6">
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
                  {archiveStatus === 'ready' && items.length === 0 && <div className="rounded-[var(--radius-md)] bg-[var(--bg-secondary)] p-4 text-sm leading-relaxed text-[var(--text-secondary)]"><p className="font-semibold text-[var(--text-primary)]">No saved briefs yet.</p><p className="mt-2">Generate a brief when the server-side provider is ready. The archive will preserve the immutable result here.</p></div>}
                  {archiveStatus === 'ready' && items.length > 0 && <ArchiveList items={items} selectedId={selectedId} onSelect={id => void open(id)} />}
                </div>
              </Card>
              <p className="mt-3 text-xs leading-relaxed text-[var(--text-secondary)]">Market data basis and coverage are server-reported. Browser time does not decide quote freshness.</p>
            </aside>
          </div>
        )}
      </div>
    </main>
  )
}
