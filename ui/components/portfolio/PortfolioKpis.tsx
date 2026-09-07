'use client'

import { useMemo, type ReactNode } from 'react'
import {
  Banknote,
  Briefcase,
  Coins,
  CreditCard,
  GraduationCap,
  HeartPulse,
  Landmark,
  PiggyBank,
  TrendingUp,
  Wallet,
} from 'lucide-react'
import StatCard from '@/components/ui/StatCard'
import { CREDIT_ACCOUNT_TYPES } from '@/lib/api'
import type { Account, DashboardSummary, Holding, PortfolioValuationSummary } from '@/lib/api'

/** Display labels for every account type the parser/UI can produce. */
const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  checking: 'Checking',
  savings: 'Savings',
  money_market: 'Money Market',
  cd: 'CDs',
  credit_card: 'Credit Cards',
  loan: 'Loans',
  mortgage: 'Mortgage',
  investment: 'Brokerage',
  brokerage: 'Brokerage',
  '401k': '401(k)',
  ira: 'IRA',
  roth_ira: 'Roth IRA',
  hsa: 'HSA',
  '529': '529 Plan',
  crypto: 'Crypto',
  debit_card: 'Debit Card',
  other: 'Other',
}

/** Cash-like account types — liquid balances that are NOT invested. */
const CASH_TYPES = new Set(['checking', 'savings', 'money_market', 'cd'])

const TYPE_ICONS: Record<string, ReactNode> = {
  checking: <Wallet className="w-5 h-5" aria-hidden="true" />,
  savings: <PiggyBank className="w-5 h-5" aria-hidden="true" />,
  money_market: <Banknote className="w-5 h-5" aria-hidden="true" />,
  cd: <Landmark className="w-5 h-5" aria-hidden="true" />,
  credit_card: <CreditCard className="w-5 h-5" aria-hidden="true" />,
  loan: <Landmark className="w-5 h-5" aria-hidden="true" />,
  mortgage: <Landmark className="w-5 h-5" aria-hidden="true" />,
  investment: <TrendingUp className="w-5 h-5" aria-hidden="true" />,
  brokerage: <TrendingUp className="w-5 h-5" aria-hidden="true" />,
  '401k': <Briefcase className="w-5 h-5" aria-hidden="true" />,
  ira: <Briefcase className="w-5 h-5" aria-hidden="true" />,
  roth_ira: <Briefcase className="w-5 h-5" aria-hidden="true" />,
  hsa: <HeartPulse className="w-5 h-5" aria-hidden="true" />,
  '529': <GraduationCap className="w-5 h-5" aria-hidden="true" />,
  crypto: <Coins className="w-5 h-5" aria-hidden="true" />,
}

interface PortfolioKpisProps {
  ready: boolean
  summary: DashboardSummary | null
  accounts: Account[]
  valuation: PortfolioValuationSummary | null
  holdings: Holding[]
  pricesAvailable: boolean
}

export default function PortfolioKpis({
  ready,
  summary,
  accounts,
  valuation,
  holdings,
  pricesAvailable,
}: PortfolioKpisProps) {
  const activeAccounts = useMemo(() => accounts.filter((a) => a.is_active), [accounts])

  // Net worth comes from the dashboard summary (all account balances,
  // credit-adjusted server-side); investments from the holdings valuation
  // projection. The two differ ON PURPOSE: net worth includes cash
  // accounts and subtracts debt, while investments is only the holdings sum.
  const netWorth = summary?.total_balance ?? 0
  const investments = valuation?.grand_total ?? 0

  const { cashEquiv, cashCount, debt, debtCount } = useMemo(() => {
    let cash = 0
    let cashCount = 0
    let owed = 0
    let debtCount = 0
    for (const a of activeAccounts) {
      const type = (a.account_type ?? 'other').toLowerCase()
      if (CASH_TYPES.has(type)) {
        cash += a.current_balance ?? 0
        cashCount += 1
      }
      if (CREDIT_ACCOUNT_TYPES.has(type)) {
        owed += a.current_balance ?? 0
        debtCount += 1
      }
    }
    return { cashEquiv: cash, cashCount, debt: owed, debtCount }
  }, [activeAccounts])

  // Per account-type balance rows. Asset types are positive; credit
  // types render as owed (negative) so the net-worth math is visible.
  const typeRows = useMemo(() => {
    const byType = new Map<string, { balance: number; count: number }>()
    for (const a of activeAccounts) {
      const type = (a.account_type ?? 'other').toLowerCase()
      const row = byType.get(type) ?? { balance: 0, count: 0 }
      row.balance += a.current_balance ?? 0
      row.count += 1
      byType.set(type, row)
    }
    return Array.from(byType.entries())
      .map(([type, { balance, count }]) => ({
        type,
        label: ACCOUNT_TYPE_LABELS[type] ?? type,
        balance: CREDIT_ACCOUNT_TYPES.has(type) ? -balance : balance,
        count,
        isDebt: CREDIT_ACCOUNT_TYPES.has(type),
      }))
      .sort((a, b) => Math.abs(b.balance) - Math.abs(a.balance))
  }, [activeAccounts])

  // Insight cards — derived from the holdings list, never invented.
  const insights = useMemo(() => {
    const withBasis = holdings.filter(
      (h) => h.cost_basis_total != null && h.current_value != null,
    )
    const investedCapital = withBasis.reduce((s, h) => s + (h.cost_basis_total ?? 0), 0)
    const marketValue = withBasis.reduce((s, h) => s + (h.current_value ?? 0), 0)
    const unrealized = marketValue - investedCapital
    const unrealizedPct = investedCapital > 0 ? (unrealized / investedCapital) * 100 : null

    // Today's P&L: live_value today minus yesterday's value, derived per
    // holding from the server-computed day_change_pct.
    let todayPnl = 0
    let todayCount = 0
    for (const h of holdings) {
      if (h.live_value != null && h.day_change_pct != null) {
        const d = h.day_change_pct / 100
        todayPnl += h.live_value - h.live_value / (1 + d)
        todayCount += 1
      }
    }

    let top: Holding | null = null
    for (const h of holdings) {
      const v = h.live_value ?? h.current_value ?? 0
      const topV = top ? (top.live_value ?? top.current_value ?? 0) : -Infinity
      if (v > topV) top = h
    }
    const topValue = top ? (top.live_value ?? top.current_value ?? 0) : 0
    const topPct = investments > 0 && top ? (topValue / investments) * 100 : null

    return { investedCapital, unrealized, unrealizedPct, todayPnl, todayCount, top, topValue, topPct }
  }, [holdings, investments])

  return (
    <section className="mb-8 space-y-6" aria-label="Portfolio key metrics">
      {/* Headline row — net worth + portfolio composition */}
      <div className="bento-grid">
        <StatCard
          title="Net Worth"
          value={netWorth}
          change={ready && summary?.last_sync ? 'synced' : undefined}
          changeType="positive"
          icon={<Landmark className="w-5 h-5" aria-hidden="true" />}
          format="currency"
          className="col-span-12 md:col-span-6 xl:col-span-3"
        />
        <StatCard
          title="Investments"
          value={investments}
          change={
            valuation
              ? `${valuation.accounts.length} account${valuation.accounts.length === 1 ? '' : 's'}`
              : undefined
          }
          changeType="positive"
          icon={<TrendingUp className="w-5 h-5" aria-hidden="true" />}
          format="currency"
          className="col-span-12 md:col-span-6 xl:col-span-3"
        />
        <StatCard
          title="Cash & Equivalents"
          value={cashEquiv}
          change={cashCount > 0 ? `${cashCount} account${cashCount === 1 ? '' : 's'}` : undefined}
          changeType="positive"
          icon={<Wallet className="w-5 h-5" aria-hidden="true" />}
          format="currency"
          className="col-span-12 md:col-span-6 xl:col-span-3"
        />
        <StatCard
          title="Debt Owed"
          value={-debt}
          change={debtCount > 0 ? `${debtCount} account${debtCount === 1 ? '' : 's'}` : undefined}
          changeType={debt > 0 ? 'negative' : 'neutral'}
          icon={<CreditCard className="w-5 h-5" aria-hidden="true" />}
          format="currency"
          className="col-span-12 md:col-span-6 xl:col-span-3"
        />
      </div>

      {/* Per account-type balances — one card per type present */}
      {typeRows.length > 0 && (
        <div className="bento-grid">
          {typeRows.map((row) => (
            <StatCard
              key={row.type}
              title={row.label}
              value={row.balance}
              change={`${row.count} account${row.count === 1 ? '' : 's'}`}
              changeType={row.isDebt ? 'negative' : 'neutral'}
              icon={TYPE_ICONS[row.type] ?? <Wallet className="w-5 h-5" aria-hidden="true" />}
              format="currency"
              className="col-span-12 md:col-span-6 xl:col-span-3"
            />
          ))}
        </div>
      )}

      {/* Insight cards — performance vs cost basis + live movement */}
      {holdings.length > 0 && (
        <div className="bento-grid">
          <StatCard
            title="Unrealized Gain / Loss"
            value={insights.unrealized}
            change={
              insights.unrealizedPct != null
                ? `${insights.unrealizedPct >= 0 ? '+' : ''}${insights.unrealizedPct.toFixed(1)}% vs cost basis`
                : undefined
            }
            changeType={insights.unrealized >= 0 ? 'positive' : 'negative'}
            icon={<TrendingUp className="w-5 h-5" aria-hidden="true" />}
            format="currency"
            className="col-span-12 md:col-span-6 xl:col-span-3"
          />
          <StatCard
            title="Invested Capital"
            value={insights.investedCapital}
            change={`${holdings.length} position${holdings.length === 1 ? '' : 's'}`}
            changeType="neutral"
            icon={<PiggyBank className="w-5 h-5" aria-hidden="true" />}
            format="currency"
            className="col-span-12 md:col-span-6 xl:col-span-3"
          />
          <StatCard
            title="Today's P&L"
            value={pricesAvailable ? insights.todayPnl : 0}
            change={
              pricesAvailable
                ? `${insights.todayCount} priced symbol${insights.todayCount === 1 ? '' : 's'}`
                : 'offline — refresh for live'
            }
            changeType={insights.todayPnl >= 0 ? 'positive' : 'negative'}
            icon={<Coins className="w-5 h-5" aria-hidden="true" />}
            format="currency"
            className="col-span-12 md:col-span-6 xl:col-span-3"
          />
          <StatCard
            title="Top Position"
            value={insights.topValue}
            change={
              insights.top
                ? `${insights.top.symbol ?? '—'}${insights.topPct != null ? ` · ${insights.topPct.toFixed(1)}%` : ''}`
                : undefined
            }
            changeType="neutral"
            icon={<Briefcase className="w-5 h-5" aria-hidden="true" />}
            format="currency"
            className="col-span-12 md:col-span-6 xl:col-span-3"
          />
        </div>
      )}
    </section>
  )
}