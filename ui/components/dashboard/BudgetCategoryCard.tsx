'use client'

import { motion, useReducedMotion } from 'framer-motion'
import type { BudgetCategoryStatus } from '@/lib/api'
import AnimatedRadialProgress from '@/components/charts/AnimatedRadialProgress'
import { formatNumber } from '@/lib/format'

interface BudgetCategoryCardProps {
  category: BudgetCategoryStatus
}

const groupColors: Record<string, string> = {
  fixed: 'var(--primary-500)',
  flexible: 'var(--info-500)',
  debt: 'var(--warning-500)',
  savings: 'var(--success-500)',
  other: 'var(--slate-400)',
}

export default function BudgetCategoryCard({ category }: BudgetCategoryCardProps) {
  const reduced = useReducedMotion()

  const formatCurrency = (n: number) => formatNumber(n)

  const isOver = category.percent_used > 100
  const isWarning = category.percent_used > 80 && !isOver
  const statusColor = isOver
    ? 'var(--danger-500)'
    : isWarning
      ? 'var(--warning-500)'
      : groupColors[category.budget_group] || 'var(--success-500)'

  return (
    <motion.div
      className="card flex items-center gap-4 p-4"
      initial={reduced ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduced ? { duration: 0 } : { duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      whileHover={reduced ? undefined : { y: -2 }}
      whileTap={reduced ? undefined : { scale: 0.99 }}
    >
      <AnimatedRadialProgress
        percentage={Math.min(category.percent_used, 100)}
        size={56}
        strokeWidth={5}
        color={statusColor}
        trackColor="var(--bg-tertiary)"
        className="shrink-0"
        label={
          <span className="text-[10px] font-bold text-[var(--text-primary)]">
            {category.percent_used.toFixed(0)}%
          </span>
        }
      />

      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <h4 className="truncate text-sm font-semibold text-[var(--text-primary)]">
            {category.category_name}
          </h4>
          <span
            className={`shrink-0 text-xs font-semibold ${
              isOver ? 'text-[var(--danger-500)]' : isWarning ? 'text-[var(--warning-500)]' : 'text-[var(--success-600)]'
            }`}
          >
            {formatCurrency(Math.abs(category.remaining))} {isOver ? 'over' : 'left'}
          </span>
        </div>

        <div className="mt-1 flex items-center justify-between text-xs text-[var(--text-tertiary)]">
          <span>
            {formatCurrency(category.actual)} <span className="opacity-60">of</span> {formatCurrency(category.planned)}
          </span>
          <span className="font-medium capitalize text-[var(--text-secondary)]">
            {category.budget_group}
          </span>
        </div>

      </div>
    </motion.div>
  )
}
