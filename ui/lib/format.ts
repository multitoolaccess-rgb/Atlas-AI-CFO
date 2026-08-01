/**
 * Shared formatting utilities.
 *
 * Centralises currency / percent / number formatters so chart components,
 * dashboard widgets, and page-level JSX stop duplicating the same
 * Intl.NumberFormat / toFixed logic in every file.
 *
 * Usage:
 *   import { formatCurrency, formatCompact, formatPercent } from '@/lib/format'
 */

// ─── Currency ──────────────────────────────────────────────────────────

/**
 * Full currency string with comma grouping — e.g. "$12,345".
 * Drops cents for values >= $1 (maximumFractionDigits: 0).
 *
 * Use for: KPI cards, tooltips, table cells, center donut labels.
 */
export function formatCurrency(value: number): string {
  if (Math.abs(value) >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(1)}M`
  }
  if (Math.abs(value) >= 1_000) {
    return `$${Math.round(value).toLocaleString('en-US')}`
  }
  return `$${value.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

/**
 * Compact plain number for chart axis ticks — "0", "5K", "1.2M".
 * Keeps labels short so they don't collide on narrow axes.
 *
 * Use for: Recharts YAxis tickFormatter, sparkline labels.
 */
export function formatCompact(value: number): string {
  if (value === 0) return '0'
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(0)}K`
  return `${Math.round(value)}`
}

// ─── Percent ───────────────────────────────────────────────────────────

/**
 * Formatted percent string — e.g. "12.3%".
 *
 * @param value  A ratio in **percentage points** (not 0-1).
 *               So `formatPercent(12.34)` → "12.3%".
 * @param decimals  Fraction digits. Default 1.
 */
export function formatPercent(value: number, decimals = 1): string {
  return `${value.toFixed(decimals)}%`
}

// ─── Plain number ──────────────────────────────────────────────────────

/**
 * Locale-aware integer with comma grouping — e.g. "1,234".
 * Useful for transaction counts, account numbers, etc.
 */
export function formatNumber(value: number): string {
  return value.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

/**
 * Phase 2 Slice 2 — Decimal-string formatter. Accepts a canonical
 * Decimal string (e.g. ``"4500000.00"``) and returns a thousands-
 * grouped two-digit form (e.g. ``"4,500,000.00"``) WITHOUT coercing
 * through ``Number()`` and WITHOUT losing cents.
 *
 * Per `docs/10-roadmap/PHASE2_VERTICAL_SLICE_PLAN.md` §2 AC2, every
 * money value reaching the UI must be rendered from a canonical
 * Decimal string with no ``Number()``/``parseFloat`` on the API
 * path. This formatter exists precisely so the existing
 * ``formatNumber`` (which expects a number and drops cents) can
 * stay untouched for non-money integer use cases while Slice 2
 * money surfaces preserve cents + canonical form.
 *
 * Edge cases:
 *   - ``"15000000.00"``  → ``"15,000,000.00"``
 *   - ``"3200000.00"``   → ``"3,200,000.00"``
 *   - ``"12345.6"``     → ``"12,345.6"``    (no cents padding — caller
 *                                             is canonical-string source)
 *   - ``"12345"``       → ``"12,345"``     (no fractional part)
 *   - ``"0.01"``        → ``"0.01"``
 *   - ``"-4500.50"``    → ``"-4,500.50"``  (negative supported)
 */
export function formatDecimalString(value: string): string {
  if (typeof value !== 'string') return ''
  const negative = value.startsWith('-')
  const unsigned = negative ? value.slice(1) : value
  const dotIdx = unsigned.indexOf('.')
  const whole = dotIdx === -1 ? unsigned : unsigned.slice(0, dotIdx)
  const frac = dotIdx === -1 ? '' : unsigned.slice(dotIdx + 1)
  const wholeGrouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',') || '0'
  const sign = negative ? '-' : ''
  return frac ? `${sign}${wholeGrouped}.${frac}` : `${sign}${wholeGrouped}`
}

/**
 * Compact plain number for chart axis/ticks — e.g. "1.2M", "8K", "0".
 * Keeps labels short without a currency symbol.
 */
export function formatCompactNumber(value: number): string {
  if (value === 0) return '0'
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(0)}K`
  return `${Math.round(value)}`
}

/**
 * Format a YYYY-MM month label as "Oct 2023".
 * Falls back to the raw string if parsing fails.
 */
export function formatMonthLabel(value: string): string {
  try {
    const date = new Date(`${value}-01T00:00:00`)
    return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  } catch {
    return value
  }
}
