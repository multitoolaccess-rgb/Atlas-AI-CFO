'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Sparkles,
  CheckCircle2,
  XCircle,
  X,
  Clock,
  TrendingUp,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { Button } from '@/components/ui'
import {
  rulesService,
  type RecommendationLogItem,
} from '@/lib/api'

interface ApprovalQueueProps {
  /** Pre-fetched items (optional — component fetches its own if omitted). */
  items?: RecommendationLogItem[]
  /** Pre-fetched pending count. */
  pendingCount?: number
  loading?: boolean
}

const PRIORITY_STYLES: Record<string, { badge: string; border: string }> = {
  high: {
    badge: 'bg-[var(--danger-100)] text-[var(--danger-700)]',
    border: 'border-l-[var(--danger-500)]',
  },
  medium: {
    badge: 'bg-[var(--warning-100)] text-[var(--warning-700)]',
    border: 'border-l-[var(--warning-500)]',
  },
  low: {
    badge: 'bg-[var(--info-100)] text-[var(--info-700)]',
    border: 'border-l-[var(--info-500)]',
  },
}

const STATUS_ICONS: Record<string, React.ReactNode> = {
  approved: <CheckCircle2 className="w-3.5 h-3.5 text-[var(--success-600)]" />,
  denied: <XCircle className="w-3.5 h-3.5 text-[var(--danger-600)]" />,
  dismissed: <X className="w-3.5 h-3.5 text-[var(--text-tertiary)]" />,
}

function formatRelativeTime(iso: string): string {
  const now = Date.now()
  const then = new Date(iso).getTime()
  const diffMs = now - then
  const diffMins = Math.floor(diffMs / 60000)
  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  return `${diffDays}d ago`
}

export default function ApprovalQueue({
  items: propItems,
  pendingCount: propPendingCount,
  loading: propLoading,
}: ApprovalQueueProps) {
  const [items, setItems] = useState<RecommendationLogItem[]>(propItems ?? [])
  const [pendingCount, setPendingCount] = useState(propPendingCount ?? 0)
  const [loading, setLoading] = useState(propLoading ?? !propItems)
  const [actingId, setActingId] = useState<number | null>(null)
  const [filter, setFilter] = useState<'pending' | 'all'>('pending')
  const [expanded, setExpanded] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [listRes, statsRes] = await Promise.all([
        rulesService.listRecommendations({
          status: filter === 'pending' ? 'pending' : undefined,
          limit: 50,
        }),
        rulesService.getRecommendationStats(),
      ])
      setItems(listRes.items)
      setPendingCount(statsRes.pending)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? 'Failed to load recommendations.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    // When the parent provides items, trust them — don't fetch.
    if (propItems) {
      setItems(propItems)
      setPendingCount(propPendingCount ?? 0)
      setLoading(propLoading ?? false)
      return
    }
    fetchData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [propItems, propPendingCount, propLoading, filter])

  const handleAction = async (
    id: number,
    action: 'approve' | 'deny' | 'dismiss',
  ) => {
    setActingId(id)
    setError(null)
    try {
      await rulesService.takeRecommendationAction(id, action)
      // Map action verb to the status enum value stored on the model.
      const newStatus =
        action === 'approve'
          ? 'approved'
          : action === 'deny'
            ? 'denied'
            : 'dismissed'
      // Remove from list if filtering by pending
      if (filter === 'pending') {
        setItems((prev) => prev.filter((i) => i.id !== id))
      } else {
        setItems((prev) =>
          prev.map((i) =>
            i.id === id
              ? {
                  ...i,
                  status: newStatus as RecommendationLogItem['status'],
                  resolved_at: new Date().toISOString(),
                  resolved_by: 'user',
                }
              : i,
          ),
        )
      }
      // Only decrement pending count when the acted-on item was actually
      // pending. Prevents count drift in the "Show all" view.
      const actedItem = items.find((i) => i.id === id)
      if (actedItem?.status === 'pending') {
        setPendingCount((c) => Math.max(0, c - 1))
      }
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? `Failed to ${action} recommendation.`
      setError(msg)
    } finally {
      setActingId(null)
    }
  }

  const pendingItems = items.filter((i) => i.status === 'pending')
  const resolvedItems = items.filter((i) => i.status !== 'pending')

  return (
    <div
      className="card p-6"
      data-testid="approval-queue"
      role="region"
      aria-label="Recommendation approval queue"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[var(--primary-50)] flex items-center justify-center border border-[var(--primary-200)]">
            <Sparkles
              className="w-4 h-4 text-[var(--primary-600)]"
              aria-hidden="true"
            />
          </div>
          <div>
            <h3 className="headline-md text-[var(--text-primary)]">
              Approval Queue
            </h3>
            <p className="text-xs text-[var(--text-tertiary)]">
              {pendingCount > 0
                ? `${pendingCount} pending recommendation${pendingCount !== 1 ? 's' : ''}`
                : 'No pending recommendations'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setFilter(filter === 'pending' ? 'all' : 'pending')}
            className="label-sm text-[var(--text-tertiary)] hover:text-[var(--primary-600)] transition-colors px-2 py-1 rounded-[var(--radius-sm)] hover:bg-[var(--primary-50)]"
            data-testid="approval-queue-filter-toggle"
          >
            {filter === 'pending' ? 'Show all' : 'Pending only'}
          </button>
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="p-1 rounded-[var(--radius-sm)] text-[var(--text-tertiary)] hover:text-[var(--primary-600)] hover:bg-[var(--primary-50)] transition-colors"
            aria-label={expanded ? 'Collapse queue' : 'Expand queue'}
            data-testid="approval-queue-toggle"
          >
            {expanded ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div
          className="mb-4 p-3 rounded-[var(--radius-md)] bg-[var(--warning-50)] text-[var(--warning-700)] border border-[var(--warning-200)] text-sm"
          role="alert"
          data-testid="approval-queue-error"
        >
          {error}
        </div>
      )}

      {/* Content */}
      {expanded && (
        <>
          {loading ? (
            <div className="flex items-center gap-2 py-8 justify-center">
              <Clock className="w-4 h-4 animate-spin text-[var(--primary-600)]" />
              <span className="text-sm text-[var(--text-secondary)]">
                Loading recommendations…
              </span>
            </div>
          ) : items.length === 0 ? (
            <div className="py-8 text-center" data-testid="approval-queue-empty">
              <CheckCircle2 className="w-8 h-8 text-[var(--success-400)] mx-auto mb-2" />
              <p className="text-sm text-[var(--text-secondary)]">
                {filter === 'pending'
                  ? 'All caught up — no pending recommendations.'
                  : 'No recommendations yet.'}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {/* Pending items */}
              {pendingItems.map((item) => (
                <RecommendationRow
                  key={item.id}
                  item={item}
                  acting={actingId === item.id}
                  onAction={handleAction}
                />
              ))}

              {/* Resolved items (when showing all) */}
              {filter === 'all' && resolvedItems.length > 0 && (
                <>
                  <div className="flex items-center gap-2 pt-2">
                    <div className="flex-1 h-px bg-[var(--border-subtle)]" />
                    <span className="label-sm text-[var(--text-tertiary)]">
                      Resolved
                    </span>
                    <div className="flex-1 h-px bg-[var(--border-subtle)]" />
                  </div>
                  {resolvedItems.map((item) => (
                    <RecommendationRow
                      key={item.id}
                      item={item}
                      acting={false}
                      onAction={handleAction}
                      resolved
                    />
                  ))}
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function RecommendationRow({
  item,
  acting,
  onAction,
  resolved = false,
}: {
  item: RecommendationLogItem
  acting: boolean
  onAction: (id: number, action: 'approve' | 'deny' | 'dismiss') => void
  resolved?: boolean
}) {
  const style = PRIORITY_STYLES[item.priority] ?? PRIORITY_STYLES.medium

  return (
    <div
      className={`
        p-4 rounded-[var(--radius-md)] border-l-4 ${style.border}
        bg-[var(--bg-secondary)] border border-[var(--border-subtle)]
        transition-opacity duration-200
        ${resolved ? 'opacity-60' : ''}
      `}
      data-testid={`approval-queue-item-${item.id}`}
      role="article"
      aria-label={`${item.priority} priority: ${item.title}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span
              className={`label-sm px-1.5 py-0.5 rounded ${style.badge}`}
              data-testid={`approval-queue-priority-${item.id}`}
            >
              {item.priority}
            </span>
            <span className="label-sm text-[var(--text-tertiary)]">
              {item.category}
            </span>
            <span className="text-xs text-[var(--text-disabled)]">
              {formatRelativeTime(item.created_at)}
            </span>
          </div>
          <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-1 truncate">
            {item.title}
          </h4>
          {item.description && (
            <p className="text-xs text-[var(--text-secondary)] leading-relaxed line-clamp-2">
              {item.description}
            </p>
          )}
          {item.impact && (
            <div className="mt-2 flex items-center gap-1.5">
              {item.priority === 'high' ? (
                <AlertTriangle
                  className="w-3 h-3 text-[var(--warning-600)]"
                  aria-hidden="true"
                />
              ) : (
                <TrendingUp
                  className="w-3 h-3 text-[var(--success-600)]"
                  aria-hidden="true"
                />
              )}
              <span className="text-xs font-medium text-[var(--text-secondary)]">
                Impact: {item.impact}
              </span>
            </div>
          )}
        </div>

        {/* Actions */}
        {resolved ? (
          <div className="flex items-center gap-1.5 shrink-0">
            {STATUS_ICONS[item.status]}
            <span className="label-sm text-[var(--text-tertiary)] capitalize">
              {item.status}
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 shrink-0">
            <Button
              variant="primary"
              size="sm"
              onClick={() => onAction(item.id, 'approve')}
              disabled={acting}
              icon={
                acting ? (
                  <Clock className="w-3 h-3 animate-spin" />
                ) : (
                  <CheckCircle2 className="w-3 h-3" />
                )
              }
              ariaLabel="Approve recommendation"
              data-testid={`approval-queue-approve-${item.id}`}
            >
              Approve
            </Button>
            <Button
              variant="tertiary"
              size="sm"
              onClick={() => onAction(item.id, 'deny')}
              disabled={acting}
              icon={<XCircle className="w-3 h-3" />}
              ariaLabel="Deny recommendation"
              data-testid={`approval-queue-deny-${item.id}`}
            >
              Deny
            </Button>
            <button
              type="button"
              onClick={() => onAction(item.id, 'dismiss')}
              disabled={acting}
              className="p-1 rounded-[var(--radius-sm)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors disabled:opacity-50"
              aria-label="Dismiss recommendation"
              data-testid={`approval-queue-dismiss-${item.id}`}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
