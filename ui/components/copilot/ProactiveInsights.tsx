'use client'

import { TrendingUp, AlertTriangle, Award, Sparkles, ArrowUpRight, ArrowDownRight } from 'lucide-react'

/**
 * Phase 4 — ProactiveInsights.
 *
 * Renders a stack of contextual AI insight cards derived from the
 * dashboard's existing ``InsightItem`` stream. Each card has a category
 * (opportunity / warning / achievement / info), a headline, a supporting
 * metric, and an optional "Ask Scout" action that forwards the insight
 * to the copilot as a pre-filled query.
 *
 * The cards use the Atlas accent palette:
 *   - opportunity → emerald wealth green
 *   - warning     → amber caution
 *   - achievement → gold premium
 *   - info        → electric blue
 *
 * data-testid surface:
 * - ``copilot-insights`` — the container
 * - ``copilot-insight-{i}`` — each card (0-indexed)
 * - ``copilot-insight-ask-{i}`` — the "Ask Scout" button on each card
 */

export type InsightCategory = 'opportunity' | 'warning' | 'achievement' | 'info'

export interface ProactiveInsight {
  category: InsightCategory
  headline: string
  /** Optional supporting metric, e.g. "$720/year" or "+18%". */
  metric?: string
  /** Longer context line. */
  detail?: string
  /** Pre-filled query to send to Scout when the user taps "Ask Scout". */
  askQuery?: string
}

interface ProactiveInsightsProps {
  insights: ProactiveInsight[]
  /** Called with the pre-filled query when "Ask Scout" is clicked. */
  onAsk?: (query: string) => void
  /** Max cards to render. Default 4. */
  maxItems?: number
  className?: string
}

// ---- Category config ---------------------------------------------------

const CATEGORY_CONFIG: Record<
  InsightCategory,
  { icon: typeof TrendingUp; color: string; bgColor: string; label: string }
> = {
  opportunity: {
    icon: TrendingUp,
    color: 'var(--success-600)',
    bgColor: 'color-mix(in srgb, var(--success-500) 10%, transparent)',
    label: 'Opportunity',
  },
  warning: {
    icon: AlertTriangle,
    color: 'var(--warning-600)',
    bgColor: 'color-mix(in srgb, var(--warning-500) 10%, transparent)',
    label: 'Heads up',
  },
  achievement: {
    icon: Award,
    color: 'var(--accent-gold, var(--warning-500))',
    bgColor: 'color-mix(in srgb, var(--accent-gold, var(--warning-500)) 12%, transparent)',
    label: 'Achievement',
  },
  info: {
    icon: Sparkles,
    color: 'var(--accent-electric)',
    bgColor: 'color-mix(in srgb, var(--accent-electric) 10%, transparent)',
    label: 'Insight',
  },
}

// ---- Component ---------------------------------------------------------

export default function ProactiveInsights({
  insights,
  onAsk,
  maxItems = 4,
  className,
}: ProactiveInsightsProps) {
  const visible = insights.slice(0, maxItems)

  if (visible.length === 0) {
    return (
      <div
        className={`px-4 py-6 text-center ${className ?? ''}`}
        data-testid="copilot-insights-empty"
      >
        <Sparkles
          className="w-6 h-6 mx-auto mb-2 text-[var(--text-tertiary)]"
          aria-hidden="true"
        />
        <p className="text-xs text-[var(--text-tertiary)]">
          No new insights. Scout is watching your cash flow.
        </p>
      </div>
    )
  }

  return (
    <div
      className={`flex flex-col gap-2 ${className ?? ''}`}
      data-testid="copilot-insights"
    >
      {visible.map((insight, i) => {
        const config = CATEGORY_CONFIG[insight.category]
        const Icon = config.icon
        return (
          <div
            key={`${insight.headline}-${i}`}
            className="rounded-[var(--radius-md)] p-3 transition-all duration-200"
            style={{ backgroundColor: config.bgColor }}
            data-testid={`copilot-insight-${i}`}
          >
            <div className="flex items-start gap-2.5">
              <span
                className="flex-shrink-0 w-7 h-7 rounded-lg flex items-center justify-center"
                style={{ backgroundColor: 'color-mix(in srgb, var(--bg-primary) 60%, transparent)' }}
              >
                <Icon
                  className="w-3.5 h-3.5"
                  style={{ color: config.color }}
                  aria-hidden="true"
                />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-0.5">
                  <span
                    className="text-[10px] font-semibold uppercase tracking-wider"
                    style={{ color: config.color }}
                  >
                    {config.label}
                  </span>
                  {insight.metric && (
                    <span
                      className="text-[10px] font-bold tabular-nums px-1.5 py-0.5 rounded-full"
                      style={{
                        backgroundColor: 'color-mix(in srgb, var(--bg-primary) 70%, transparent)',
                        color: config.color,
                      }}
                    >
                      {insight.metric}
                    </span>
                  )}
                </div>
                <p className="text-sm font-medium text-[var(--text-primary)] leading-snug">
                  {insight.headline}
                </p>
                {insight.detail && (
                  <p className="text-xs text-[var(--text-tertiary)] mt-0.5 leading-snug">
                    {insight.detail}
                  </p>
                )}
                {insight.askQuery && onAsk && (
                  <button
                    type="button"
                    onClick={() => onAsk(insight.askQuery!)}
                    className="mt-2 inline-flex items-center gap-1 text-xs font-medium
                               text-[var(--accent-electric)] hover:underline
                               transition-colors duration-150"
                    data-testid={`copilot-insight-ask-${i}`}
                  >
                    Ask Scout
                    <ArrowUpRight className="w-3 h-3" aria-hidden="true" />
                  </button>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ---- Derivation helper -------------------------------------------------

/**
 * Derive proactive insights from the dashboard's ``InsightItem`` stream.
 * The existing backend already produces category-tagged insights with
 * change percentages; we map them into the card schema above and add
 * pre-filled Scout queries for actionable ones.
 */
import type { InsightItem } from '@/lib/api'

export function deriveProactiveInsights(
  insights: InsightItem[],
  summary?: { total_income_month?: number; total_expenses_month?: number; total_balance?: number } | null,
): ProactiveInsight[] {
  return insights.slice(0, 8).map((raw) => {
    const isUp = raw.change_pct > 0
    const metric = `${isUp ? '+' : ''}${raw.change_pct.toFixed(0)}%`
    const category: InsightCategory =
      raw.type === 'warning' ? 'warning'
        : raw.type === 'success' ? 'achievement'
          : 'opportunity'

    // Build a pre-filled Scout query from the category + label.
    const askQuery =
      category === 'warning'
        ? `Why did my ${raw.category} spending go ${isUp ? 'up' : 'down'} ${Math.abs(raw.change_pct).toFixed(0)}%?`
        : category === 'achievement'
          ? `Tell me more about my ${raw.category} progress.`
          : `What can I do about my ${raw.category} trend?`

    return {
      category,
      headline: raw.message,
      metric,
      detail: `${raw.category} · ${raw.current.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })} vs ${raw.previous.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })}`,
      askQuery,
    }
  })
}
