'use client';

import React from 'react';

/**
 * Extend native button attributes so callers can pass through
 * ``data-testid``, ``data-*``, ``aria-*``, ``name``, ``form``, ``value``,
 * and any other HTMLButtonElement field. Previously every unknown
 * prop was silently dropped by the manual prop list -- which made
 * RTL's ``screen.getByTestId('import-history-delete-99')`` queries in
 * the Vitest suite silently fail (the underlying <button> never
 * received the test-id, but the test code thought it did).
 */
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'tertiary' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  /** Icon node (e.g. `<SearchIcon className="w-4 h-4" />`). Sizing should be set on the icon itself. */
  icon?: React.ReactNode;
  iconPosition?: 'left' | 'right';
  /** Friendly spoken label; explicit prop so callers don't have to know to use ``aria-label``. */
  ariaLabel?: string;
}

const variantClasses: Record<NonNullable<ButtonProps['variant']>, string> = {
  primary:
    'bg-[var(--interactive-primary)] text-[var(--accent-on-primary)] hover:bg-[var(--interactive-hover)] hover:shadow-[var(--shadow-3)] active:bg-[var(--interactive-active)] disabled:bg-[var(--slate-400)]',
  secondary:
    'bg-[var(--slate-100)] text-[var(--text-primary)] hover:bg-[var(--slate-200)] active:bg-[var(--slate-300)] disabled:bg-[var(--slate-100)] disabled:opacity-50 dark:bg-[var(--slate-200)] dark:hover:bg-[var(--slate-300)] dark:active:bg-[var(--slate-400)]',
  tertiary:
    'bg-transparent text-[var(--text-secondary)] border border-[var(--border-color)] hover:bg-[var(--slate-100)] active:bg-[var(--slate-200)] disabled:opacity-50 dark:hover:bg-[var(--slate-200)] dark:active:bg-[var(--slate-300)]',
  danger:
    'bg-[var(--danger-500)] text-[var(--text-on-brand)] hover:bg-[var(--danger-600)] active:bg-[var(--danger-700)] disabled:bg-[var(--slate-400)]',
};

const sizeClasses: Record<NonNullable<ButtonProps['size']>, string> = {
  sm: 'px-3 py-1 text-sm rounded-md',
  md: 'px-4 py-2 rounded-lg',
  lg: 'px-6 py-3 text-lg rounded-lg',
};

const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  children,
  onClick,
  disabled = false,
  className = '',
  icon,
  iconPosition = 'left',
  type = 'button',
  ariaLabel,
  ...rest
}) => {
  const baseClasses =
    'inline-flex min-h-11 items-center justify-center gap-2 font-medium transition-[background-color,border-color,box-shadow,transform,color] duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-focus)] active:scale-[0.98] disabled:cursor-not-allowed';

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      className={`${baseClasses} ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
      {...rest}
    >
      {icon && iconPosition === 'left' && icon}
      {children}
      {icon && iconPosition === 'right' && icon}
    </button>
  );
};

export default Button;
