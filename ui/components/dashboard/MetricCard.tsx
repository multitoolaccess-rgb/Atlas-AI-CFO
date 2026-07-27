'use client';

import React from 'react';

interface MetricCardProps {
  label: string;
  value: number;
  trend?: number;
  trendType?: 'positive' | 'negative' | 'neutral';
  period?: string;
  /** Icon node (e.g. `<Wallet className="w-5 h-5" />`). Set sizing on the icon. */
  icon?: React.ReactNode;
  format?: 'currency' | 'percent' | 'number';
  actionable?: boolean;
  onClick?: () => void;
}

import { formatNumber } from '@/lib/format'

const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  trend,
  trendType = 'neutral',
  period,
  icon,
  format = 'currency',
  actionable = false,
  onClick,
}) => {
  const formatValue = (val: number, fmt: string): string => {
    switch (fmt) {
      case 'currency':
      case 'number':
      default:
        return formatNumber(val);
      case 'percent':
        return `${val.toFixed(1)}%`;
    }
  };

  const getTrendColor = (): string => {
    if (trend === undefined) return 'text-neutral';
    switch (trendType) {
      case 'positive':
        return 'text-positive';
      case 'negative':
        return 'text-negative';
      case 'neutral':
      default:
        return 'text-neutral';
    }
  };

  const getTrendArrow = (): string => {
    if (trend === undefined) return '';
    return trendType === 'positive' ? '↗' : trendType === 'negative' ? '↘' : '→';
  };

  const handleKeyDown = actionable
    ? (e: React.KeyboardEvent<HTMLDivElement>) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick?.();
        }
      }
    : undefined;

  return (
    <div
      className={`card ${actionable ? 'card-interactive' : ''} p-6 flex flex-col`}
      onClick={onClick}
      role={actionable ? 'button' : 'article'}
      tabIndex={actionable ? 0 : -1}
      onKeyDown={handleKeyDown}
    >
      <div className="flex-between mb-4">
        <span className="label-md text-secondary">{label}</span>
        {icon && (
          <span className="text-secondary inline-flex" aria-hidden="true">
            {icon}
          </span>
        )}
      </div>

      <div className="numeric-lg text-primary mb-2">{formatValue(value, format)}</div>

      {(trend !== undefined || period) && (
        <div className={`body-sm flex-between ${getTrendColor()}`}>
          <div className="flex items-center gap-2">
            {trend !== undefined && (
              <>
                <span>{getTrendArrow()}</span>
                <span>
                  {trendType === 'positive' ? '+' : ''}
                  {trend}
                </span>
              </>
            )}
          </div>
          {period && <span className="text-tertiary">{period}</span>}
        </div>
      )}
    </div>
  );
};

export default MetricCard;
