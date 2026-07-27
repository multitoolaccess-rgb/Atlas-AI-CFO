'use client'

import { useMemo } from 'react'
import { Receipt } from 'lucide-react'
import type { Transaction } from '@/lib/api'
import { rulesService, type Category, CATEGORY_GROUP_ORDER, CATEGORY_GROUP_COLORS, CATEGORY_GROUP_LABELS } from '@/lib/api'
import { useEffect, useState } from 'react'
import { CategoryDot } from '@/components/ui/CategoryChip'

interface SpendingByCategoryProps {
  transactions: Transaction[]
  loading?: boolean
  className?: string
  /** Phase E — pre-loaded categories from parent to avoid duplicate fetches. */
  categories?: Category[]
}

interface CategoryAggregate {
  name: string
  total: number
  count: number
  pct: number
  /** Canonical color from the BE Category.color column. */
  color: string
  /** Optional emoji icon from the BE Category.icon column. */
  icon: string | null
}

export default function SpendingByCategory({ transactions, loading, className = '', categories: externalCategories }: SpendingByCategoryProps) {
  // Phase 29 — pull the canonical Category.color from the BE rather
  // than the per-render indexed CATEGORY_COLORS array (the pre-Phase
  // 29 bug). Phase E — use parent-provided categories when available
  // to avoid a duplicate API call.
  const [fetchedCategories, setFetchedCategories] = useState<Category[]>([])
  useEffect(() => {
    if (externalCategories && externalCategories.length > 0) return
    let cancelled = false
    const load = async () => {
      try {
        const list = await rulesService.listCategories()
        if (!cancelled) setFetchedCategories(list)
      } catch {
        if (!cancelled) setFetchedCategories([])
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [externalCategories])
  const categories = externalCategories && externalCategories.length > 0 ? externalCategories : fetchedCategories
  const colorByName = useMemo(() => {
    const m = new Map<string, { color: string; icon: string | null }>()
    for (const c of categories) {
      m.set(c.name.toLowerCase(), {
        color: c.color || 'var(--slate-400)',
        icon: c.icon || null,
      })
    }
    return m
  }, [categories])

  // Build a group lookup from the categories list.
  const groupByName = useMemo(() => {
    const m = new Map<string, string>()
    for (const c of categories) {
      m.set(c.name.toLowerCase(), c.group || 'Expenses')
    }
    return m
  }, [categories])

  const { aggregates, totalSpending } = useMemo(() => {
    // Only count expenses (negative amounts) for category breakdown
    const expenses = transactions.filter((t) => t.amount < 0)
    const map = new Map<string, { total: number; count: number }>()
    for (const txn of expenses) {
      const name = txn.category_name || 'Uncategorized'
      const existing = map.get(name) ?? { total: 0, count: 0 }
      existing.total += Math.abs(txn.amount)
      existing.count += 1
      map.set(name, existing)
    }
    const total = expenses.reduce((s, t) => s + Math.abs(t.amount), 0)
    const absTotal = Math.max(1, total)
    const items = Array.from(map.entries())
      .map(([name, { total: catTotal, count }]) => {
        const meta = colorByName.get(name.toLowerCase())
        return {
          name,
          total: catTotal,
          count,
          pct: (catTotal / absTotal) * 100,
          color: meta?.color || 'var(--slate-400)',
          icon: meta?.icon || null,
          group: groupByName.get(name.toLowerCase()) || 'Expenses',
        }
      })
      .sort((a, b) => b.total - a.total)
      .slice(0, 8) // Top 8 categories

    return { aggregates: items, totalSpending: total }
  }, [transactions, colorByName, groupByName])

  if (loading) {
    return (
      <div className={`card p-6 ${className}`} aria-label="Spending by category" aria-busy="true">
        <h3 className="headline-md text-primary mb-4">Spending by Category</h3>
        <div className="space-y-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i}>
              <div className="skeleton h-3 w-1/4 mb-2" />
              <div className="skeleton h-2 w-full" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (aggregates.length === 0) {
    return (
      <div className={`card p-6 ${className}`} aria-label="Spending by category">
        <h3 className="headline-md text-primary mb-4">Spending by Category</h3>
        <p className="body-sm text-tertiary">
          No categorized expenses yet. Upload a statement or auto-categorize your transactions.
        </p>
      </div>
    )
  }

  return (
    <div className={`card p-6 animate-fadeIn ${className}`} aria-label="Spending by category">
      <div className="flex-between mb-5">
        <h3 className="headline-md text-primary">Spending by Category</h3>
        <span className="numeric-sm text-negative">
          −${totalSpending.toLocaleString('en-US', { maximumFractionDigits: 0 })}
        </span>
      </div>

      {/* Donut-style summary ring */}
      <div className="flex items-center gap-6 mb-5">
        <div className="relative w-24 h-24 flex-shrink-0">
          <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
            {aggregates.reduce<{ elements: React.ReactNode[]; offset: number }>(
              (acc, agg, idx) => {
                const dash = agg.pct
                const gap = 100 - dash
                const element = (
                  <circle
                    key={idx}
                    cx="18"
                    cy="18"
                    r="15.915"
                    fill="none"
                    stroke={agg.color}
                    strokeWidth="3.5"
                    strokeDasharray={`${dash} ${gap}`}
                    strokeDashoffset={`${-acc.offset}`}
                    className="transition-all duration-700"
                  />
                )
                return { elements: [...acc.elements, element], offset: acc.offset + dash }
              },
              { elements: [], offset: 0 },
            ).elements}
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-[10px] text-tertiary uppercase tracking-wider">
              {aggregates.length}
            </span>
            <span className="text-[10px] text-tertiary">categories</span>
          </div>
        </div>

        {/* Top 3 legend */}
        <div className="flex-1 space-y-2">
          {aggregates.slice(0, 3).map((agg) => (
            <div key={agg.name} className="flex items-center gap-2">
              <CategoryDot
                category={{ name: agg.name, color: agg.color }}
                size="sm"
              />
              <span className="body-sm text-on-surface truncate">{agg.name}</span>
              <span className="body-sm text-tertiary ml-auto">
                {agg.pct.toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Full bar breakdown — grouped by category group */}
      <div className="space-y-3">
        {(() => {
          // Group the top-8 aggregates by their group, preserving sort order.
          const grouped = new Map<string, typeof aggregates>()
          for (const agg of aggregates) {
            const g = agg.group || 'Expenses'
            if (!grouped.has(g)) grouped.set(g, [])
            grouped.get(g)!.push(agg)
          }
          // Render groups in canonical order, skipping empty.
          const elements: React.ReactNode[] = []
          for (const groupName of CATEGORY_GROUP_ORDER) {
            const items = grouped.get(groupName)
            if (!items || items.length === 0) continue
            const groupColor = CATEGORY_GROUP_COLORS[groupName] || 'var(--slate-500)'
            elements.push(
              <div key={`group-${groupName}`}>
                <div className="flex items-center gap-2 mb-2 mt-1">
                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: groupColor }} />
                  <span className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: groupColor }}>
                    {CATEGORY_GROUP_LABELS[groupName] || groupName}
                  </span>
                </div>
                <div className="space-y-2.5">
                  {items.map((agg) => (
                    <div key={agg.name} className="group">
                      <div className="flex-between mb-1">
                        <div className="flex items-center gap-2">
                          {agg.icon ? (
                            <span className="text-sm" aria-hidden="true">{agg.icon}</span>
                          ) : (
                            <Receipt className="w-3.5 h-3.5 text-tertiary" aria-hidden="true" />
                          )}
                          <span className="label-md text-on-surface">{agg.name}</span>
                          <span className="text-[10px] text-tertiary">({agg.count})</span>
                        </div>
                        <span className="numeric-sm text-primary">
                          ${agg.total.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                        </span>
                      </div>
                      <div className="relative h-1.5 w-full bg-[var(--slate-100)] rounded-[var(--radius-full)] overflow-hidden">
                        <div
                          className="h-full rounded-[var(--radius-full)] transition-all duration-700 ease-out group-hover:opacity-80"
                          style={{
                            width: `${Math.min(100, agg.pct)}%`,
                            backgroundColor: agg.color,
                          }}
                          role="progressbar"
                          aria-valuenow={Math.round(agg.pct)}
                          aria-valuemin={0}
                          aria-valuemax={100}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>,
            )
          }
          return elements
        })()}
      </div>
    </div>
  )
}
