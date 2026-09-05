'use client'

import { Landmark, PiggyBank, TrendingUp, Wallet } from 'lucide-react'
import StatCard from '@/components/ui/StatCard'
import type { DashboardSummary } from '@/lib/api'

interface HeroSummaryProps {
  loading?: boolean
  summary: DashboardSummary | null
  greeting?: string
}

export default function HeroSummary({ loading, summary, greeting }: HeroSummaryProps) {
  return (
    <section className="mb-8">
      {/* Header with greeting + portfolio status */}
      <div className="flex items-end justify-between mb-8">
        <div>
          <h1 className="headline-xl text-primary mb-2">
            {greeting ? `Hello, ${greeting}` : 'Loading…'}
          </h1>
          <p className="body-md text-secondary">
            {loading || !summary
              ? 'Fetching your latest figures…'
              : summary.transactions_count > 0
                ? `${summary.transactions_count} transactions tracked across ${summary.accounts_count} accounts.`
                : 'Connect an account or upload a statement to get started.'}
          </p>
        </div>
      </div>

      {/* Metrics Grid (real numbers from /api/dashboard/summary) */}
      {/* GAP-10 (UI-12): the four cards were ``col-span-3`` at every
          breakpoint, which squeezed them to ~72px on a 390px viewport
          and pushed the card icons past the right edge (scrollWidth
          407 > 390). Cards now go full-width on phones, 2-up on
          tablets, and back to 4-up on xl screens. */}
      <div className="bento-grid">
        <StatCard
          title="Net Worth"
          value={summary?.total_balance ?? 0}
          change={loading ? undefined : summary && summary.last_sync ? 'synced' : undefined}
          changeType={loading ? 'neutral' : 'positive'}
          icon={<Landmark className="w-5 h-5" aria-hidden="true" />}
          format="currency"
          className="col-span-12 md:col-span-6 xl:col-span-3"
        />
        <StatCard
          title="Cash Flow (month)"
          value={(summary?.total_income_month ?? 0) - (summary?.total_expenses_month ?? 0)}
          icon={<TrendingUp className="w-5 h-5" aria-hidden="true" />}
          format="currency"
          className="col-span-12 md:col-span-6 xl:col-span-3"
        />
        <StatCard
          title="Income (month)"
          value={summary?.total_income_month ?? 0}
          icon={<Wallet className="w-5 h-5" aria-hidden="true" />}
          format="currency"
          className="col-span-12 md:col-span-6 xl:col-span-3"
        />
        <StatCard
          title="Expenses (month)"
          value={summary?.total_expenses_month ?? 0}
          icon={<PiggyBank className="w-5 h-5" aria-hidden="true" />}
          format="currency"
          className="col-span-12 md:col-span-6 xl:col-span-3"
        />
      </div>
    </section>
  )
}
