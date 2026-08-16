'use client';

import React from 'react';

type BadgeVariant = 'success' | 'danger' | 'warning' | 'neutral' | 'info' | 'primary';
type BadgeSize = 'sm' | 'md';

interface BadgeProps {
  variant?: BadgeVariant;
  size?: BadgeSize;
  icon?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

const variantClasses: Record<BadgeVariant, string> = {
  success: 'bg-[var(--success-100)] text-[var(--success-700)]',
  danger:  'bg-[var(--danger-100)]  text-[var(--danger-700)]',
  warning: 'bg-[var(--warning-100)] text-[var(--warning-700)]',
  neutral: 'bg-[var(--slate-100)]   text-[var(--slate-700)]',
  info:    'bg-[var(--info-100)]    text-[var(--info-700)]',
  primary: 'bg-[var(--primary-100)] text-[var(--primary-700)]',
};

const sizeClasses: Record<BadgeSize, string> = {
  sm: 'px-2 py-0.5 text-[var(--label-sm-size)]',
  md: 'px-3 py-1 text-[var(--label-md-size)]',
};

const Badge: React.FC<BadgeProps> = ({
  variant = 'neutral',
  size = 'sm',
  icon,
  children,
  className = '',
}) => {
  return (
    <span
      className={`
        inline-flex items-center gap-1
        rounded-[var(--radius-full)]
        font-[var(--label-md-weight)]
        tracking-[var(--label-md-spacing)]
        uppercase
        transition-colors duration-[var(--duration-fast)]
        ${variantClasses[variant]}
        ${sizeClasses[size]}
        ${className}
      `}
      role="status"
    >
      {icon && <span className="text-sm leading-none">{icon}</span>}
      <span className="leading-none">{children}</span>
    </span>
  );
};

export default Badge;
