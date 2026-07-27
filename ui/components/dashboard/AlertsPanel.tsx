'use client';

import React from 'react';
import {
  AlertTriangle,
  Calendar,
  Clock,
  ShieldAlert,
  TrendingUp,
  Zap,
} from 'lucide-react';
import type { AnomalyItem, UpcomingBillItem, InsightItem } from '@/lib/api';
import { formatNumber } from '@/lib/format';

interface AlertsPanelProps {
  anomalies: AnomalyItem[];
  upcomingBills: UpcomingBillItem[];
  insights: InsightItem[];
  loading?: boolean;
  className?: string;
}

export default function AlertsPanel({
  anomalies,
  upcomingBills,
  insights,
  loading = false,
  className,
}: AlertsPanelProps) {
  if (loading) {
    return (
      <div className={`card p-8 ${className ?? ''}`} aria-busy="true">
        <h3 className="text-xl font-semibold text-primary mb-6">Alerts & Insights</h3>
        <div className="space-y-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-16 w-full" />
          ))}
        </div>
      </div>
    );
  }

  const totalAlerts = anomalies.length + upcomingBills.length;
  // Only show warnings from insights
  const warnings = insights.filter((i) => i.type === 'warning').slice(0, 3);

  if (totalAlerts === 0 && warnings.length === 0) {
    return (
      <div className={`card p-8 ${className ?? ''}`}>
        <h3 className="text-xl font-semibold text-primary mb-4">Alerts & Insights</h3>
        <div className="flex flex-col items-center justify-center h-32 text-secondary text-sm gap-2">
          <ShieldAlert className="w-8 h-8 text-[var(--success-500)]" aria-hidden="true" />
          <p className="font-medium text-[var(--success-600)]">All clear</p>
          <p className="text-xs text-tertiary">No unusual spending or upcoming bills detected</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`card p-8 ${className ?? ''}`}>
      <div className="flex-between mb-6">
        <div>
          <h3 className="text-xl font-semibold text-primary">Alerts & Insights</h3>
          <p className="text-xs uppercase tracking-wider text-secondary mt-1">
            {totalAlerts} alert{totalAlerts !== 1 ? 's' : ''} require attention
          </p>
        </div>
        {totalAlerts > 0 && (
          <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-[var(--danger-500)] text-white text-xs font-bold">
            {totalAlerts}
          </span>
        )}
      </div>

      <div className="space-y-4" role="list" aria-label="Financial alerts">
        {/* Anomalies section */}
        {anomalies.length > 0 && (
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-secondary mb-3 flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5" aria-hidden="true" />
              Unusual Spending
            </p>
            <div className="space-y-2">
              {anomalies.slice(0, 3).map((anomaly) => (
                <div
                  key={anomaly.transaction_id}
                  className="flex items-center gap-3 p-3 rounded-xl bg-[var(--danger-50)] dark:bg-[var(--danger-500)]/10 border border-[var(--danger-200)] dark:border-[var(--danger-500)]/20"
                  role="listitem"
                >
                  <AlertTriangle className="w-4 h-4 text-[var(--danger-500)] flex-shrink-0" aria-hidden="true" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-primary truncate">{anomaly.merchant}</p>
                    <p className="text-xs text-secondary">
                      {formatNumber(anomaly.amount)} — {anomaly.multiplier.toFixed(1)}× the usual {formatNumber(anomaly.median)}
                    </p>
                  </div>
                  {anomaly.date && (
                    <span className="text-xs text-tertiary flex-shrink-0">
                      {new Date(anomaly.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                    </span>
                  )}
                </div>
              ))}
              {anomalies.length > 3 && (
                <p className="text-xs text-tertiary pl-3">+{anomalies.length - 3} more anomalies</p>
              )}
            </div>
          </div>
        )}

        {/* Upcoming bills section */}
        {upcomingBills.length > 0 && (
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-secondary mb-3 flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5" aria-hidden="true" />
              Upcoming Bills
            </p>
            <div className="space-y-2">
              {upcomingBills.slice(0, 4).map((bill) => {
                const daysUntil = bill.predicted_next_date
                  ? Math.ceil(
                      (new Date(bill.predicted_next_date).getTime() - Date.now()) /
                        (1000 * 60 * 60 * 24),
                    )
                  : null;
                const isUrgent = daysUntil !== null && daysUntil <= 7;

                return (
                  <div
                    key={bill.merchant}
                    className={`flex items-center gap-3 p-3 rounded-xl border ${
                      isUrgent
                        ? 'bg-[var(--warning-50)] dark:bg-[var(--warning-500)]/10 border-[var(--warning-200)] dark:border-[var(--warning-500)]/20'
                        : 'bg-slate-50 dark:bg-slate-800/50 border-slate-100 dark:border-slate-700'
                    }`}
                    role="listitem"
                  >
                    <Clock
                      className={`w-4 h-4 flex-shrink-0 ${
                        isUrgent ? 'text-[var(--warning-600)]' : 'text-secondary'
                      }`}
                      aria-hidden="true"
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-primary truncate">{bill.merchant}</p>
                      <p className="text-xs text-secondary">
                        {formatNumber(bill.median_amount)} · every {bill.median_interval_days} days
                      </p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className={`text-sm font-mono font-bold ${isUrgent ? 'text-[var(--warning-600)]' : 'text-primary'}`}>
                        {formatNumber(bill.median_amount)}
                      </p>
                      {daysUntil !== null && (
                        <p className={`text-xs ${isUrgent ? 'text-[var(--warning-600)]' : 'text-tertiary'}`}>
                          {daysUntil < 0 ? `${Math.abs(daysUntil)} day${Math.abs(daysUntil) !== 1 ? 's' : ''} overdue` : daysUntil === 0 ? 'Due today' : `in ${daysUntil} day${daysUntil !== 1 ? 's' : ''}`}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
              {upcomingBills.length > 4 && (
                <p className="text-xs text-tertiary pl-3">+{upcomingBills.length - 4} more upcoming</p>
              )}
            </div>
          </div>
        )}

        {/* Spending warnings from insights */}
        {warnings.length > 0 && (
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-secondary mb-3 flex items-center gap-1.5">
              <TrendingUp className="w-3.5 h-3.5" aria-hidden="true" />
              Spending Alerts
            </p>
            <div className="space-y-2">
              {warnings.map((warning) => (
                <div
                  key={warning.category}
                  className="flex items-center gap-3 p-3 rounded-xl bg-[var(--warning-50)] dark:bg-[var(--warning-500)]/10 border border-[var(--warning-200)] dark:border-[var(--warning-500)]/20"
                  role="listitem"
                >
                  <TrendingUp className="w-4 h-4 text-[var(--warning-600)] flex-shrink-0" aria-hidden="true" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-primary">{warning.category}</p>
                    <p className="text-xs text-secondary">{warning.message}</p>
                  </div>
                  <span className="text-xs font-mono font-bold text-[var(--danger-500)] flex-shrink-0">
                    +{warning.change_pct.toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
