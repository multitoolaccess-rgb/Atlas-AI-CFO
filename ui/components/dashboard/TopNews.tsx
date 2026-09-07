'use client'

import { ExternalLink, AlertCircle } from 'lucide-react'
import { formatCurrency } from '@/lib/format'
import { BriefNewsItem } from '@/lib/marketBriefs'

interface TopNewsProps {
  news: BriefNewsItem[]
  isLoading?: boolean
  onStoryClick?: (story: BriefNewsItem) => void
}

/**
 * TopNews - Material news stories for the portfolio
 * 
 * Displays:
 * - Top 3-5 material news stories
 * - Headlines with "why it matters" summary
 * - Source and timestamp
 * - Clickable cards with external link
 * - Empty state when no news available
 */
export default function TopNews({
  news,
  isLoading = false,
  onStoryClick,
}: TopNewsProps) {
  if (isLoading) {
    return (
      <div className="rounded-xl border border-outline-variant/20 p-6 bg-surface-container/30">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-secondary mb-4">
          YOUR NEWS
        </h2>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 bg-surface-container animate-pulse rounded-lg" />
          ))}
        </div>
      </div>
    )
  }

  if (!news || news.length === 0) {
    return (
      <div className="rounded-xl border border-outline-variant/20 p-6 bg-surface-container/30">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-secondary mb-4">
          YOUR NEWS
        </h2>
        <div className="flex items-center justify-center py-8 text-secondary">
          <p className="text-sm">No recent news for your portfolio</p>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-outline-variant/20 p-6 bg-surface-container/30">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-secondary mb-4">
        YOUR NEWS
      </h2>

      <div className="space-y-3">
        {news.map((story, idx) => (
          <NewsCard
            key={`${story.id}-${idx}`}
            story={story}
            onClick={() => onStoryClick?.(story)}
          />
        ))}
      </div>

      {news.length > 0 && (
        <button className="mt-4 w-full text-sm font-medium text-primary hover:opacity-80 transition-opacity">
          View all news →
        </button>
      )}
    </div>
  )
}

interface NewsCardProps {
  story: BriefNewsItem
  onClick?: () => void
}

function NewsCard({ story, onClick }: NewsCardProps) {
  const publishedTime = formatTimeAgo(story.published_at)

  return (
    <button
      onClick={onClick}
      className="w-full text-left p-3 rounded-lg border border-outline-variant/20 hover:bg-surface-container transition-colors group"
    >
      {/* Symbols and materiality */}
      <div className="flex items-center gap-2 mb-2">
        {story.symbols.map((symbol) => (
          <span
            key={symbol}
            className="inline-block px-2 py-1 text-xs font-semibold rounded bg-primary/10 text-primary"
          >
            {symbol}
          </span>
        ))}
        <MaterialityBadge score={story.materiality_score} />
      </div>

      {/* Headline */}
      <h3 className="font-semibold text-sm text-on-surface leading-snug mb-1 group-hover:text-primary transition-colors">
        {story.headline}
      </h3>

      {/* Why it matters */}
      {story.summary && (
        <p className="text-xs text-secondary leading-relaxed mb-2">
          <span className="font-medium">Why it matters:</span> {story.summary}
        </p>
      )}

      {/* Source and time */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-tertiary">
          {story.source} • {publishedTime}
        </p>
        <ExternalLink className="w-3 h-3 text-tertiary opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
    </button>
  )
}

function MaterialityBadge({ score }: { score: number }) {
  let color = 'bg-secondary/10 text-secondary'
  let label = 'Standard'

  if (score >= 0.9) {
    color = 'bg-danger-50 text-danger-600'
    label = 'Critical'
  } else if (score >= 0.7) {
    color = 'bg-warning-50 text-warning-600'
    label = 'High'
  } else if (score >= 0.5) {
    color = 'bg-success-50 text-success-600'
    label = 'Medium'
  }

  return (
    <span className={`ml-auto inline-block px-2 py-1 text-xs font-medium rounded ${color}`}>
      {label}
    </span>
  )
}

function formatTimeAgo(date: string | Date): string {
  const dateObj = typeof date === 'string' ? new Date(date) : date
  const now = new Date()
  const diffMs = now.getTime() - dateObj.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`

  return dateObj.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  })
}
