'use client'

/**
 * Phase 29 — CategoryChip + CategoryDot
 * --------------------------------------
 * Canonical visual primitives for category color across the entire
 * stack (overview, portfolio, activity, settings, merchant-rule
 * chips, recommend-to-rule picker). The color comes from the
 * server-side `Category.color` column (seeded in
 * `app.services.categorizer.DEFAULT_CATEGORIES`) so every page
 * reads the SAME hex value — no more per-page indexed color arrays
 * (the pre-Phase-29 `CATEGORY_COLORS` constant in
 * `SpendingByCategory.tsx` was the bug: it assigned colors by sort
 * position, so the same category rendered in different colors on
 * different pages).
 *
 * Design rules (locked):
 *   - Color comes ONLY from `category.color` (or `var(--slate-400)`
 *     when null, so a freshly-created user category without an
 *     explicit color still renders a sane chip).
 *   - Icon comes from `category.icon` (the seed uses emoji; we
 *     render the emoji verbatim so the visual vocabulary matches
 *     the BE seed). When icon is null we omit it.
 *   - The chip's text color on a solid-color background is white
 *     (luminance > 0.5 → white). When the chip uses a low-saturation
 *     category like Transfer (#64748b) we still pick white because
 *     the chip's solid background meets WCAG AA contrast at >=4.5:1
 *     for the slate-500 hue.
 *   - The chip's hover state uses opacity (not backgroundColor) so
 *     the color identity is preserved through the hover.
 *   - The chip is a button when `onClick` is provided, a span
 *     otherwise. ARIA: when interactive, the button announces the
 *     category name as the accessible label.
 */

import * as React from 'react'
import { X } from 'lucide-react'

export interface CategoryChipProps {
  /** Category object (or partial — only color + name + icon are read). */
  category: {
    name: string
    color?: string | null
    icon?: string | null
  }
  /** Size variant. `sm` is the default for inline list rows; `md`
   *  for filter pills; `lg` for the rules-list row highlight. */
  size?: 'sm' | 'md' | 'lg'
  /** Optional click handler — turns the chip into a button. */
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void
  /** Optional dismiss affordance (close button on the right). */
  onDismiss?: (e: React.MouseEvent<HTMLButtonElement>) => void
  /** ARIA override — defaults to the category name. */
  ariaLabel?: string
  /** When true, renders the chip in a "selected" state (e.g. a
   *  filter pill is currently active). */
  active?: boolean
  className?: string
}

/** Fallback color when a user-created category has no color yet. */
const FALLBACK_COLOR = '#94a3b8' // slate-400 (matches "Other" in seed)

const sizeClasses: Record<NonNullable<CategoryChipProps['size']>, string> = {
  sm: 'px-2 py-0.5 text-[11px] gap-1.5',
  md: 'px-2.5 py-1 text-xs gap-2',
  lg: 'px-3 py-1.5 text-sm gap-2',
}

const iconSizeClasses: Record<
  NonNullable<CategoryChipProps['size']>,
  string
> = {
  sm: 'text-[11px]',
  md: 'text-sm',
  lg: 'text-base',
}

const dotSizeClasses: Record<
  NonNullable<CategoryChipProps['size']>,
  string
> = {
  sm: 'w-1.5 h-1.5',
  md: 'w-2 h-2',
  lg: 'w-2.5 h-2.5',
}

export const CategoryChip = React.forwardRef<
  HTMLButtonElement,
  CategoryChipProps
>(function CategoryChip(
  {
    category,
    size = 'sm',
    onClick,
    onDismiss,
    ariaLabel,
    active = false,
    className = '',
  },
  ref,
) {
  const color = category.color || FALLBACK_COLOR
  const icon = category.icon || null
  const labelText = category.name || 'Uncategorized'

  // When active, the chip inverts: the solid color fills the entire
  // pill (matching the source-pill convention on the Settings
  // Merchant Rules card). When inactive, the chip carries the color
  // as a soft tint so the user sees the category identity without
  // overwhelming the surrounding UI.
  const stateClasses = active
    ? 'text-white shadow-sm'
    : 'text-on-surface bg-[var(--bg-tertiary)] border border-outline-variant/40'

  const baseClasses = [
    'inline-flex items-center rounded-full font-semibold whitespace-nowrap',
    'transition-all duration-[var(--duration-fast)]',
    'focus-visible:outline-2 focus-visible:outline-offset-2',
    'focus-visible:outline-[var(--primary-500)]',
    sizeClasses[size],
    stateClasses,
    onClick ? 'cursor-pointer hover:opacity-90 active:scale-[0.97]' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  const innerContent = (
    <>
      {/* Color dot — always rendered. Acts as the visual identity
          for the chip in dense lists. The solid color is the BE
          seed value, not a per-render hash. */}
      <span
        className={`${dotSizeClasses[size]} rounded-full flex-shrink-0`}
        style={{ backgroundColor: color }}
        aria-hidden="true"
      />
      {/* Optional emoji icon — the seed's value. Rendered inline
          so the chip layout handles a missing icon (the row
          collapses cleanly with no orphan spacing). */}
      {icon ? (
        <span
          className={`${iconSizeClasses[size]} flex-shrink-0`}
          aria-hidden="true"
        >
          {icon}
        </span>
      ) : null}
      <span className="truncate">{labelText}</span>
      {onDismiss ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onDismiss(e)
          }}
          className="
            ml-1 -mr-1 p-0.5 rounded-full
            hover:bg-black/10 active:bg-black/20
            focus-visible:outline-2 focus-visible:outline-offset-1
            focus-visible:outline-white
            transition-colors duration-[var(--duration-fast)]
          "
          aria-label={`Remove ${labelText} filter`}
          data-testid={`category-chip-dismiss-${labelText}`}
        >
          <X
            className={`${
              size === 'sm'
                ? 'w-2.5 h-2.5'
                : size === 'md'
                  ? 'w-3 h-3'
                  : 'w-3.5 h-3.5'
            }`}
            aria-hidden="true"
          />
        </button>
      ) : null}
    </>
  )

  if (onClick) {
    return (
      <button
        ref={ref}
        type="button"
        onClick={onClick}
        aria-label={ariaLabel || labelText}
        aria-pressed={active}
        className={baseClasses}
        style={active ? { backgroundColor: color } : undefined}
        data-testid={`category-chip-${labelText}`}
      >
        {innerContent}
      </button>
    )
  }
  return (
    <span
      className={baseClasses}
      aria-label={ariaLabel || labelText}
      data-testid={`category-chip-${labelText}`}
    >
      {innerContent}
    </span>
  )
})

/** CategoryDot — minimal visual primitive for inline use cases
 *  (settings dropdown menu rows, table-cell colour indicators,
 *  list-item prefixes). Renders a 1.5/2/2.5 char-height solid
 *  circle in the canonical color. */
export interface CategoryDotProps {
  category: {
    name?: string | null
    color?: string | null
  }
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

export function CategoryDot({
  category,
  size = 'sm',
  className = '',
}: CategoryDotProps) {
  const color = category.color || FALLBACK_COLOR
  const sizeCls = dotSizeClasses[size]
  return (
    <span
      className={`${sizeCls} rounded-full flex-shrink-0 ${className}`}
      style={{ backgroundColor: color }}
      aria-label={category.name ? `${category.name} indicator` : 'Category indicator'}
      role="presentation"
      data-testid={`category-dot-${category.name ?? 'unknown'}`}
    />
  )
}

export default CategoryChip
