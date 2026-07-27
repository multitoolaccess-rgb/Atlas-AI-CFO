/**
 * CategoryDot — small colored decorative indicator rendered inline next to
 * a category name (Activity page's per-row promote picker, Settings card
 * chips, etc.).
 *
 * Props:
 *   - category: { name: string; color?: string | null }
 *   - size?: 'sm' | 'md' | 'lg' — controls the dot diameter (8 / 10 / 14 px)
 *
 * Behavior:
 *   - Uses `category.color` as the CSS background. If missing, falls back
 *     to the hard-coded brand hex ('#6366f1') so the dot still renders
 *     instead of silently disappearing against a CSS-variable resolve
 *     failure (theme that never registered `--primary-500`, dark-mode
 *     overrides, jsdom tests).
 *   - Exposes the category name via aria-label + title for screen readers
 *     + hover tooltips.
 *
 * Why a separate component and not a one-liner in the consumers? Three
 * pages (activity row picker, settings merchant rule list, possibly the
 * Phase 16 family card) need the same visual + accessibility treatment,
 * so centralizing it prevents drift. The barrel re-export at
 * `ui/components/ui/index.ts` exposes it as `CategoryDot` to consumers
 * that prefer `import { CategoryDot } from '@/components/ui'`.
 */
import type { CSSProperties } from 'react'

const FALLBACK_COLOR = '#6366f1' // Tailwind indigo-500 — never a CSS var.

export interface CategoryDotProps {
  category: { name: string; color?: string | null }
  size?: 'sm' | 'md' | 'lg'
}

const SIZE_MAP: Record<NonNullable<CategoryDotProps['size']>, string> = {
  sm: '0.5rem', // 8px
  md: '0.625rem', // 10px
  lg: '0.875rem', // 14px
}

export default function CategoryDot({
  category,
  size = 'md',
}: CategoryDotProps) {
  const diameter = SIZE_MAP[size]
  const color = (category?.color && category.color.trim()) || FALLBACK_COLOR
  const style: CSSProperties = {
    display: 'inline-block',
    width: diameter,
    height: diameter,
    borderRadius: '9999px',
    backgroundColor: color,
    flexShrink: 0,
    boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.06)',
  }
  return (
    <span
      role="img"
      aria-label={`${category?.name ?? 'Uncategorized'} category indicator`}
      title={category?.name}
      style={style}
      data-testid={`category-dot-${(category?.name ?? 'unknown').toLowerCase().replace(/\s+/g, '_')}`}
    />
  )
}
