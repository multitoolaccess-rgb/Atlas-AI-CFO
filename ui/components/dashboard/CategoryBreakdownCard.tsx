'use client'

import { useMemo, useState } from 'react'
import { ChevronRight, ListFilter } from 'lucide-react'
import ExpandableCard from '@/components/dashboard/ExpandableCard'
import { formatCurrency } from '@/lib/format'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CategoryBreakdownItem {
  id: string
  name: string
  amount: number
  /** Theme-aware hex color for the swatch. */
  color: string
  group?: string
}

interface CategoryBreakdownCardProps {
  title: string
  subtitle?: string
  icon?: React.ReactNode
  items: CategoryBreakdownItem[]
  total: number
  /** Called when a category row is clicked for drilldown. */
  onSelect?: (item: CategoryBreakdownItem) => void
  className?: string
}

const VISIBLE_ROWS = 8

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function CategoryBreakdownCard({
  title,
  subtitle,
  icon,
  items,
  total,
  onSelect,
  className = '',
}: CategoryBreakdownCardProps) {
  const [hovered, setHovered] = useState<string | null>(null)

  const sorted = useMemo(
    () => [...items].filter((i) => i.amount > 0).sort((a, b) => b.amount - a.amount),
    [items],
  )
  const visible = sorted.slice(0, VISIBLE_ROWS)

  const row = (item: CategoryBreakdownItem) => {
    const pct = total > 0 ? (item.amount / total) * 100 : 0
    const isActive = hovered === item.id
    return (
      <div
        key={item.id}
        role="button"
        tabIndex={0}
        aria-label={`${item.name}: ${formatCurrency(item.amount)} (${pct.toFixed(1)}%)`}
        className={`flex items-center gap-3 p-3 rounded-lg border transition-all duration-150 cursor-pointer ${
          isActive
            ? 'bg-[var(--bg-tertiary)] border-[var(--primary-200)]'
            : 'bg-[var(--bg-secondary)] border-[var(--border-color)] hover:border-[var(--primary-200)]'
        }`}
        onClick={() => onSelect?.(item)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onSelect?.(item)
          }
        }}
        onMouseEnter={() => setHovered(item.id)}
        onMouseLeave={() => setHovered(null)}
        onFocus={() => setHovered(item.id)}
        onBlur={() => setHovered(null)}
      >
        <div className="w-3 h-3 rounded-sm flex-shrink-0" style={{ backgroundColor: item.color }} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-[var(--text-primary)] truncate">{item.name}</p>
          <p className="text-xs text-[var(--text-tertiary)]">
            {pct.toFixed(1)}% of total{item.group ? ` · ${item.group}` : ''}
          </p>
        </div>
        <p className="text-sm font-bold text-[var(--text-primary)] tabular-nums whitespace-nowrap">{formatCurrency(item.amount)}</p>
        <ChevronRight className="w-4 h-4 text-[var(--text-tertiary)] flex-shrink-0" />
      </div>
    )
  }

  const expandedContent =
    sorted.length > VISIBLE_ROWS ? (
      <div className="space-y-2">{sorted.map(row)}</div>
    ) : undefined

  return (
    <ExpandableCard
      title={title}
      subtitle={subtitle ?? (sorted.length > 0 ? `${sorted.length} items · ${formatCurrency(total)}` : 'No data in this range')}
      icon={icon ?? <ListFilter className="w-4 h-4 text-[var(--primary-600)]" />}
      expandedContent={expandedContent}
      className={className}
    >
      {sorted.length > 0 ? (
        <div className="space-y-2">{visible.map(row)}</div>
      ) : (
        <div className="flex min-h-[160px] items-center justify-center rounded-lg border border-dashed border-[var(--border-color)] bg-[var(--bg-secondary)] px-6 text-center">
          <div>
            <p className="text-sm font-semibold text-[var(--text-primary)]">No categories in this range</p>
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">Add transactions to see category detail.</p>
          </div>
        </div>
      )}
    </ExpandableCard>
  )
}