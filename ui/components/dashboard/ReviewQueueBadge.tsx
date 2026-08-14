'use client'

import { useMemo } from 'react'
import Link from 'next/link'
import { AlertCircle } from 'lucide-react'
import type { Transaction } from '@/lib/api'

interface ReviewQueueBadgeProps {
  transactions: Transaction[]
  className?: string
}

export default function ReviewQueueBadge({ transactions, className = '' }: ReviewQueueBadgeProps) {
  const uncategorizedCount = useMemo(
    () => transactions.filter((t) => !t.category_id && !t.category_name).length,
    [transactions],
  )

  if (uncategorizedCount === 0) return null

  return (
    <Link
      href="/cash-flow?view=transactions&status=uncategorized"
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-[var(--warning-50)] text-[var(--warning-700)] border border-[var(--warning-200)] hover:bg-[var(--warning-100)] transition-colors duration-150 ${className}`}
      aria-label={`${uncategorizedCount} transactions need categorization`}
    >
      <AlertCircle className="w-3.5 h-3.5" />
      <span>{uncategorizedCount} need review</span>
    </Link>
  )
}
