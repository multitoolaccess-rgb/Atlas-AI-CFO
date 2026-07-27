'use client';

import {
  TrendingUp, TrendingDown, AlertTriangle, Calendar, Wallet,
  BarChart3, GitCompare, Search, PiggyBank, Database,
} from 'lucide-react';

/**
 * Phase 30e — ToolCard component.
 *
 * Renders an inline card showing the result of an assistant tool call.
 * The card type is determined by the ``tool`` name:
 *
 * - ``get_totals`` → Summary card (balance, income, expenses)
 * - ``get_category_spend`` / ``get_merchant_spend`` → Summary card
 * - ``get_cash_flow`` → Summary card (income, expenses, net)
 * - ``compute_savings_rate`` → Summary card with progress bar
 * - ``get_trends`` → Mini bar chart (monthly expense trend)
 * - ``compare_periods`` → Side-by-side comparison table
 * - ``detect_anomalies`` → Alert list
 * - ``predict_upcoming_bills`` → Upcoming bills list
 * - ``compute_investable_surplus`` → Summary card with breakdown
 * - ``search_history`` → Search results list
 *
 * data-testid surface:
 * - ``tool-card`` — root container
 * - ``tool-card-{tool_name}`` — tool-specific variant
 * - ``tool-card-value-{key}`` — individual data values
 */

interface ToolCardProps {
  tool: string;
  result: Record<string, unknown>;
}

import { formatNumber } from '@/lib/format';

/** Format a number as a plain value (no currency symbol). */
function fmtNumber(val: unknown): string {
  if (typeof val !== 'number' || isNaN(val)) return '—';
  return formatNumber(val);
}

/** Format a number as a percentage. */
function fmtPct(val: unknown): string {
  if (typeof val !== 'number' || isNaN(val)) return '—';
  return `${val.toFixed(1)}%`;
}

/** A single stat in a summary card. */
function StatItem({
  label, value, testId, accent,
}: {
  label: string;
  value: string;
  testId: string;
  accent?: 'positive' | 'negative' | 'neutral';
}) {
  const color =
    accent === 'positive' ? 'text-[var(--success-600)]' :
    accent === 'negative' ? 'text-[var(--error-600)]' :
    'text-primary';
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-tertiary uppercase tracking-wide">{label}</span>
      <span className={`text-lg font-semibold ${color}`} data-testid={testId}>
        {value}
      </span>
    </div>
  );
}

/** Summary card for totals / cash flow / category spend. */
function SummaryCard({ tool, result }: { tool: string; result: Record<string, unknown> }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
      {'total_balance' in result && (
        <StatItem label="Total Balance" value={fmtNumber(result.total_balance)} testId="tool-card-value-total_balance" />
      )}
      {'total_income_month' in result && (
        <StatItem label="Income (Month)" value={fmtNumber(result.total_income_month)} testId="tool-card-value-total_income_month" accent="positive" />
      )}
      {'total_expenses_month' in result && (
        <StatItem label="Expenses (Month)" value={fmtNumber(result.total_expenses_month)} testId="tool-card-value-total_expenses_month" accent="negative" />
      )}
      {'income' in result && !('total_income_month' in result) && (
        <StatItem label="Income" value={fmtNumber(result.income)} testId="tool-card-value-income" accent="positive" />
      )}
      {'expenses' in result && !('total_expenses_month' in result) && (
        <StatItem label="Expenses" value={fmtNumber(result.expenses)} testId="tool-card-value-expenses" accent="negative" />
      )}
      {'net_cash_flow' in result && (
        <StatItem label="Net Cash Flow" value={fmtNumber(result.net_cash_flow)} testId="tool-card-value-net_cash_flow" accent={typeof result.net_cash_flow === 'number' && result.net_cash_flow >= 0 ? 'positive' : 'negative'} />
      )}
      {'net' in result && !('net_cash_flow' in result) && (
        <StatItem label="Net" value={fmtNumber(result.net)} testId="tool-card-value-net" accent={typeof result.net === 'number' && result.net >= 0 ? 'positive' : 'negative'} />
      )}
      {'total_spend' in result && (
        <StatItem label="Total Spend" value={fmtNumber(result.total_spend)} testId="tool-card-value-total_spend" accent="negative" />
      )}
      {'transaction_count' in result && (
        <StatItem label="Transactions" value={String(result.transaction_count)} testId="tool-card-value-transaction_count" />
      )}
      {'category' in result && (
        <StatItem label="Category" value={String(result.category)} testId="tool-card-value-category" />
      )}
      {'merchant' in result && (
        <StatItem label="Merchant" value={String(result.merchant)} testId="tool-card-value-merchant" />
      )}
      {'monthly_goal_target' in result && (
        <StatItem label="Monthly Goal Target" value={fmtNumber(result.monthly_goal_target)} testId="tool-card-value-monthly_goal_target" />
      )}
      {'investable_surplus' in result && (
        <StatItem label="Investable Surplus" value={fmtNumber(result.investable_surplus)} testId="tool-card-value-investable_surplus" accent={typeof result.investable_surplus === 'number' && result.investable_surplus >= 0 ? 'positive' : 'negative'} />
      )}
      {'goal_count' in result && (
        <StatItem label="Goals" value={String(result.goal_count)} testId="tool-card-value-goal_count" />
      )}
    </div>
  );
}

/** Savings rate card with a progress bar. */
function SavingsRateCard({ result }: { result: Record<string, unknown> }) {
  const rate = typeof result.savings_rate === 'number' ? result.savings_rate : 0;
  return (
    <div className="flex flex-col gap-3">
      <SummaryCard tool="compute_savings_rate" result={result} />
      <div className="mt-1">
        <div className="flex justify-between items-baseline mb-1">
          <span className="text-xs text-tertiary uppercase tracking-wide">Savings Rate</span>
          <span className="text-lg font-semibold text-primary" data-testid="tool-card-value-savings_rate">
            {fmtPct(rate)}
          </span>
        </div>
        <div className="h-2 rounded-full bg-surface-container overflow-hidden">
          <div
            className="h-full rounded-full bg-[var(--success-500)] transition-all duration-500"
            style={{ width: `${Math.min(100, Math.max(0, rate))}%` }}
          />
        </div>
      </div>
    </div>
  );
}

/** Mini bar chart for trends. */
function TrendsCard({ result }: { result: Record<string, unknown> }) {
  const trend = Array.isArray(result.trend) ? result.trend as Array<Record<string, unknown>> : [];
  const direction = String(result.direction || 'stable');
  const maxExpense = Math.max(...trend.map((t) => typeof t.expenses === 'number' ? t.expenses : 0), 1);
  const dirIcon = direction === 'increasing' ? <TrendingUp className="w-4 h-4 text-[var(--error-500)]" /> :
    direction === 'decreasing' ? <TrendingDown className="w-4 h-4 text-[var(--success-500)]" /> :
    <BarChart3 className="w-4 h-4 text-secondary" />;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        {dirIcon}
        <span className="text-sm font-medium text-secondary capitalize" data-testid="tool-card-value-direction">
          Expenses {direction}
        </span>
      </div>
      <div className="flex items-end gap-1.5 h-24" data-testid="tool-card-trend-chart">
        {trend.map((t, i) => {
          const expense = typeof t.expenses === 'number' ? t.expenses : 0;
          const heightPct = (expense / maxExpense) * 100;
          return (
            <div key={i} className="flex-1 flex flex-col items-center gap-1 min-w-0">
              <div className="text-[10px] text-tertiary truncate w-full text-center">
                {typeof t.month === 'string' ? t.month.slice(5) : ''}
              </div>
              <div
                className="w-full rounded-t bg-primary/70 hover:bg-primary transition-all duration-300"
                style={{ height: `${Math.max(2, heightPct)}%` }}
                title={fmtNumber(expense)}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Side-by-side comparison table. */
function ComparePeriodsCard({ result }: { result: Record<string, unknown> }) {
  const pa = result.period_a as Record<string, unknown> | undefined;
  const pb = result.period_b as Record<string, unknown> | undefined;
  const deltas = result.deltas as Record<string, unknown> | undefined;
  if (!pa || !pb) return <SummaryCard tool="compare_periods" result={result} />;

  const fmtDelta = (v: unknown) => {
    if (typeof v !== 'number') return '—';
    const sign = v >= 0 ? '+' : '';
    return `${sign}${fmtNumber(v)}`;
  };

  return (
    <table className="w-full text-sm" data-testid="tool-card-compare-table">
      <thead>
        <tr className="text-xs text-tertiary uppercase tracking-wide border-b border-outline-variant/20">
          <th className="text-left py-1.5 font-normal">Metric</th>
          <th className="text-right py-1.5 font-normal">Period A</th>
          <th className="text-right py-1.5 font-normal">Period B</th>
          <th className="text-right py-1.5 font-normal">Delta</th>
        </tr>
      </thead>
      <tbody>
        {['income', 'expenses', 'net'].map((key) => (
          <tr key={key} className="border-b border-outline-variant/10">
            <td className="py-1.5 capitalize text-secondary">{key}</td>
            <td className="text-right py-1.5 text-primary">{fmtNumber(pa[key])}</td>
            <td className="text-right py-1.5 text-primary">{fmtNumber(pb[key])}</td>
            <td className={`text-right py-1.5 font-medium ${typeof deltas?.[key] === 'number' && (deltas[key] as number) >= 0 ? 'text-[var(--success-600)]' : 'text-[var(--error-600)]'}`}>
              {fmtDelta(deltas?.[key])}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Anomaly alert list. */
function AnomaliesCard({ result }: { result: Record<string, unknown> }) {
  const anomalies = Array.isArray(result.anomalies) ? result.anomalies as Array<Record<string, unknown>> : [];
  if (anomalies.length === 0) {
    return (
      <div className="flex items-center gap-2 text-sm text-secondary" data-testid="tool-card-anomalies-empty">
        <AlertTriangle className="w-4 h-4 text-[var(--success-500)]" />
        No anomalies detected in the last {String(result.lookback_days || 90)} days.
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2" data-testid="tool-card-anomalies-list">
      {anomalies.map((a, i) => (
        <div key={i} className="flex items-center gap-3 p-2 rounded-lg bg-[var(--warning-50)] border border-[var(--warning-200)]">
          <AlertTriangle className="w-4 h-4 text-[var(--warning-600)] flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-primary truncate">{String(a.merchant || 'Unknown')}</div>
            <div className="text-xs text-tertiary">
              {fmtNumber(a.amount)} · {String(a.multiplier)}× the median of {fmtNumber(a.median)}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/** Upcoming bills list. */
function BillsCard({ result }: { result: Record<string, unknown> }) {
  const bills = Array.isArray(result.bills) ? result.bills as Array<Record<string, unknown>> : [];
  if (bills.length === 0) {
    return (
      <div className="flex items-center gap-2 text-sm text-secondary" data-testid="tool-card-bills-empty">
        <Calendar className="w-4 h-4" />
        No recurring bills detected.
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2" data-testid="tool-card-bills-list">
      {bills.map((b, i) => (
        <div key={i} className="flex items-center gap-3 p-2 rounded-lg bg-surface-container">
          <Calendar className="w-4 h-4 text-primary flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-primary truncate">{String(b.merchant || 'Unknown')}</div>
            <div className="text-xs text-tertiary">
              Next: {String(b.predicted_next_date || '—')} · {fmtNumber(b.median_amount)}
            </div>
          </div>
          <div className="flex-shrink-0 text-xs text-tertiary">
            {Math.round(typeof b.confidence === 'number' ? b.confidence * 100 : 0)}% confidence
          </div>
        </div>
      ))}
    </div>
  );
}

/** Search history results. */
function SearchHistoryCard({ result }: { result: Record<string, unknown> }) {
  const matches = Array.isArray(result.matches) ? result.matches as Array<Record<string, unknown>> : [];
  if (matches.length === 0) {
    return (
      <div className="text-sm text-secondary" data-testid="tool-card-search-empty">
        No past messages found for &ldquo;{String(result.query || '')}&rdquo;.
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2" data-testid="tool-card-search-list">
      {matches.map((m, i) => (
        <div key={i} className="p-2 rounded-lg bg-surface-container text-sm">
          <span className="text-xs text-tertiary mr-2">
            {String(m.role || '')}:
          </span>
          <span className="text-secondary">{String(m.content || '')}</span>
        </div>
      ))}
    </div>
  );
}

/** Tool icon mapping. */
const TOOL_ICONS: Record<string, React.ReactNode> = {
  get_totals: <Wallet className="w-4 h-4" />,
  get_category_spend: <Wallet className="w-4 h-4" />,
  get_merchant_spend: <Wallet className="w-4 h-4" />,
  get_cash_flow: <PiggyBank className="w-4 h-4" />,
  compute_savings_rate: <PiggyBank className="w-4 h-4" />,
  get_trends: <BarChart3 className="w-4 h-4" />,
  compare_periods: <GitCompare className="w-4 h-4" />,
  detect_anomalies: <AlertTriangle className="w-4 h-4" />,
  predict_upcoming_bills: <Calendar className="w-4 h-4" />,
  compute_investable_surplus: <PiggyBank className="w-4 h-4" />,
  search_history: <Search className="w-4 h-4" />,
};

/** Tool display name mapping. */
const TOOL_LABELS: Record<string, string> = {
  get_totals: 'Account Totals',
  get_category_spend: 'Category Spend',
  get_merchant_spend: 'Merchant Spend',
  get_cash_flow: 'Cash Flow',
  compute_savings_rate: 'Savings Rate',
  get_trends: 'Spending Trends',
  compare_periods: 'Period Comparison',
  detect_anomalies: 'Anomaly Detection',
  predict_upcoming_bills: 'Upcoming Bills',
  compute_investable_surplus: 'Investable Surplus',
  search_history: 'Search History',
};

export default function ToolCard({ tool, result }: ToolCardProps) {
  // Don't render a card for errors or null results.
  if (!result || typeof result !== 'object') return null;
  if ('error' in result) {
    return (
      <div
        className="rounded-xl border border-[var(--error-200)] bg-[var(--error-50)] p-3 my-2"
        data-testid="tool-card"
        data-testid-tool={tool}
      >
        <div className="flex items-center gap-2 text-sm text-[var(--error-700)]">
          <AlertTriangle className="w-4 h-4" />
          {String(result.error)}
        </div>
      </div>
    );
  }

  const icon = TOOL_ICONS[tool] || <Database className="w-4 h-4" />;
  const label = TOOL_LABELS[tool] || tool;

  // Pick the card renderer based on the tool.
  let cardContent: React.ReactNode;
  if (tool === 'get_trends') {
    cardContent = <TrendsCard result={result} />;
  } else if (tool === 'compare_periods') {
    cardContent = <ComparePeriodsCard result={result} />;
  } else if (tool === 'detect_anomalies') {
    cardContent = <AnomaliesCard result={result} />;
  } else if (tool === 'predict_upcoming_bills') {
    cardContent = <BillsCard result={result} />;
  } else if (tool === 'search_history') {
    cardContent = <SearchHistoryCard result={result} />;
  } else if (tool === 'compute_savings_rate') {
    cardContent = <SavingsRateCard result={result} />;
  } else {
    cardContent = <SummaryCard tool={tool} result={result} />;
  }

  return (
    <div
      className="rounded-xl border border-outline-variant/30 bg-surface-container-low p-4 my-2"
      data-testid="tool-card"
      data-testid-tool={tool}
    >
      <div className="flex items-center gap-2 mb-3">
        <span className="text-primary">{icon}</span>
        <span className="text-xs font-medium text-secondary uppercase tracking-wide">
          {label}
        </span>
      </div>
      {cardContent}
    </div>
  );
}
