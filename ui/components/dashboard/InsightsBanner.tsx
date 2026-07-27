'use client'

import { useState, useEffect } from 'react'
import { rulesService, type InsightItem } from '@/lib/api'
import { AlertTriangle, TrendingUp, TrendingDown, X } from 'lucide-react'

interface InsightsBannerProps {
  /** Max insights to show. Default 3. */
  limit?: number
}

const typeConfig = {
  warning: {
    bg: 'bg-warning-50',
    border: 'border-warning-200',
    icon: AlertTriangle,
    iconColor: 'text-warning-500',
    textColor: 'text-warning-700',
  },
  info: {
    bg: 'bg-info-50',
    border: 'border-info-200',
    icon: TrendingUp,
    iconColor: 'text-info-500',
    textColor: 'text-info-700',
  },
  success: {
    bg: 'bg-success-50',
    border: 'border-success-200',
    icon: TrendingDown,
    iconColor: 'text-success-500',
    textColor: 'text-success-700',
  },
}

export default function InsightsBanner({ limit = 3 }: InsightsBannerProps) {
  const [insights, setInsights] = useState<InsightItem[]>([])
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    let cancelled = false
    rulesService.getDashboardInsights().then(
      (data) => {
        if (!cancelled) setInsights(data.insights.slice(0, limit))
      },
      () => { /* silent fail — insights are non-critical */ },
    )
    return () => { cancelled = true }
  }, [limit])

  if (dismissed || insights.length === 0) return null

  return (
    <div className="space-y-2">
      {insights.map((insight, i) => {
        const config = typeConfig[insight.type] || typeConfig.info
        const Icon = config.icon
        return (
          <div
            key={`${insight.category}-${i}`}
            className={`flex items-center gap-3 p-3 rounded-lg border ${config.bg} ${config.border}`}
          >
            <Icon className={`w-4 h-4 shrink-0 ${config.iconColor}`} />
            <p className={`text-sm font-medium flex-1 ${config.textColor}`}>
              {insight.message}
            </p>
            <span className="text-xs font-bold tabular-nums text-on-surface-variant">
              {insight.change_pct > 0 ? '+' : ''}{insight.change_pct.toFixed(0)}%
            </span>
            {i === 0 && (
              <button
                onClick={() => setDismissed(true)}
                className="p-1 hover:bg-black/5 dark:hover:bg-white/5 rounded transition-colors"
                aria-label="Dismiss insights"
              >
                <X className="w-3 h-3 text-on-surface-variant" />
              </button>
            )}
          </div>
        )
      })}
    </div>
  )
}
