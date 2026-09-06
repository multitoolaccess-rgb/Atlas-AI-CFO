/**
 * Shared theme-aware color palette for the CashFlix dashboard.
 *
 * Single source of truth for every role-based, category, and series
 * color that needs to adapt between light and dark mode. Components
 * that render SVG, canvas, or inline `style={{ color }}` (where CSS
 * custom properties don't work) should import from here instead of
 * hardcoding hex values.
 *
 * Usage:
 *   import { DASHBOARD_COLORS, useThemeColors, getDashboardColor,
 *           luminance, getTextColor, getTextSecondaryColor } from '@/lib/themeColors'
 *
 *   // In a component:
 *   const tc = useThemeColors()
 *   <div style={{ color: tc.earn }}>...</div>
 *
 *   // Outside React (pure helpers):
 *   getDashboardColor('earn', isDark)
 *   getTextColor('#B91C1C')
 */

import { useThemeMode } from './useThemeMode'
import { useAppearance } from '@/components/providers/AppearanceProvider'
import type { AccentProfile } from './appearance'

// ---------------------------------------------------------------------------
// Color palettes — light and dark variants for every named role/series
// ---------------------------------------------------------------------------

/**
 * Master color map. Each key has a `light` (rich mid-tones for white paper)
 * and `dark` (vivid brights for dark substrate) variant.
 *
 * Keys span three categories:
 *   1. CashflowRole values (spend, earn, save, invest, debt, transfer)
 *   2. Dashboard series/segment names (essential, flexible, income,
 *      spend_series, retained, net_retained)
 *   3. Semantic accents (income_accent = sky-blue income highlight)
 */
export const DASHBOARD_COLORS: Record<'light' | 'dark', Record<string, string>> = {
  light: {
    // CashflowRole — match tokens.css light-mode success/danger/etc ramps
    spend:     '#B91C1C', // red-700
    earn:      '#047857', // emerald-700
    save:      '#4338CA', // indigo-700
    invest:    '#0369A1', // sky-700
    debt:      '#B45309', // amber-700
    transfer:  '#6B7280', // gray-500

    // Breakdown segments
    essential: '#C81425', // aviation red
    flexible:  '#D97706', // amber-600
    savings:   '#059669', // emerald-600

    // Trend / KPI series
    income:        '#0369A1', // sky-700 — readable on white
    spend_series:  '#C81425', // aviation red
    net_retained:  '#059669', // emerald-600

    // KPI accents
    income_accent: '#0369A1', // sky-700
    spend_accent:  '#C81425', // aviation red
    saved_accent:  '#0EA5E9', // sky-500
    retained_accent: '#059669', // emerald-600

    // Sankey special node types (suffixed to avoid collision with trend keys)
    // getNodeFill() maps node_type 'income' → 'income_node' etc.
    income_node:   '#047857',
    retained_node: '#4338CA',
    overspend_node:'#B91C1C',
    allocation:    '#6B7280',
    expense:       '#B91C1C',
    outcome:       '#0369A1',

    // Account palette — portfolio donut + allocation bars.
    // Deep shades for white paper (high contrast).
    account_0: '#0D9488', // teal-600
    account_1: '#6366F1', // indigo-500
    account_2: '#D97706', // amber-600
    account_3: '#DB2777', // pink-600
    account_4: '#059669', // emerald-600
    account_5: '#7C3AED', // violet-600

    // Analyst consensus — sell-side recommendation bar chart
    consensus_strong_buy: '#16A34A', // green-600
    consensus_buy:        '#22C55E', // green-500
    consensus_hold:       '#A3A3A3', // neutral gray
    consensus_sell:       '#F59E0B', // amber-500
    consensus_strong_sell:'#DC2626', // red-600
  },
  dark: {
    // CashflowRole — vivid brights for dark substrate
    spend:     '#F87171', // red-400
    earn:      '#34D399', // emerald-400
    save:      '#818CF8', // indigo-400
    invest:    '#38BDF8', // sky-400
    debt:      '#FBBF24', // amber-400
    transfer:  '#9CA3AF', // gray-400

    // Breakdown segments
    essential: '#F87171', // red-400
    flexible:  '#FBBF24', // amber-400
    savings:   '#34D399', // emerald-400

    // Trend / KPI series
    income:        '#38BDF8', // sky-400
    spend_series:  '#F87171', // red-400
    net_retained:  '#34D399', // emerald-400

    // KPI accents
    income_accent: '#38BDF8', // sky-400
    spend_accent:  '#F87171', // red-400
    saved_accent:  '#38BDF8', // sky-400
    retained_accent: '#34D399', // emerald-400

    // Sankey special node types (suffixed to avoid collision with trend keys)
    // getNodeFill() maps node_type 'income' → 'income_node' etc.
    income_node:   '#34D399',
    retained_node: '#818CF8',
    overspend_node:'#F87171',
    allocation:    '#9CA3AF',
    expense:       '#F87171',
    outcome:       '#38BDF8',

    // Account palette — vivid brights for dark substrate.
    account_0: '#2DD4BF', // teal-400
    account_1: '#818CF8', // indigo-400
    account_2: '#FBBF24', // amber-400
    account_3: '#F472B6', // pink-400
    account_4: '#34D399', // emerald-400
    account_5: '#A78BFA', // violet-400

    // Analyst consensus — sell-side recommendation bar chart
    consensus_strong_buy: '#4ADE80', // green-400
    consensus_buy:        '#34D399', // emerald-400
    consensus_hold:       '#9CA3AF', // gray-400
    consensus_sell:       '#FBBF24', // amber-400
    consensus_strong_sell:'#F87171', // red-400
  },
}

/**
 * Darker variant for gradient source stops (Sankey links).
 * Light mode: deep shades for origin-side depth.
 * Dark mode: mid-spectrum (between dark accent and bright fill).
 */
export const GRADIENT_SOURCE_COLORS: Record<'light' | 'dark', Record<string, string>> = {
  light: {
    spend:     '#991B1B',
    earn:      '#065F46',
    save:      '#3730A3',
    invest:    '#075985',
    debt:      '#92400E',
    transfer:  '#4B5563',
    income:    '#065F46',
    retained:  '#3730A3',
    overspend: '#991B1B',
    allocation:'#4B5563',
    expense:   '#991B1B',
    outcome:   '#075985',
  },
  dark: {
    spend:     '#EF4444',
    earn:      '#10B981',
    save:      '#6366F1',
    invest:    '#0EA5E9',
    debt:      '#D97706',
    transfer:  '#6B7280',
    income:    '#10B981',
    retained:  '#6366F1',
    overspend: '#EF4444',
    allocation:'#6B7280',
    expense:   '#EF4444',
    outcome:   '#0EA5E9',
  },
}

// ---------------------------------------------------------------------------
// Pure helpers (no React — usable outside components)
// ---------------------------------------------------------------------------

/** Get a named dashboard color for the current theme. */
export function getDashboardColor(key: string, isDark: boolean): string {
  const palette = isDark ? DASHBOARD_COLORS.dark : DASHBOARD_COLORS.light
  return palette[key] ?? (isDark ? '#6BA3F0' : '#5B8BFF')
}

/** Get a gradient-source color for the current theme. */
export function getGradientSourceColor(key: string, isDark: boolean): string {
  const palette = isDark ? GRADIENT_SOURCE_COLORS.dark : GRADIENT_SOURCE_COLORS.light
  return palette[key] ?? (isDark ? '#4A7FD4' : '#3B5BDB')
}

const ACCENT_CHART_COLORS: Record<AccentProfile, Record<'light' | 'dark', string>> = {
  indigo: { light: '#4d50c9', dark: '#7c83ff' },
  vermilion: { light: '#c93a1b', dark: '#ff5a36' },
  ion: { light: '#5b7900', dark: '#c7f43d' },
}

/** Profile identity for selected/recommended chart series only. */
export function getAccentChartColor(accent: AccentProfile, isDark: boolean): string {
  return ACCENT_CHART_COLORS[accent][isDark ? 'dark' : 'light']
}

/** Relative luminance (WCAG 2.1 §3). Input: 8-bit sRGB hex (#RRGGBB). */
export function luminance(hex: string): number {
  const raw = hex.replace('#', '')
  if (raw.length !== 6) return 0
  const r = parseInt(raw.slice(0, 2), 16) / 255
  const g = parseInt(raw.slice(2, 4), 16) / 255
  const b = parseInt(raw.slice(4, 6), 16) / 255
  const toLinear = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b)
}

/** Pick white or near-black text for ≥ 4.5:1 contrast against bgHex. */
export function getTextColor(bgHex: string): string {
  return luminance(bgHex) > 0.35 ? '#1A1810' : '#FFFFFF'
}

/** Softer variant for secondary text inside colored nodes. */
export function getTextSecondaryColor(bgHex: string): string {
  return luminance(bgHex) > 0.35 ? 'rgba(26,24,16,0.7)' : 'rgba(255,255,255,0.78)'
}

/** Stable fallback palette for unrecognized budget-group keys. */
const GROUP_FALLBACK_KEYS = ['account_0', 'account_1', 'account_2', 'account_3', 'account_4', 'account_5']

/**
 * Theme-aware hex color for a budget/group bucket key.
 *
 * `palette` is the object returned by `useThemeColors()` — its values are
 * hex strings that resolve inside SVG attributes and inline styles (CSS
 * `var(--…)` strings do not reliably resolve in SVG presentation
 * attributes such as `stopColor`).
 *
 * Unknown group keys get a stable color derived from the key itself, so
 * the same custom group is always the same color across charts.
 */
export function resolveGroupColor(group: string, palette: Record<string, string>): string {
  const key = group.trim().toLowerCase()
  switch (key) {
    case 'income':
      return palette.income_accent ?? palette.income
    case 'expenses':
    case 'expense':
    case 'spend':
      return palette.spend_series ?? palette.spend
    case 'debt':
      return palette.debt
    case 'investments':
    case 'invest':
      return palette.invest
    case 'transfer':
      return palette.transfer
    case 'fixed':
    case 'essential':
      return palette.essential
    case 'flexible':
      return palette.flexible
    case 'savings':
    case 'save':
      return palette.savings
    case 'other':
    case 'uncategorized':
    case '':
      return palette.transfer
    default: {
      let h = 0
      for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0
      return palette[GROUP_FALLBACK_KEYS[h % GROUP_FALLBACK_KEYS.length]] ?? '#8b92b9'
    }
  }
}

// ---------------------------------------------------------------------------
// React hook — returns the full theme-aware palette for the current mode
// ---------------------------------------------------------------------------

/**
 * Returns the full DASHBOARD_COLORS palette for the current theme.
 * Re-evaluates automatically when the user toggles dark/light mode.
 *
 * Example:
 *   const tc = useThemeColors()
 *   <span style={{ color: tc.earn }}>+$500</span>
 */
export function useThemeColors(): Record<string, string> {
  const isDark = useThemeMode()
  const { accent } = useAppearance()
  const palette = { ...(isDark ? DASHBOARD_COLORS.dark : DASHBOARD_COLORS.light) }
  const profileAccent = getAccentChartColor(accent, isDark)

  // Only Atlas-selected context follows the profile. Finance semantics
  // such as spend, earn, debt, consensus, and loss remain fixed.
  palette.save = profileAccent
  palette.retained_accent = profileAccent
  palette.retained_node = profileAccent
  palette.outcome = profileAccent
  return palette
}

/** Canonical CashflowRole values — use this instead of hardcoding the
 *  array literal so the type and the values stay in sync. */
export const CASHFLOW_ROLES = ['spend', 'earn', 'save', 'invest', 'debt', 'transfer'] as const
