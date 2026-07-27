'use client';

import React from 'react';

type ProgressVariant = 'primary' | 'success' | 'warning' | 'danger';
type ProgressSize = 'sm' | 'md' | 'lg';

interface ProgressBarProps {
  /** Numeric value 0–100. Clamped internally. */
  value: number;
  variant?: ProgressVariant;
  size?: ProgressSize;
  /** Optional label rendered above the bar (e.g. "Retirement Fund") */
  label?: string;
  /** Show percentage text beside / above the bar */
  showPercentage?: boolean;
  className?: string;
}

const variantClasses: Record<ProgressVariant, string> = {
  primary: 'bg-[var(--primary-500)]',
  success: 'bg-[var(--success-500)]',
  warning: 'bg-[var(--warning-500)]',
  danger:  'bg-[var(--danger-500)]',
};

const heightClasses: Record<ProgressSize, string> = {
  sm: 'h-1',
  md: 'h-2',
  lg: 'h-3',
};

const ProgressBar: React.FC<ProgressBarProps> = ({
  value,
  variant = 'primary',
  size = 'md',
  label,
  showPercentage = false,
  className = '',
}) => {
  const safeValue = Math.min(100, Math.max(0, value));
  const rounded = Math.round(safeValue);

  return (
    <div className={`w-full ${className}`}>
      {(label || showPercentage) && (
        <div className="flex items-center justify-between mb-2">
          {label && <span className="label-md text-[var(--text-primary)]">{label}</span>}
          {showPercentage && (
            <span className="label-md text-[var(--text-secondary)]">{rounded}%</span>
          )}
        </div>
      )}
      <div
        className="w-full bg-[var(--slate-200)] rounded-[var(--radius-full)] overflow-hidden"
        role="progressbar"
        aria-valuenow={rounded}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ? `${label} progress: ${rounded}%` : `Progress: ${rounded}%`}
      >
        <div
          className={`
            ${heightClasses[size]}
            ${variantClasses[variant]}
            rounded-[var(--radius-full)]
            transition-all duration-500 ease-out
          `}
          style={{ width: `${safeValue}%` }}
        />
      </div>
    </div>
  );
};

export default ProgressBar;
