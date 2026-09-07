'use client'

import { Calendar, TrendingUp } from 'lucide-react'
import { BriefEarningsEvent } from '@/lib/marketBriefs'

interface EarningsCalendarProps {
  earnings: BriefEarningsEvent[]
  isLoading?: boolean
  onEarningClick?: (earning: BriefEarningsEvent) => void
}

/**
 * EarningsCalendar - Upcoming earnings timeline for portfolio holdings
 * 
 * Displays:
 * - Earnings events in next 7 days
 * - Date, symbol, EPS estimate vs whisper
 * - Confidence indicator (high/medium/low probability)
 * - Visual timeline layout
 * - Empty state when no earnings
 */
export default function EarningsCalendar({
  earnings,
  isLoading = false,
  onEarningClick,
}: EarningsCalendarProps) {
  if (isLoading) {
    return (
      <div className="rounded-xl border border-outline-variant/20 p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-secondary mb-4">
          EARNINGS THIS WEEK
        </h2>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-surface-container animate-pulse rounded-lg" />
          ))}
        </div>
      </div>
    )
  }

  if (!earnings || earnings.length === 0) {
    return (
      <div className="rounded-xl border border-outline-variant/20 p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-secondary mb-4">
          EARNINGS THIS WEEK
        </h2>
        <div className="flex items-center justify-center py-8 text-secondary">
          <Calendar className="w-4 h-4 mr-2" aria-hidden="true" />
          <p className="text-sm">No earnings scheduled this week</p>
        </div>
      </div>
    )
  }

  // Sort by date
  const sortedEarnings = [...earnings].sort((a, b) => 
    new Date(a.date).getTime() - new Date(b.date).getTime()
  )

  return (
    <div className="rounded-xl border border-outline-variant/20 p-6">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-secondary mb-4">
        EARNINGS THIS WEEK
      </h2>

      <div className="space-y-3">
        {sortedEarnings.map((earning, idx) => (
          <EarningsRow
            key={`${earning.symbol}-${earning.date}`}
            earning={earning}
            onClick={() => onEarningClick?.(earning)}
          />
        ))}
      </div>
    </div>
  )
}

interface EarningsRowProps {
  earning: BriefEarningsEvent
  onClick?: () => void
}

function EarningsRow({ earning, onClick }: EarningsRowProps) {
  const dateStr = formatEarningsDate(earning.date)
  const confidenceLevel = getConfidenceLevel(earning.confidence)

  return (
    <button
      onClick={onClick}
      className="w-full text-left p-3 rounded-lg border border-outline-variant/20 hover:bg-surface-container transition-colors group"
    >
      <div className="flex items-center gap-3">
        {/* Date column */}
        <div className="w-24 flex-shrink-0">
          <p className="text-xs font-semibold text-secondary uppercase tracking-wide">
            {dateStr}
          </p>
        </div>

        {/* Symbol and name */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-on-surface">
            {earning.symbol}
          </p>
          <p className="text-xs text-secondary truncate">
            {earning.name}
          </p>
        </div>

        {/* EPS data */}
        <div className="flex-shrink-0 text-right">
          <p className="text-xs text-secondary">
            EPS: <span className="font-mono font-semibold text-on-surface">${earning.eps_estimate?.toFixed(2) || 'TBD'}</span>
          </p>
          {earning.eps_whisper && earning.eps_estimate && (
            <p className="text-xs text-tertiary">
              Whisper: ${earning.eps_whisper.toFixed(2)}
            </p>
          )}
        </div>

        {/* Confidence bar */}
        <div className="flex-shrink-0 ml-2">
          <ConfidenceBar level={earning.confidence} />
        </div>
      </div>
    </button>
  )
}

function ConfidenceBar({ level }: { level: string }) {
  const bars = level === 'high' ? 3 : level === 'medium' ? 2 : 1
  const color = level === 'high' ? 'text-success-500' : level === 'medium' ? 'text-warning-500' : 'text-secondary'

  return (
    <div className={`flex items-center gap-0.5 ${color}`}>
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className={`w-1 h-4 rounded-sm transition-colors ${
            i <= bars ? 'bg-current' : 'bg-outline-variant/20'
          }`}
        />
      ))}
    </div>
  )
}

function formatEarningsDate(date: Date | string): string {
  const dateObj = typeof date === 'string' ? new Date(date) : date
  const now = new Date()
  const tomorrow = new Date(now)
  tomorrow.setDate(tomorrow.getDate() + 1)

  if (dateObj.toDateString() === now.toDateString()) {
    return 'TODAY'
  }

  if (dateObj.toDateString() === tomorrow.toDateString()) {
    return 'TOMORROW'
  }

  return dateObj.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  }).toUpperCase()
}

function getConfidenceLevel(confidence: string): number {
  switch (confidence.toLowerCase()) {
    case 'high':
      return 3
    case 'medium':
      return 2
    case 'low':
      return 1
    default:
      return 1
  }
}
