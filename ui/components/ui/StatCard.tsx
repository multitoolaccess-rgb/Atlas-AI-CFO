'use client';

import React from 'react';

interface StatCardProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string;
  value: string | number;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  /** Icon node (e.g. `<Wallet className="w-5 h-5" />`). Set sizing on the icon. */
  icon?: React.ReactNode;
  format?: 'currency' | 'percent' | 'number';
}

export default function StatCard({
  title,
  value,
  change,
  changeType = 'neutral',
  icon,
  format = 'currency',
  className = '',
  ...rest
}: StatCardProps) {
  const formatValue = (val: string | number, fmt: string): string => {
    if (typeof val === 'string') return val;
    switch (fmt) {
      case 'currency':
        return new Intl.NumberFormat('en-US', {
          style: 'currency',
          currency: 'USD',
          maximumFractionDigits: 0,
        }).format(val);
      case 'percent':
        return `${val.toFixed(1)}%`;
      case 'number':
      default:
        return new Intl.NumberFormat('en-US', {
          maximumFractionDigits: 0,
        }).format(val);
    }
  };

  const changeClass =
    changeType === 'positive'
      ? 'text-[var(--success-700)]'
      : changeType === 'negative'
        ? 'text-[var(--danger-700)]'
        : 'text-neutral';

  return (
    <div
      {...rest}
      className={`card p-6 rounded-[var(--radius-lg)] flex flex-col justify-between h-32 ${className}`}
      role="article"
      aria-label={`${title}: ${formatValue(value, format)}`}
    >
      <div className="flex-between">
        <span className="label-md text-secondary">{title}</span>
        {icon && (
          <span className="text-secondary inline-flex" aria-hidden="true">
            {icon}
          </span>
        )}
      </div>
      <div className="flex items-baseline gap-2">
        <span className="numeric-lg text-primary">
          {formatValue(value, format)}
        </span>
        {change && <span className={`body-sm font-semibold ${changeClass}`}>{change}</span>}
      </div>
    </div>
  );
}
