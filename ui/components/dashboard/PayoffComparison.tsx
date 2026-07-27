'use client'

import { useMemo, useState } from 'react'
import { filterEligibleDebts, simulateAvalanche, simulateSnowball } from '@/lib/payoffStrategy'
import type { DebtItem } from '@/lib/api'
import { formatNumber } from '@/lib/format'
import { Trophy, Clock, DollarSign, TrendingDown, Zap, Target } from 'lucide-react'

interface PayoffComparisonProps {
  debts: DebtItem[]
}

export default function PayoffComparison({ debts }: PayoffComparisonProps) {
  const [extraPayment, setExtraPayment] = useState(0)

  const eligible = useMemo(() => filterEligibleDebts(debts), [debts])

  const { avalanche, snowball } = useMemo(() => {
    if (eligible.length === 0) {
      return { avalanche: null, snowball: null }
    }
    return {
      avalanche: simulateAvalanche(eligible, extraPayment),
      snowball: simulateSnowball(eligible, extraPayment),
    }
  }, [eligible, extraPayment])

  if (eligible.length < 2) return null

  const formatMonths = (months: number | null) => {
    if (months === null) return 'N/A'
    const y = Math.floor(months / 12)
    const m = months % 12
    if (y === 0) return `${m}m`
    if (m === 0) return `${y}y`
    return `${y}y ${m}m`
  }

  // Determine which strategy wins each metric
  const avalancheWinsInterest = !!(avalanche && snowball && avalanche.totalInterest < snowball.totalInterest - 0.01)
  const snowballWinsInterest = !!(avalanche && snowball && snowball.totalInterest < avalanche.totalInterest - 0.01)
  const avalancheWinsMonths = !!(avalanche && snowball && avalanche.totalMonths != null && snowball.totalMonths != null && avalanche.totalMonths < snowball.totalMonths)
  const snowballWinsMonths = !!(avalanche && snowball && avalanche.totalMonths != null && snowball.totalMonths != null && snowball.totalMonths < avalanche.totalMonths)

  const interestSavings = avalanche && snowball ? Math.abs(avalanche.totalInterest - snowball.totalInterest) : 0
  const tied = avalanche && snowball && !avalancheWinsInterest && !snowballWinsInterest

  const renderStrategyCard = (
    label: string,
    icon: React.ReactNode,
    accentColor: string,
    result: NonNullable<typeof avalanche>,
    winsInterest: boolean | undefined,
    winsMonths: boolean | undefined,
  ) => (
    <div className={`card p-6 relative overflow-hidden`}>
      {winsInterest ? (
        <div className="absolute top-3 right-3">
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[0.6rem] font-bold uppercase tracking-wider bg-success-100 text-success-700">
            <Trophy className="w-3 h-3" /> Best for savings
          </span>
        </div>
      ) : null}

      <div className="flex items-center gap-2 mb-4">
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${accentColor}`}>
          {icon}
        </div>
        <h4 className="text-sm font-bold text-on-surface">{label}</h4>
      </div>

      {/* Summary metrics */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div>
          <p className="text-[0.65rem] text-on-surface-variant">Total Interest</p>
          <p className={`text-sm font-bold tabular-nums ${winsInterest ? 'text-success-600' : 'text-on-surface'}`}>
            {formatNumber(result.totalInterest)}
          </p>
        </div>
        <div>
          <p className="text-[0.65rem] text-on-surface-variant">Payoff Time</p>
          <p className={`text-sm font-bold tabular-nums ${winsMonths ? 'text-success-600' : 'text-on-surface'}`}>
            {formatMonths(result.totalMonths)}
          </p>
        </div>
        <div>
          <p className="text-[0.65rem] text-on-surface-variant">Total Paid</p>
          <p className="text-sm font-bold tabular-nums text-on-surface">
            {formatNumber(result.totalPaid)}
          </p>
        </div>
      </div>

      {/* Payoff order */}
      <div>
        <p className="text-[0.65rem] font-bold uppercase tracking-wider text-on-surface-variant mb-2">Payoff Order</p>
        <div className="space-y-2">
          {result.payoffOrder.map((step, i) => (
            <div key={step.account_id} className="flex items-center gap-3 text-xs">
              <span className="w-5 h-5 rounded-full bg-slate-100 flex items-center justify-center text-[0.6rem] font-bold text-on-surface-variant shrink-0">
                {i + 1}
              </span>
              <span className="flex-1 text-on-surface truncate">{step.account_name}</span>
              <span className="text-on-surface-variant tabular-nums shrink-0">
                {formatMonths(step.monthPaidOff)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[var(--primary-50)] flex items-center justify-center border border-[var(--primary-200)]">
            <Zap className="w-4 h-4 text-[var(--primary-600)]" aria-hidden="true" />
          </div>
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-on-surface">Payoff Strategy</h3>
            <p className="text-xs text-on-surface-variant">
              Compare methods to become debt-free
            </p>
          </div>
        </div>

        {/* Extra payment input */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-on-surface-variant whitespace-nowrap">Extra $/mo:</label>
          <input
            type="number"
            min={0}
            step={50}
            value={extraPayment || ''}
            onChange={(e) => setExtraPayment(Math.max(0, Number(e.target.value) || 0))}
            placeholder="0"
            className="w-24 px-2 py-1 text-sm bg-surface-container border border-outline-variant/30 rounded-lg text-right tabular-nums"
          />
        </div>
      </div>

      {/* Savings insight banner */}
      {avalanche && snowball && (
        <div className="mb-4 p-3 rounded-lg bg-info-50 border border-info-200">
          <p className="text-xs text-info-700">
            {tied ? (
              <>Both strategies cost the <strong>same amount</strong> with this debt mix.</>
            ) : avalancheWinsInterest ? (
              <><strong>Avalanche saves            {formatNumber(interestSavings)}</strong> in interest vs Snowball.{snowballWinsMonths && snowball.totalMonths && avalanche.totalMonths && (<> But Snowball pays off {formatMonths(avalanche.totalMonths - snowball.totalMonths)} sooner.</>)}</>
            ) : (
              <><strong>Snowball saves            {formatNumber(interestSavings)}</strong> in interest vs Avalanche.{avalancheWinsMonths && avalanche.totalMonths && snowball.totalMonths && (<> But Avalanche pays off {formatMonths(snowball.totalMonths - avalanche.totalMonths)} sooner.</>)}</>
            )}
          </p>
        </div>
      )}

      {/* Strategy cards side by side */}
      {avalanche && snowball && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {renderStrategyCard(
            'Avalanche',
            <Target className="w-4 h-4 text-white" />,
            'bg-danger-500',
            avalanche,
            avalancheWinsInterest,
            avalancheWinsMonths,
          )}
          {renderStrategyCard(
            'Snowball',
            <TrendingDown className="w-4 h-4 text-white" />,
            'bg-info-500',
            snowball,
            snowballWinsInterest,
            snowballWinsMonths,
          )}
        </div>
      )}
    </div>
  )
}
