'use client'

/**
 * Phase 2 Slice 2 — Latest Forecast Card.
 *
 * Surfaces the persisted Phase 1 forecast version under a goal:
 *   - Goal target (canonical Decimal string from the goals endpoint).
 *   - Projected ending balance (canonical Decimal string from
 *     ``forecast_version.ending_balance`` — NEVER Number).
 *   - Probability / status (boolean from
 *     ``forecast_version.target_decision.target_status`` → bounded
 *     qualitative tag; NO Monte Carlo, NO LLM probability).
 *   - Forecast timestamp (RFC 3339 Z, server-truncated).
 *   - Data freshness (``drivers.data_age_days`` + bounded relative age).
 *
 * The "Why this projection?" expansion shows:
 *   - model_version, calculation_version, input_state_hash
 *     (NO money values or statement data — provenance contracts)
 *   - bounded scenarios (conservative | base | optimistic) summary
 *
 * Deliberately a NEW compliment to ``RecommendationCard.tsx`` — does
 * not modify the existing card so the dashboard ``/recommendations``
 * page demo continues to work.
 */

import { useState } from 'react'
import {
  ChevronDown,
  ChevronUp,
  Clock,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import { formatDecimalString } from '@/lib/format'

const formatNumber = formatDecimalString // Slice 2 alias preserving canonical Decimal.
import type {
  ForecastVersionWire,
  ForecastWire,
  LinkRel,
  ScenarioName,
} from '@/lib/api_phase2'

export interface LatestForecastCardProps {
  goalName: string
  /** Canonical Decimal string from the goals endpoint. */
  goalTargetAmount: string
  forecast: ForecastWire
  version: ForecastVersionWire
}

const STATUS_LABEL: Record<'on-track' | 'gap', string> = {
  'on-track': 'On track',
  gap: 'Gap remaining',
}

const SCENARIO_TESTID: Record<ScenarioName, string> = {
  conservative: 'scenario-conservative',
  base: 'scenario-base',
  optimistic: 'scenario-optimistic',
}

function compactAgeLabel(dataAgeDays: number): string {
  if (dataAgeDays <= 0) return 'today'
  if (dataAgeDays === 1) return '1 day ago'
  return `${dataAgeDays} days ago`
}

function shortTimestamp(rfc3339: string): string {
  // Render "<YYYY-MM-DD HH:MM:SS>Z" in a compact bordered form so the
  // card stays a single row on mobile.
  return rfc3339.replace('T', ' ').slice(0, 19) + 'Z'
}

export default function LatestForecastCard({
  goalName,
  goalTargetAmount,
  forecast,
  version,
}: LatestForecastCardProps) {
  const [expanded, setExpanded] = useState(false)

  const targetStatus = version.target_decision.target_status
  const statusKey: keyof typeof STATUS_LABEL = targetStatus
    ? 'on-track'
    : 'gap'
  const statusLabel = STATUS_LABEL[statusKey]
  const freshness = compactAgeLabel(version.drivers.data_age_days)

  const selfLink = forecast.links.find((l) => l.rel === ('self' satisfies LinkRel))
  void selfLink  // reserved for HATEOAS rendering in a follow-up slice

  return (
    <article
      className="card p-6 mt-4"
      role="article"
      aria-label={`Latest forecast for ${goalName}`}
      data-testid={`latest-forecast-card-${forecast.id}`}
    >
      <header className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          <Sparkles
            className="w-5 h-5 text-primary"
            aria-hidden="true"
          />
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-primary">
              Latest forecast
            </div>
            <h3 className="text-base font-semibold text-primary">
              {goalName}
            </h3>
          </div>
        </div>
        <span
          className={
            'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold ' +
            (targetStatus
              ? 'bg-success-50 text-success-700 border border-success-200'
              : 'bg-warning-50 text-warning-700 border border-warning-200')
          }
          data-testid="forecast-status-tag"
          aria-label={`Forecasting status ${statusLabel}`}
        >
          {targetStatus ? (
            <TrendingUp className="w-3 h-3" aria-hidden="true" />
          ) : (
            <TrendingDown className="w-3 h-3" aria-hidden="true" />
          )}
          {statusLabel}
        </span>
      </header>

      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
        <div>
          <dt className="text-[0.65rem] font-bold uppercase tracking-wider text-on-surface-variant">
            Goal target
          </dt>
          <dd
            className="numeric-md text-primary"
            data-testid="forecast-target"
          >
            {formatNumber(goalTargetAmount)}
          </dd>
        </div>
        <div>
          <dt className="text-[0.65rem] font-bold uppercase tracking-wider text-on-surface-variant">
            Projected ending balance
          </dt>
          <dd
            className="numeric-md text-primary"
            data-testid="forecast-projected"
          >
            {formatNumber(version.ending_balance)}
          </dd>
        </div>
      </dl>
      <div className="flex items-center gap-2 text-xs text-on-surface-variant mb-4">
        <Clock className="w-3.5 h-3.5" aria-hidden="true" />
        <span data-testid="forecast-timestamp">
          Forecast calculated {shortTimestamp(version.calculated_at)}
          {' '}· data {freshness} ({version.drivers.data_age_days} days)
        </span>
      </div>

      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="inline-flex items-center gap-1.5 text-xs font-bold text-primary hover:text-primary-600 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500"
        aria-expanded={expanded}
        aria-controls={`why-this-${forecast.id}`}
        data-testid="why-this-toggle"
      >
        {expanded ? (
          <ChevronUp className="w-3.5 h-3.5" aria-hidden="true" />
        ) : (
          <ChevronDown className="w-3.5 h-3.5" aria-hidden="true" />
        )}
        Why this projection?
      </button>

      {expanded && (
        <section
          id={`why-this-${forecast.id}`}
          className="mt-4 pt-4 border-t border-outline-variant/30 space-y-3"
          data-testid="why-this-panel"
        >
          <p className="text-xs text-on-surface-variant leading-relaxed">
            Based on the immutable Phase 1 forecast version{' '}
            <code
              className="text-[10px] tabular-nums"
              data-testid="forecast-version"
            >
              #{version.version_number}
            </code>
            {' '} — model{' '}
            <code className="text-[10px] tabular-nums">{version.model_version}</code>
            {' '} · calculation engine{' '}
            <code className="text-[10px] tabular-nums">{version.calculation_version}</code>
            {' '} · input state hash{' '}
            <code
              className="text-[10px] tabular-nums break-all"
              data-testid="forecast-hash"
            >
              {version.input_state_hash.slice(0, 8)}…
            </code>
          </p>
          <div className="grid grid-cols-3 gap-2 text-xs">
            {version.scenarios.map((s) => (
              <div
                key={s.name}
                className="flex flex-col gap-0.5 p-2.5 rounded-lg border border-outline-variant/20 bg-surface-container-low"
                data-testid={SCENARIO_TESTID[s.name]}
              >
                <span className="font-bold uppercase tracking-wider text-on-surface-variant text-[0.65rem]">
                  {s.name}
                </span>
                <span className="numeric-sm text-primary tabular-nums">
                  {formatNumber(s.ending_balance)}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </article>
  )
}
