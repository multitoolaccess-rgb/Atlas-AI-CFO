'use client'

import { useMemo, useState, useCallback, useEffect } from 'react'
import { Receipt, ArrowUpDown, ChevronRight } from 'lucide-react'
import type { Transaction, Category } from '@/lib/api'
import { CATEGORY_GROUP_ORDER, CATEGORY_GROUP_COLORS, CATEGORY_GROUP_LABELS, rulesService } from '@/lib/api'
import ExpandableCard from '@/components/dashboard/ExpandableCard'
import TreemapChart from '@/components/charts/TreemapChart'
import type { TreemapDatum } from '@/components/charts/TreemapChart'
import TiltCard from '@/components/ui/TiltCard'
import { formatNumber } from '@/lib/format'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface SpendByCategoryBarProps {
  transactions: Transaction[]
  /** Pre-computed category color map (name→color). Parent owns the fetch. */
  colorByName?: Map<string, string>
  loading?: boolean
  className?: string
  /** Called when a user clicks a category for drilldown. */
  onCategoryClick?: (categoryName: string) => void
  /** Phase D — pre-loaded categories list for group lookups. */
  categories?: Category[]
}

type SortMode = 'highest' | 'alpha' | 'count'

const SORT_LABELS: Record<SortMode, string> = {
  highest: 'Highest Spend',
  alpha: 'A → Z',
  count: 'Most Transactions',
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function SpendByCategoryBar({
  transactions,
  colorByName: externalColorMap,
  loading,
  className = '',
  onCategoryClick,
  categories: externalCategories,
}: SpendByCategoryBarProps) {
  const colorByName = useMemo(
    () => externalColorMap ?? new Map<string, string>(),
    [externalColorMap],
  )
  const [sortBy, setSortBy] = useState<SortMode>('highest')
  const [showAll, setShowAll] = useState(false)

  // Phase D — fetch categories for group lookups if not provided.
  const [fetchedCategories, setFetchedCategories] = useState<Category[]>([])
  useEffect(() => {
    if (externalCategories && externalCategories.length > 0) return
    let cancelled = false
    rulesService.listCategories().then((list) => {
      if (!cancelled) setFetchedCategories(list)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [externalCategories])
  const categories = externalCategories && externalCategories.length > 0 ? externalCategories : fetchedCategories

  const groupByName = useMemo(() => {
    const m = new Map<string, string>()
    for (const c of categories) {
      m.set(c.name.toLowerCase(), c.group || 'Expenses')
    }
    return m
  }, [categories])

  const allCategories = useMemo(() => {
    // Count all negative-amount transactions grouped by user-assigned
    // category.  This is a CATEGORY visualization ("where is my money
    // going") — not a cashflow classification.
    const expenses = transactions.filter((t) => t.amount < 0)
    const map = new Map<string, { total: number; count: number }>()
    for (const txn of expenses) {
      const name = txn.category_name || 'Uncategorized'
      const existing = map.get(name) ?? { total: 0, count: 0 }
      existing.total += Math.abs(txn.amount)
      existing.count += 1
      map.set(name, existing)
    }
    return Array.from(map.entries()).map(([name, { total, count }]) => ({
      name,
      value: total,
      color: colorByName.get(name.toLowerCase()) || 'var(--slate-400)',
      subLabel: `${count} txn${count === 1 ? '' : 's'}`,
      count,
      group: groupByName.get(name.toLowerCase()) || 'Expenses',
    }))
  }, [transactions, colorByName, groupByName])

  const sortedCategories = useMemo(() => {
    const sorted = [...allCategories]
    switch (sortBy) {
      case 'highest':
        sorted.sort((a, b) => b.value - a.value)
        break
      case 'alpha':
        sorted.sort((a, b) => a.name.localeCompare(b.name))
        break
      case 'count':
        sorted.sort((a, b) => b.count - a.count)
        break
    }
    return sorted
  }, [allCategories, sortBy])

  const visibleCategories = showAll ? sortedCategories : sortedCategories.slice(0, 12)

  const treemapData: TreemapDatum[] = useMemo(
    () =>
      visibleCategories.map((c) => ({
        id: c.name,
        name: c.name,
        value: c.value,
        color: c.color,
      })),
    [visibleCategories],
  )

  const totalSpending = allCategories.reduce((s, d) => s + d.value, 0)

  const cycleSortBy = useCallback(() => {
    setSortBy((prev) => {
      const modes: SortMode[] = ['highest', 'alpha', 'count']
      const idx = modes.indexOf(prev)
      return modes[(idx + 1) % modes.length]
    })
  }, [])

  const headerRight = (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={cycleSortBy}
        className="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--slate-100)] transition-colors duration-150"
        aria-label={`Sort by ${SORT_LABELS[sortBy]}`}
      >
        <ArrowUpDown className="w-3.5 h-3.5" />
        <span className="hidden sm:inline">{SORT_LABELS[sortBy]}</span>
      </button>
    </div>
  )

  const expandedContent = allCategories.length > 8 ? (
    <div className="space-y-3">
      <p className="text-xs text-tertiary">
        Showing {visibleCategories.length} of {allCategories.length} categories
      </p>
      {!showAll && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="text-xs font-semibold text-[var(--primary-600)] hover:text-[var(--primary-700)] transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--primary-500)]"
        >
          Show all {allCategories.length} categories <ChevronRight className="w-3 h-3 inline" />
        </button>
      )}
      {/* Phase D — spending distribution grouped by category group */}
      <div className="p-3 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-color)]">
        <p className="label-sm text-tertiary mb-2">Spending Distribution</p>
        <div className="space-y-2">
          {(() => {
            // Group sorted categories by their group.
            const grouped = new Map<string, typeof sortedCategories>()
            for (const cat of sortedCategories.slice(0, 12)) {
              const g = cat.group || 'Expenses'
              if (!grouped.has(g)) grouped.set(g, [])
              grouped.get(g)!.push(cat)
            }
            const elements: React.ReactNode[] = []
            for (const groupName of CATEGORY_GROUP_ORDER) {
              const items = grouped.get(groupName)
              if (!items || items.length === 0) continue
              const groupColor = CATEGORY_GROUP_COLORS[groupName] || 'var(--slate-500)'
              elements.push(
                <div key={`exp-${groupName}`}>
                  <div className="flex items-center gap-1.5 mb-1 mt-1">
                    <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: groupColor }} />
                    <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: groupColor }}>
                      {CATEGORY_GROUP_LABELS[groupName] || groupName}
                    </span>
                  </div>
                  {items.map((cat) => (
                    <div key={cat.name} className="flex items-center gap-2 text-xs pl-3">
                      <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: cat.color }} />
                      <span className="text-[var(--text-secondary)] flex-1 truncate">{cat.name}</span>
                      <span className="font-semibold text-on-surface">{formatNumber(cat.value)}</span>
                      <span className="text-[var(--text-tertiary)] w-12 text-right">
                        {totalSpending > 0 ? Math.round((cat.value / totalSpending) * 100) : 0}%
                      </span>
                    </div>
                  ))}
                </div>,
              )
            }
            return elements
          })()}
        </div>
      </div>
    </div>
  ) : undefined

  if (loading) {
    return (
      <ExpandableCard
        title="Spending by Category"
        subtitle="Loading…"
        icon={<Receipt className="w-4 h-4 text-[var(--primary-600)]" />}
        className={className}
      >
        <div className="skeleton h-[280px] w-full" aria-busy="true" />
      </ExpandableCard>
    )
  }

  return (
    <ExpandableCard
      title="Spending by Category"
      subtitle={`${allCategories.length} categories · ${formatNumber(totalSpending)} total`}
      icon={<Receipt className="w-4 h-4 text-[var(--primary-600)]" />}
      headerRight={headerRight}
      expandedContent={expandedContent}
      className={className}
    >
      {treemapData.length > 0 ? (
        <TiltCard className="p-2">
          <div className="flex flex-col md:flex-row items-center gap-6">
            <TreemapChart
              data={treemapData}
              height={280}
              onSelect={(d) => onCategoryClick?.(d.name)}
              className="flex-shrink-0 w-full md:w-2/3"
            />
            <div className="flex-1 w-full">
              <ul className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-1 gap-2 max-h-[260px] overflow-auto pr-1">
                {visibleCategories.map((cat) => (
                  <li key={cat.name}>
                    <button
                      type="button"
                      className="flex items-center gap-2 text-sm rounded-md px-2 py-1.5 hover:bg-[var(--bg-secondary)] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--primary-500)] transition-colors text-left w-full"
                      onClick={() => onCategoryClick?.(cat.name)}
                    >
                      <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: cat.color }} />
                      <span className="flex-1 truncate text-[var(--text-secondary)]">{cat.name}</span>
                      <span className="font-semibold text-on-surface tabular-nums">{formatNumber(cat.value)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </TiltCard>
      ) : (
        <div className="flex items-center justify-center h-[200px] text-[var(--text-tertiary)]">
          <p className="text-sm">No categorized expenses yet.</p>
        </div>
      )}
    </ExpandableCard>
  )
}
