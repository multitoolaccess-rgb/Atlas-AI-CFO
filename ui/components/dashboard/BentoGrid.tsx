'use client';

import React, { useMemo } from 'react';
import { useThemeColors } from '@/lib/themeColors';
import { ArrowUpRight, Landmark, PlusCircle, Shield, Sparkles, TrendingUp } from 'lucide-react';
import RecommendationCard from './RecommendationCard';
import ChartLine from '@/components/charts/ChartLine';
import ChartDonut from '@/components/charts/ChartDonut';
import type {
  DashboardSummary,
  DashboardTrendsResponse,
  DashboardBreakdownResponse,
  Account,
} from '@/lib/api';

/* ─── Account-type display mapping ─────────────────────────────── */
const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  checking: 'Checking',
  savings: 'Savings',
  credit_card: 'Credit Cards',
  investment: 'Investments',
  '401k': '401(k)',
  ira: 'IRA',
  hsa: 'HSA',
  '529': '529 Plan',
  loan: 'Loans',
  mortgage: 'Mortgage',
  crypto: 'Crypto',
  debit_card: 'Debit Card',
  other: 'Other',
};



interface BentoGridProps {
  summary: DashboardSummary;
  accounts: Account[];
  trends?: DashboardTrendsResponse | null;
  breakdown?: DashboardBreakdownResponse | null;
}

export default function BentoGrid({ summary, accounts, trends, breakdown }: BentoGridProps) {
  const tc = useThemeColors();

  // ─── Theme-aware allocation palette ──────────────────────────
  const ALLOCATION_COLORS = useMemo(() => [
    tc.account_0, tc.account_1, tc.account_2, tc.account_3,
    tc.account_4, tc.account_5,
    tc.spend, tc.earn,
  ], [tc]);

  // ─── Portfolio Growth from trends data ────────────────────────
  const portfolioData = (trends?.trends ?? []).map((t) => ({
    month: t.month,
    portfolio: t.income,
    benchmark: t.retained,
  }));

  const savingsRate = summary.total_income_month > 0
    ? Math.round(((summary.total_income_month - summary.total_expenses_month) / summary.total_income_month) * 100)
    : 0;

  const portfolioReturn = `+${savingsRate}%`;

  // ─── Risk Score from summary data ────────────────────────────
  const activeAccounts = accounts.filter((a) => a.is_active).length;
  const diversityScore = Math.min(activeAccounts * 15, 60);
  const savingsBonus = savingsRate >= 20 ? 25 : savingsRate >= 10 ? 15 : 5;
  const riskScore = Math.min(diversityScore + savingsBonus, 95);

  // ─── Asset Allocation from accounts ──────────────────────────
  const balanceByType = new Map<string, number>();
  accounts
    .filter((a) => a.is_active)
    .forEach((a) => {
      const key = (a.account_type ?? 'other').toLowerCase();
      balanceByType.set(key, (balanceByType.get(key) ?? 0) + a.current_balance);
    });

  const allocationSlices = Array.from(balanceByType.entries())
    .map(([type, balance]) => ({
      label: ACCOUNT_TYPE_LABELS[type] ?? type,
      value: Math.abs(balance),
    }))
    .sort((a, b) => b.value - a.value)
    .map((slice, i) => ({ ...slice, color: ALLOCATION_COLORS[i % ALLOCATION_COLORS.length] }));

  const totalAllocation = allocationSlices.reduce((s, x) => s + x.value, 0);

  // ─── Spending by Category from breakdown ──────────────────────
  const spendingData = (breakdown?.buckets ?? []).map((b) => ({
    name: b.label,
    value: b.amount,
    color: b.color,
  }));

  const totalMonthlySpend = breakdown?.total_spend ?? spendingData.reduce((s, d) => s + d.value, 0);

  // ─── Goal Progress from summary.user_goals ────────────────────
  const goals = useMemo(() =>
    (summary.user_goals ?? [])
      .filter((g) => !g.is_archived && g.target_amount > 0)
      .map((g) => ({
        label: g.name,
        percentage: Math.min(100, Math.round((summary.total_balance / g.target_amount) * 100)),
      })),
    [summary.user_goals, summary.total_balance],
  );

  // ─── Progress bar color helper ───────────────────────────────
  const getProgressColor = (percentage: number): string => {
    if (percentage >= 85) return 'progress-success';
    if (percentage >= 60) return 'progress-warning';
    return 'progress-danger';
  };

  // ─── Insight cards ───────────────────────────────────────────
  const insights = [
    {
      label: 'Savings Rate',
      value: `${savingsRate}%`,
      Icon: TrendingUp,
      color: savingsRate >= 20 ? 'text-positive' : savingsRate >= 10 ? 'text-warning' : 'text-danger',
    },
    {
      label: 'Accounts',
      value: `${summary.accounts_count} active`,
      Icon: Landmark,
      color: 'text-info',
    },
    {
      label: 'Risk Score',
      value: `${riskScore}/100`,
      Icon: Shield,
      color: riskScore >= 70 ? 'text-success-600' : riskScore >= 40 ? 'text-warning' : 'text-danger',
    },
  ];

  // ─── Data-driven recommendation ─────────────────────────────
  const recommendation = useMemo(() => {
    // Pick the most impactful recommendation based on user data
    if (savingsRate < 10 && summary.total_income_month > 0) {
      return {
        title: 'Boost Your Savings Rate',
        description: `Your savings rate is ${savingsRate}%, which is below the recommended 20%. Consider reviewing your spending categories to find areas to cut back. Even a 5% increase could add $${Math.round(summary.total_income_month * 0.05).toLocaleString()} to your savings monthly.`,
        impact: `Potential $${Math.round(summary.total_income_month * 0.12).toLocaleString()}/year additional savings`,
        priority: 'high' as const,
      };
    }
    if (goals.length > 0) {
      const nearestGoal = goals.reduce((a, b) => a.percentage > b.percentage ? a : b);
      if (nearestGoal.percentage >= 80) {
        return {
          title: `${nearestGoal.label} Almost Funded!`,
          description: `You're ${nearestGoal.percentage}% of the way to your ${nearestGoal.label} goal. A small boost in contributions could get you there faster. Consider increasing your monthly allocation by 10%.`,
          impact: 'Goal completion accelerated',
          priority: 'low' as const,
        };
      }
    }
    if (summary.total_expenses_month > summary.total_income_month * 0.9 && summary.total_income_month > 0) {
      return {
        title: 'Spending Nearing Income',
        description: `Your expenses are ${Math.round((summary.total_expenses_month / summary.total_income_month) * 100)}% of your income this month. Review your flexible spending categories to build a buffer and avoid dipping into savings.`,
        impact: 'Improved financial resilience',
        priority: 'medium' as const,
      };
    }
    return {
      title: 'Your Finances Are On Track',
      description: `With a ${savingsRate}% savings rate across ${summary.accounts_count} accounts, you're maintaining a healthy financial profile. Keep monitoring your goals and spending patterns.`,
      impact: 'Maintain current trajectory',
      priority: 'low' as const,
    };
  }, [savingsRate, summary.total_income_month, summary.total_expenses_month, summary.accounts_count, goals]);

  return (
    <div className="bento-grid">
      {/* ── Row 1, Left: Portfolio Growth (Line Chart) ──────────────── */}
      <div className="col-span-12 lg:col-span-7 card p-8">
        <div className="flex-between mb-8">
          <div>
            <h3 className="text-xl font-semibold text-primary">Portfolio Growth</h3>
            <p className="text-xs uppercase tracking-wider text-secondary mt-1 flex items-center gap-1">
              <ArrowUpRight className="w-3 h-3 text-positive" aria-hidden="true" />
              Savings rate: {portfolioReturn}
            </p>
          </div>
          <span className="text-xs text-secondary bg-slate-100 dark:bg-slate-700 px-3 py-1 rounded-md">
            Per global filter ↑
          </span>
        </div>

        {portfolioData.length > 0 ? (
          <ChartLine
            data={portfolioData}
            series={[
              { key: 'portfolio', name: 'Income', color: 'var(--primary-500)' },
              { key: 'benchmark', name: 'Retained', color: 'var(--success-500)', strokeDasharray: '5 5' },
            ]}
            xKey="month"
            height={256}
            currency
            showGrid
          />
        ) : (
          <div className="flex items-center justify-center h-64 text-secondary text-sm">
            No trend data available
          </div>
        )}
      </div>

      {/* ── Row 1, Right: Data-driven Recommendation ────────────────── */}
      <div className="col-span-12 lg:col-span-5">
        <RecommendationCard
          title={recommendation.title}
          description={recommendation.description}
          impact={recommendation.impact}
          priority={recommendation.priority}
        />
      </div>

      {/* ── Row 2, Left: Asset Allocation (Donut Chart) ─────────────── */}
      <div className="col-span-12 lg:col-span-5 card p-8">
        <div className="flex-between mb-4">
          <h3 className="text-xl font-semibold text-primary">Asset Allocation</h3>
          <Sparkles className="w-4 h-4 text-primary-300 opacity-50" aria-hidden="true" />
        </div>
        {allocationSlices.length > 0 ? (
          <ChartDonut
            slices={allocationSlices}
            centerLabel="Total"
            centerValue={totalAllocation}
            height={320}
            currency
          />
        ) : (
          <div className="flex items-center justify-center h-64 text-secondary text-sm">
            No accounts found
          </div>
        )}
      </div>

      {/* ── Row 2, Right: Goal Progress ─────────────────────────────── */}
      <div className="col-span-12 lg:col-span-7 card p-8">
        <div className="flex-between mb-6">
          <h3 className="text-xl font-semibold text-primary">Goal Progress</h3>
          <button
            className="p-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-md focus-ring transition-all"
            type="button"
            aria-label="Add new goal"
          >
            <PlusCircle className="w-5 h-5 text-primary-500" aria-hidden="true" />
          </button>
        </div>

        {goals.length > 0 ? (
          <div className="space-y-6">
            {goals.map((goal) => (
              <div key={goal.label}>
                <div className="flex-between mb-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-primary">
                    {goal.label}
                  </span>
                  <span className="text-xs font-bold uppercase tracking-wider text-secondary">
                    {goal.percentage}%
                  </span>
                </div>
                <div className="progress-bar">
                  <div
                    className={`${getProgressColor(goal.percentage)}`}
                    style={{ width: `${goal.percentage}%` }}
                    role="progressbar"
                    aria-valuenow={goal.percentage}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`${goal.label} progress`}
                  />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-40 text-secondary text-sm gap-2">
            <p>No goals configured yet</p>
            <p className="text-xs text-tertiary">Add a goal to track your financial targets</p>
          </div>
        )}
      </div>

      {/* ── Row 3, Left: Spending by Category (from breakdown) ──────── */}
      {spendingData.length > 0 && (
        <div className="col-span-12 lg:col-span-7 card p-8">
          <div className="flex-between mb-6">
            <div>
              <h3 className="text-xl font-semibold text-primary">Spending by Category</h3>
              <p className="text-xs uppercase tracking-wider text-secondary mt-1">
                {breakdown?.period ?? 'Current period'}
              </p>
            </div>
            <span className="text-sm font-mono font-semibold text-secondary">
              ${totalMonthlySpend.toLocaleString()}
            </span>
          </div>

          <div className="space-y-4">
            {spendingData.slice(0, 6).map((item) => {
              const pct = totalMonthlySpend > 0
                ? Math.round((item.value / totalMonthlySpend) * 100)
                : 0;
              return (
                <div key={item.name}>
                  <div className="flex-between mb-1">
                    <span className="text-sm text-primary font-medium">{item.name}</span>
                    <span className="text-xs text-secondary font-mono">
                      ${item.value.toLocaleString()} ({pct}%)
                    </span>
                  </div>
                  <div className="progress-bar">
                    <div
                      style={{ width: `${pct}%`, backgroundColor: item.color }}
                      role="progressbar"
                      aria-valuenow={pct}
                      aria-valuemin={0}
                      aria-valuemax={100}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Row 3, Right: Insights ──────────────────────────────────── */}
      <div className={`col-span-12 ${spendingData.length > 0 ? 'lg:col-span-5' : 'lg:col-span-12'} card p-8`}>
        <h3 className="text-xl font-semibold text-primary mb-6">Insights</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {insights.map((insight) => {
            const Icon = insight.Icon;
            return (
              <div
                key={insight.label}
                className="bg-slate-50 dark:bg-slate-800 rounded-xl p-4 text-center border border-slate-100 dark:border-slate-700"
              >
                <Icon className={`w-8 h-8 mx-auto ${insight.color} mb-2`} aria-hidden="true" />
                <p className="text-xs font-bold uppercase tracking-wider text-secondary mb-1">
                  {insight.label}
                </p>
                <p className="text-base font-semibold text-primary">{insight.value}</p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
