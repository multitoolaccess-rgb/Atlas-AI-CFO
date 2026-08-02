'use client'

/**
 * Phase 2 Slice 2 — Explainable Recommendation Card.
 *
 * Renders the deterministic Phase 2 recommendation envelope with:
 *   - Recommended action (``action_verb``).
 *   - Why now (``why_now`` ≤ 280 chars).
 *   - Expected impact (Decimal-string min/max range).
 *   - Risks (bounded token set; NEVER freeform user content).
 *   - Confidence (high | medium | low).
 *   - Source forecast version + freshness.
 *   - Bounded assumptions reference (SHA-256 digest only).
 *
 * Three bounded buttons fire Accept / Reject / Defer, each carrying
 * the bare ``decision_etag`` from the recommendation envelope. NO
 * "Approve" string is used to disambiguate from the existing
 * ``recommendation_logs.status="approved"`` column.
 *
 * After a successful journal write, the parent must pass ``recordedEntry``;
 * the card flips to a non-interactive "Recorded" state with the journal
 * entry id + decided_at timestamp. The page is the source of truth for
 * persistence across reloads — this card is intentionally ephemeral.
 *
 * Sibling to ``RecommendationCard.tsx`` (dashboard demo card);
 * deliberately does NOT modify that card.
 */

import { useState } from 'react'
import {
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  Loader2,
  Shield,
  Sparkles,
  X as XIcon,
} from 'lucide-react'
import { formatDecimalString } from '@/lib/format'

const formatNumber = formatDecimalString // Slice 2 alias preserving canonical Decimal.
import {
  type DecisionAction,
  type DecisionJournalEntryWire,
  type DeterministicRecommendationWire,
  type RecommendationConfidence,
  type RecommendationRiskToken,
} from '@/lib/api_phase2'

export interface RecommendationExplainedCardProps {
  recommendation: DeterministicRecommendationWire
  /** Source forecast version number — used in the freshness summary. */
  sourceVersionNumber: number
  /** Source forecast version calculated_at (UTF-8 RFC 3339 Z). */
  sourceCalculatedAt: string
  /** Source forecast version data_age_days. */
  sourceDataAgeDays: number
  /** Fired when the user clicks Accept/Reject/Defer. */
  onDecide: (
    action: DecisionAction,
    recommendation: DeterministicRecommendationWire,
  ) => void | Promise<void>
  /**
   * Set after a successful journal write. When non-null, the card
   * renders the bounded "Recorded" state and disables the action
   * buttons. The card itself does NOT enforce idempotency — that is
   * the parent's responsibility (via Slice 1 backend replay).
   */
  recordedEntry?: DecisionJournalEntryWire | null
  /** Disables all three buttons while a write is in-flight. */
  busy?: boolean
  /** Retries the same logical decision with its retained idempotency key. */
  onRetry?: () => void | Promise<void>
  /** Sanitized decision-write error for the accessible retry state. */
  decisionError?: string | null
}

const CONFIDENCE_STYLE: Record<
  RecommendationConfidence,
  { bg: string; text: string; border: string; label: string }
> = {
  high: {
    bg: 'bg-success-50',
    text: 'text-success-700',
    border: 'border-success-200',
    label: 'High confidence',
  },
  medium: {
    bg: 'bg-warning-50',
    text: 'text-warning-700',
    border: 'border-warning-200',
    label: 'Medium confidence',
  },
  low: {
    bg: 'bg-surface-container',
    text: 'text-on-surface-variant',
    border: 'border-outline-variant/20',
    label: 'Low confidence',
  },
}

const RISK_LABEL: Record<RecommendationRiskToken, string> = {
  liquidity_reduction: 'Liquidity reduction',
  reversibility_required: 'Reversibility required',
  concentration: 'Concentration',
  downside_amplification: 'Downside amplifier',
  stale_input: 'Stale input',
}

const ACTION_LABEL: Record<DecisionAction, string> = {
  accept: 'Accept recommendation',
  reject: 'Reject recommendation',
  defer: 'Defer recommendation',
}

function compactTimestamp(rfc3339: string): string {
  return rfc3339.replace('T', ' ').slice(0, 19) + 'Z'
}

function relativeDataAge(days: number): string {
  if (days <= 0) return 'today'
  if (days === 1) return '1 day ago'
  return `${days} days ago`
}

export default function RecommendationExplainedCard({
  recommendation,
  sourceVersionNumber,
  sourceCalculatedAt,
  sourceDataAgeDays,
  onDecide,
  recordedEntry,
  busy = false,
  onRetry,
  decisionError = null,
}: RecommendationExplainedCardProps) {
  const [showAssumptions, setShowAssumptions] = useState(false)

  const conf = CONFIDENCE_STYLE[recommendation.confidence]
  const recorded = recordedEntry != null
  const freshness = relativeDataAge(sourceDataAgeDays)

  // Recorded (post-write) state — non-interactive.
  if (recorded) {
    return (
      <article
        className="card p-6 mt-4 bg-success-50 border border-success-200"
        role="article"
        aria-label={`Recorded decision for ${recommendation.action_verb}`}
        data-testid={`recommendation-recorded-${recommendation.forecast_id}`}
      >
        <header className="flex items-center gap-3 mb-2">
          <Check
            className="w-5 h-5 text-success-600"
            aria-hidden="true"
          />
          <h3 className="text-base font-semibold text-primary">Recorded.</h3>
        </header>
        <p className="text-sm text-on-surface-variant mb-2">
          You decided{' '}
          <strong className="text-primary">
            {recommendation.action_verb}
          </strong>{' '}
          on this recommendation — stored in the immutable decision
          journal as entry{' '}
          <code
            className="text-[10px] tabular-nums break-all"
            data-testid="recorded-journal-id"
          >
            {recordedEntry.journal_entry_id}
          </code>
          .
        </p>
        <p
          className="text-xs text-on-surface-variant"
          data-testid="recorded-decided-at"
        >
          Decided at {compactTimestamp(recordedEntry.decided_at)}
        </p>
      </article>
    )
  }

  // Pre-write (interactive) state.
  return (
    <article
      className="card p-6 mt-4"
      role="article"
      aria-label={`Recommendation: ${recommendation.action_verb}`}
      data-testid={`recommendation-explained-card-${recommendation.forecast_id}`}
    >
      <header className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-3">
          <Sparkles
            className="w-5 h-5 text-primary"
            aria-hidden="true"
          />
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-primary-500">
              Recommendation
            </div>
            <h3
              className="text-lg font-semibold text-primary mt-1"
              data-testid="action-verb"
            >
              {recommendation.action_verb}
            </h3>
          </div>
        </div>
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[0.65rem] font-bold uppercase tracking-wider ${conf.bg} ${conf.text} ${conf.border}`}
          data-testid="confidence-tag"
          aria-label={conf.label}
        >
          {conf.label}
        </span>
      </header>

      <p
        className="text-sm text-secondary leading-relaxed mb-4"
        data-testid="why-now"
      >
        {recommendation.why_now}
      </p>

      <div className="bg-surface-container-low border border-outline-variant/20 rounded-lg p-3 mb-4">
        <div className="text-xs font-bold uppercase tracking-wider text-on-surface-variant mb-1">
          Expected impact
        </div>
        <p
          className="numeric-sm text-primary tabular-nums"
          data-testid="impact-range"
        >
          {formatNumber(
            recommendation.expected_impact_range.min_delta_decimal,
          )}
          {' '}—{' '}
          {formatNumber(
            recommendation.expected_impact_range.max_delta_decimal,
          )}
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4 text-xs">
        <div>
          <div className="font-bold uppercase tracking-wider text-on-surface-variant mb-1">
            Source forecast
          </div>
          <p
            className="text-primary tabular-nums"
            data-testid="source-version"
          >
            v#{sourceVersionNumber} · calculated{' '}
            {compactTimestamp(sourceCalculatedAt)}
          </p>
        </div>
        <div>
          <div className="font-bold uppercase tracking-wider text-on-surface-variant mb-1">
            Data freshness
          </div>
          <p
            className="text-primary"
            data-testid="source-freshness"
          >
            {freshness} ({sourceDataAgeDays} days)
          </p>
        </div>
      </div>

      {recommendation.risks.length > 0 && (
        <div className="mb-4">
          <div className="text-xs font-bold uppercase tracking-wider text-on-surface-variant mb-1.5">
            Risks
          </div>
          <ul
            className="flex flex-wrap gap-1.5"
            data-testid="risks-list"
          >
            {recommendation.risks.map((r) => (
              <li
                key={r}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[0.65rem] font-semibold bg-warning-50 text-warning-700 border border-warning-200"
                data-testid={`risk-${r}`}
              >
                <Shield
                  className="w-3 h-3"
                  aria-hidden="true"
                />
                {RISK_LABEL[r]}
              </li>
            ))}
          </ul>
        </div>
      )}

      <button
        type="button"
        onClick={() => setShowAssumptions((v) => !v)}
        className="inline-flex items-center gap-1.5 text-xs font-bold text-primary hover:text-primary-600 transition-colors mb-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500"
        aria-expanded={showAssumptions}
        aria-controls={`rec-assumptions-${recommendation.forecast_id}`}
        data-testid="assumptions-toggle"
      >
        {showAssumptions ? (
          <ChevronUp
            className="w-3.5 h-3.5"
            aria-hidden="true"
          />
        ) : (
          <ChevronDown
            className="w-3.5 h-3.5"
            aria-hidden="true"
          />
        )}
        View assumptions
      </button>

      {showAssumptions && (
        <section
          id={`rec-assumptions-${recommendation.forecast_id}`}
          className="mb-4 p-3 bg-surface-container-low rounded-lg border border-outline-variant/20 text-xs"
          data-testid="assumptions-panel"
        >
          <p className="text-on-surface-variant mb-2">
            Assumptions are referenced by a SHA-256 digest only — the
            immutable Phase 1 snapshot is the canonical source. No money
            value or statement data crosses the envelope boundary.
          </p>
          <code
            className="text-[10px] tabular-nums block break-all"
            data-testid="assumptions-hash"
          >
            {recommendation.assumptions_reference}
          </code>
        </section>
      )}

      {decisionError && (
        <div
          className="mb-4 flex items-start gap-3 p-3 rounded-lg bg-warning-50 text-warning-700 border border-warning-200"
          role="alert"
          data-testid="decision-error"
        >
          <p className="flex-1 text-sm">{decisionError}</p>
          {onRetry && (
            <button
              type="button"
              onClick={() => void onRetry()}
              disabled={busy}
              className="shrink-0 text-sm font-semibold underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-warning-500 disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label="Retry decision"
              data-testid="decision-retry"
            >
              Retry decision
            </button>
          )}
        </div>
      )}

      <div
        className="flex flex-col sm:flex-row gap-2 pt-4 border-t border-outline-variant/20"
        role="group"
        aria-label="Decision actions"
      >
        <button
          type="button"
          onClick={() => onDecide('accept', recommendation)}
          disabled={busy}
          aria-label={ACTION_LABEL.accept}
          data-testid="rec-accept"
          className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg font-semibold text-sm bg-success-500 hover:bg-success-600 text-text-on-brand disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-success-500"
        >
          {busy ? (
            <Loader2
              className="w-4 h-4 animate-spin"
              aria-hidden="true"
            />
          ) : (
            <Check
              className="w-4 h-4"
              aria-hidden="true"
            />
          )}
          Accept
        </button>
        <button
          type="button"
          onClick={() => onDecide('reject', recommendation)}
          disabled={busy}
          aria-label={ACTION_LABEL.reject}
          data-testid="rec-reject"
          className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg font-semibold text-sm bg-bg-primary text-primary border border-outline-variant hover:bg-surface-container-low disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500"
        >
          <XIcon
            className="w-4 h-4"
            aria-hidden="true"
          />
          Reject
        </button>
        <button
          type="button"
          onClick={() => onDecide('defer', recommendation)}
          disabled={busy}
          aria-label={ACTION_LABEL.defer}
          data-testid="rec-defer"
          className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg font-semibold text-sm bg-bg-primary text-primary border border-outline-variant hover:bg-surface-container-low disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500"
        >
          <Clock
            className="w-4 h-4"
            aria-hidden="true"
          />
          Defer
        </button>
      </div>
    </article>
  )
}
