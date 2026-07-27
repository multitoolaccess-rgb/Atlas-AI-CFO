'use client'

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { createPortal } from 'react-dom'

import {
  Search,
  X,
  ArrowRight,
  CreditCard,
  Landmark,
  Target,
  Receipt,
  CornerDownLeft,
  ArrowUp,
  ArrowDown,
} from 'lucide-react'
import {
  rulesService,
  type Transaction,
  type Account,
  type Goal,
} from '@/lib/api'
import { formatCurrency } from '@/lib/format'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CommandPaletteProps {
  open: boolean
  onClose: () => void
  /** Called with the target path when a result is selected.
   *  The parent is responsible for navigation (e.g. router.push).
   *  Decouples the palette from Next.js for testability. */
  onNavigate?: (href: string) => void
}

/** Normalised search result item. */
interface SearchResult {
  id: string
  type: 'transaction' | 'account' | 'goal'
  title: string
  subtitle: string
  /** Navigation target on select. */
  href: string
  /** Icon component to render. */
  icon: React.ElementType
  /** Raw numeric value for secondary display (balance, amount, target). */
  value?: number
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MAX_RESULTS_PER_GROUP = 6

function matchQuery(text: string, query: string): boolean {
  if (!query) return true
  const lower = query.toLowerCase()
  return text.toLowerCase().includes(lower)
}

function toResults(
  transactions: Transaction[],
  accounts: Account[],
  goals: Goal[],
  query: string,
): SearchResult[] {
  const txResults: SearchResult[] = transactions
    .filter(
      (t) =>
        matchQuery(t.description, query) ||
        matchQuery(t.merchant_name ?? '', query) ||
        matchQuery(t.category_name ?? '', query) ||
        matchQuery(t.account_name ?? '', query) ||
        matchQuery(t.amount.toString(), query),
    )
    .slice(0, MAX_RESULTS_PER_GROUP)
    .map((t) => ({
      id: `tx-${t.id}`,
      type: 'transaction' as const,
      title: t.description,
      subtitle: [
        t.merchant_name || t.category_name || t.account_name,
        t.transaction_date,
      ]
        .filter(Boolean)
        .join(' · '),
      href: '/activity',
      icon: Receipt,
      value: t.amount,
    }))

  const acctResults: SearchResult[] = accounts
    .filter(
      (a) =>
        matchQuery(a.account_name, query) ||
        matchQuery(a.account_type, query) ||
        matchQuery(a.account_subtype ?? '', query),
    )
    .slice(0, MAX_RESULTS_PER_GROUP)
    .map((a) => ({
      id: `acct-${a.id}`,
      type: 'account' as const,
      title: a.account_name,
      subtitle: [a.account_type, a.account_subtype].filter(Boolean).join(' · '),
      href: '/accounts',
      icon: a.account_type === 'credit_card' ? CreditCard : Landmark,
      value: a.current_balance,
    }))

  const goalResults: SearchResult[] = goals
    .filter(
      (g) =>
        matchQuery(g.name, query) ||
        matchQuery(g.notes ?? '', query) ||
        matchQuery(g.target_amount.toString(), query),
    )
    .slice(0, MAX_RESULTS_PER_GROUP)
    .map((g) => ({
      id: `goal-${g.id}`,
      type: 'goal' as const,
      title: g.name,
      subtitle: g.target_date
        ? `Target: ${g.target_date}`
        : g.horizon_years
          ? `${g.horizon_years}y horizon`
          : 'No deadline',
      href: '/goals',
      icon: Target,
      value: g.target_amount,
    }))

  return [...acctResults, ...txResults, ...goalResults]
}

// ---------------------------------------------------------------------------
// Group labels
// ---------------------------------------------------------------------------

const GROUP_LABELS: Record<SearchResult['type'], string> = {
  account: 'Accounts',
  transaction: 'Transactions',
  goal: 'Goals',
}

const GROUP_ORDER: SearchResult['type'][] = ['account', 'transaction', 'goal']

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function CommandPalette({ open, onClose, onNavigate }: CommandPaletteProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const [query, setQuery] = useState('')
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [goals, setGoals] = useState<Goal[]>([])
  const [loading, setLoading] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)

  // Fetch data when palette opens
  useEffect(() => {
    if (!open) return
    setQuery('')
    setActiveIndex(0)
    setLoading(true)

    let cancelled = false
    Promise.all([
      rulesService.listTransactions({ limit: 200 }).catch(() => []),
      rulesService.listAccounts().catch(() => []),
      rulesService.listGoals().catch(() => []),
    ]).then(([txns, accts, g]) => {
      if (cancelled) return
      setTransactions(txns)
      setAccounts(accts)
      setGoals(g)
      setLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [open])

  // Focus input on open
  useEffect(() => {
    if (open) {
      // Slight delay so the portal mounts first
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open])

  // Compute filtered results
  const results = useMemo(
    () => toResults(transactions, accounts, goals, query),
    [transactions, accounts, goals, query],
  )

  // Group results by type
  const grouped = useMemo(() => {
    const map = new Map<SearchResult['type'], SearchResult[]>()
    for (const r of results) {
      const arr = map.get(r.type) ?? []
      arr.push(r)
      map.set(r.type, arr)
    }
    return map
  }, [results])

  // Flat list for keyboard navigation
  const flatResults = useMemo(() => {
    const flat: SearchResult[] = []
    for (const type of GROUP_ORDER) {
      const items = grouped.get(type)
      if (items) flat.push(...items)
    }
    return flat
  }, [grouped])

  // Reset active index when results change
  useEffect(() => {
    setActiveIndex(0)
  }, [query])

  // Navigate to selected result
  const navigateTo = useCallback(
    (result: SearchResult) => {
      onClose()
      onNavigate?.(result.href)
    },
    [onClose, onNavigate],
  )

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setActiveIndex((i) => Math.min(i + 1, flatResults.length - 1))
          break
        case 'ArrowUp':
          e.preventDefault()
          setActiveIndex((i) => Math.max(i - 1, 0))
          break
        case 'Enter':
          e.preventDefault()
          if (flatResults[activeIndex]) {
            navigateTo(flatResults[activeIndex])
          }
          break
        case 'Escape':
          e.preventDefault()
          onClose()
          break
      }
    },
    [flatResults, activeIndex, navigateTo, onClose],
  )

  // Pre-compute indexed groups for rendering (avoids mutable counter during render)
  const indexedGroups = useMemo(() => {
    let idx = 0
    return GROUP_ORDER.map((type) => {
      const items = grouped.get(type)
      if (!items?.length) return null
      const indexed = items.map((item) => ({ ...item, flatIndex: idx++ }))
      return { type, label: GROUP_LABELS[type], items: indexed }
    }).filter(Boolean) as Array<{
      type: SearchResult['type']
      label: string
      items: Array<SearchResult & { flatIndex: number }>
    }>
  }, [grouped])

  // Scroll active item into view
  useEffect(() => {
    const list = listRef.current
    if (!list) return
    const active = list.querySelector('[data-active="true"]')
    if (active) {
      active.scrollIntoView({ block: 'nearest' })
    }
  }, [activeIndex])

  // Backdrop click
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) onClose()
    },
    [onClose],
  )

  if (!open) return null
  if (typeof document === 'undefined') return null

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] bg-[var(--bg-overlay)] animate-fadeIn"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <div
        className="
          w-full max-w-xl mx-4
          bg-[var(--bg-primary)]
          rounded-[var(--radius-xl)]
          shadow-[var(--shadow-5)]
          border border-[var(--border-color)]
          overflow-hidden
          animate-scaleIn
        "
        onKeyDown={handleKeyDown}
      >
        {/* ── Search input ────────────────────────────────────── */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--border-subtle)]">
          <Search
            className="w-5 h-5 text-[var(--text-tertiary)] shrink-0"
            aria-hidden="true"
          />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search transactions, accounts, goals…"
            className="
              flex-1 bg-transparent text-sm text-[var(--text-primary)]
              placeholder:text-[var(--text-tertiary)]
              focus:outline-none
            "
            aria-label="Search"
            autoComplete="off"
            spellCheck={false}
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery('')}
              className="p-1 rounded-md text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] transition-colors"
              aria-label="Clear search"
            >
              <X className="w-4 h-4" />
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="
              px-1.5 py-0.5 rounded-md text-[10px] font-mono font-semibold
              bg-[var(--bg-tertiary)] text-[var(--text-tertiary)]
              border border-[var(--border-subtle)]
            "
            aria-label="Close command palette"
          >
            ESC
          </button>
        </div>

        {/* ── Results ─────────────────────────────────────────── */}
        <div
          ref={listRef}
          className="max-h-[50vh] overflow-y-auto py-2"
          role="listbox"
          aria-label="Search results"
        >
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-6 h-6 border-2 border-[var(--slate-200)] border-t-[var(--primary-500)] rounded-full animate-spin" />
            </div>
          ) : flatResults.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
              <Search
                className="w-8 h-8 text-[var(--text-tertiary)] mb-3 opacity-40"
                aria-hidden="true"
              />
              <p className="text-sm text-[var(--text-tertiary)]">
                {query
                  ? `No results for "${query}"`
                  : 'Type to search your finances'}
              </p>
            </div>
          ) : (
            indexedGroups.map((group) => (
              <div key={group.type} role="group" aria-label={group.label}>
                <div className="px-4 py-1.5">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-tertiary)]">
                    {group.label}
                  </span>
                </div>
                {group.items.map((item) => {
                  const isActive = item.flatIndex === activeIndex
                    const Icon = item.icon
                    return (
                      <button
                        key={item.id}
                        type="button"
                        role="option"
                        aria-selected={isActive}
                        data-active={isActive}
                        onClick={() => navigateTo(item)}
                        onMouseEnter={() => setActiveIndex(item.flatIndex)}
                        className={`
                          w-full flex items-center gap-3 px-4 py-2.5 text-left
                          transition-colors duration-100
                          ${isActive
                            ? 'bg-[var(--primary-50)] text-[var(--text-primary)]'
                            : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'
                          }
                        `}
                      >
                        <div
                          className={`
                            w-8 h-8 rounded-lg flex items-center justify-center shrink-0
                            ${isActive
                              ? 'bg-[var(--primary-100)] text-[var(--primary-600)]'
                              : 'bg-[var(--bg-tertiary)] text-[var(--text-tertiary)]'
                            }
                          `}
                        >
                          <Icon className="w-4 h-4" aria-hidden="true" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">
                            {item.title}
                          </p>
                          <p className="text-[11px] text-[var(--text-tertiary)] truncate">
                            {item.subtitle}
                          </p>
                        </div>
                        {item.value !== undefined && (
                          <span
                            className={`
                              text-xs font-mono font-semibold shrink-0
                              ${item.type === 'transaction'
                                ? item.value < 0
                                  ? 'text-[var(--danger-500)]'
                                  : 'text-[var(--success-600)]'
                                : 'text-[var(--text-secondary)]'
                              }
                            `}
                          >
                            {item.type === 'transaction'
                              ? `${item.value < 0 ? '-' : '+'}$${Math.abs(item.value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                              : formatCurrency(item.value)}
                          </span>
                        )}
                        {isActive && (
                          <ArrowRight
                            className="w-3.5 h-3.5 text-[var(--primary-500)] shrink-0"
                            aria-hidden="true"
                          />
                        )}
                      </button>
                    )
                  })}
              </div>
            ))
          )}
        </div>

        {/* ── Footer hints ────────────────────────────────────── */}
        <div className="flex items-center gap-4 px-4 py-2.5 border-t border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
          <span className="inline-flex items-center gap-1 text-[10px] text-[var(--text-tertiary)]">
            <span className="inline-flex items-center justify-center w-4 h-4 rounded bg-[var(--bg-tertiary)]">
              <ArrowUp className="w-2.5 h-2.5" />
            </span>
            <span className="inline-flex items-center justify-center w-4 h-4 rounded bg-[var(--bg-tertiary)]">
              <ArrowDown className="w-2.5 h-2.5" />
            </span>
            Navigate
          </span>
          <span className="inline-flex items-center gap-1 text-[10px] text-[var(--text-tertiary)]">
            <span className="inline-flex items-center justify-center w-4 h-4 rounded bg-[var(--bg-tertiary)]">
              <CornerDownLeft className="w-2.5 h-2.5" />
            </span>
            Open
          </span>
          <span className="inline-flex items-center gap-1 text-[10px] text-[var(--text-tertiary)]">
            <span className="inline-flex items-center justify-center px-1 h-4 rounded bg-[var(--bg-tertiary)] font-mono">
              esc
            </span>
            Close
          </span>
        </div>
      </div>
    </div>,
    document.body,
  )
}

// ---------------------------------------------------------------------------
// Hook — global Cmd+K listener
// ---------------------------------------------------------------------------

/**
 * Registers a global `Cmd+K` / `Ctrl+K` keyboard shortcut.
 * Returns the open state and a toggle function.
 *
 * @example
 *   const { open, toggle, setOpen } = useCommandPalette()
 */
export function useCommandPalette() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen((prev) => !prev)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  const toggle = useCallback(() => setOpen((prev) => !prev), [])
  const close = useCallback(() => setOpen(false), [])

  return { open, toggle, setOpen, close }
}
