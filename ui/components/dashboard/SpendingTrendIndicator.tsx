'use client'

import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { formatCurrency } from '@/lib/format'

interface SpendingTrendIndicatorProps {
  current: number
  previous: number
  /** Show percentage change alongside arrow */
  showPercent?: boolean
  /** Size variant */
  size?: 'sm' | 'md'
  /** Additional class names */
  className?: string
}

/**
 * Calculates month-over-month spending change for a category
 * and renders a trend arrow with color coding:
 * - Green (↓) for savings (spending decreased)
 * - Red (↑) for overspending (spending increased)
 * - Gray (—) for no change
 */
export function calculateMoMChange(current: number, previous: number): {
  changePct: number
  direction: 'up' | 'down' | 'flat'
  isSavings: boolean
  isOverspending: boolean
} {
  if (previous === 0) {
    return {
      changePct: current > 0 ? 100 : 0,
      direction: current > 0 ? 'up' : 'flat',
      isSavings: false,
      isOverspending: current > 0,
    }
  }
  const changePct = ((current - previous) / Math.abs(previous)) * 100
  const direction = changePct > 0 ? 'up' : changePct < 0 ? 'down' : 'flat'
  return {
    changePct: Math.abs(changePct),
    direction,
    isSavings: changePct < 0,
    isOverspending: changePct > 0,
  }
}

export default function SpendingTrendIndicator({
  current,
  previous,
  showPercent = true,
  size = 'sm',
  className = '',
}: SpendingTrendIndicatorProps) {
  const { changePct, direction, isSavings, isOverspending } =
    calculateMoMChange(current, previous)

  const sizeClasses = size === 'sm' ? 'text-xs' : 'text-sm'
  const iconSize = size === 'sm' ? 14 : 16

  if (direction === 'flat') {
    return (
      <span className={`inline-flex items-center gap-0.5 ${sizeClasses} text-[var(--text-tertiary)] ${className}`}>
        <Minus className="w-3 h-3" />
        {showPercent && <span>0%</span>}
      </span>
    )
  }

  return (
    <span
      className={`inline-flex items-center gap-0.5 ${sizeClasses} font-medium ${className}`}
      style={{
        color: isSavings
          ? 'var(--success-600)'
          : isOverspending
            ? 'var(--danger-500)'
            : 'var(--text-tertiary)',
      }}
    >
      {direction === 'up' ? (
        <TrendingUp className="w-3 h-3" />
      ) : (
        <TrendingDown className="w-3 h-3" />
      )}
      {showPercent && (
        <span>
          {direction === 'up' ? '+' : ''}
          {changePct.toFixed(0)}%
        </span>
      )}
    </span>
  )
}

/**
 * Card wrapper that shows the trend arrow alongside the category spend.
 * Used within BudgetCategoryCard to add MoM comparison.
 */
interface TrendCardProps extends SpendingTrendIndicatorProps {
  label?: string
  currentLabel?: string
  previousLabel?: string
}

export function SpendingTrendCard({
  label = 'vs last month',
  current,
  previous,
  currentLabel,
  previousLabel,
  className = '',
}: TrendCardProps) {
  const { changePct, direction, isSavings, isOverspending } =
    calculateMoMChange(current, previous)

  const formatVal = (n: number) =>
    n === 0 ? '$0' : `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className="min-w-0 flex-1">
        <span className="text-[var(--text-secondary)]">{label}</span>
        <div className="flex items-center gap-1 mt-0.5">
          <span className="text-[var(--text-tertiary)] text-xs">
            {formatVal(current)} current
          </span>
          <span className="text-[var(--text-tertiary)] text-xs opacity-50">·</span>
          <span className="text-[var(--text-tertiary)] text-xs">
            {formatVal(previous)} prev
          </span>
        </div>
      </div>
      <div className="text-right">
        <SpendingTrendIndicator
          current={current}
          previous={previous}
          size="sm"
        />
        {isSavings && (
          <p className="text-[var(--success-600)] text-[10px] font-medium">
            Saving ${formatVal(previous - current).replace('$', '')}
          </p>
        )}
        {isOverspending && (
          <p className="text-[var(--danger-500)] text-[10px] font-medium">
            +${formatVal(current - previous).replace('$', '')} over
          </p>
        )}
      </div>
    </div>
  )
}
