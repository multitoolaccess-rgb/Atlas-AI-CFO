'use client';

import React, { forwardRef, useId } from 'react';
import { ChevronDown } from 'lucide-react';

type SelectSize = 'sm' | 'md' | 'lg';
type SelectState = 'default' | 'error' | 'success';

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

interface SelectProps
  extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  options: SelectOption[];
  label?: string;
  hint?: string;
  error?: string;
  size?: SelectSize;
  state?: SelectState;
  placeholder?: string;
  containerClassName?: string;
  /** When provided, behaves as a controlled select. */
  value?: string;
  /** Initial value for uncontrolled usage. */
  defaultValue?: string;
}

const sizeClasses: Record<SelectSize, string> = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2 text-base',
  lg: 'px-5 py-3 text-lg',
};

const stateBorderClasses: Record<SelectState, string> = {
  default: 'border-[var(--border-color)] focus:border-[var(--primary-500)] focus:ring-[var(--primary-500)]',
  error:   'border-[var(--danger-500)] focus:border-[var(--danger-500)] focus:ring-[var(--danger-500)]',
  success: 'border-[var(--success-500)] focus:border-[var(--success-500)] focus:ring-[var(--success-500)]',
};

const Select = forwardRef<HTMLSelectElement, SelectProps>(({
  options,
  label,
  hint,
  error,
  size = 'md',
  state = 'default',
  placeholder,
  disabled,
  className = '',
  containerClassName = '',
  id,
  ...rest
}, ref) => {
  const generatedId = useId();
  const selectId = id ?? generatedId;
  const effectiveState: SelectState = error ? 'error' : state;
  const describedById = error ? `${selectId}-error` : hint ? `${selectId}-hint` : undefined;

  return (
    <div className={`flex flex-col gap-1.5 w-full ${containerClassName}`}>
      {label && (
        <label
          htmlFor={selectId}
          className="label-md text-[var(--text-secondary)]"
        >
          {label}
        </label>
      )}
      <div className="relative">
        <select
          id={selectId}
          ref={ref}
          disabled={disabled}
          aria-invalid={effectiveState === 'error'}
          aria-describedby={describedById}
          className={`
            w-full
            appearance-none
            bg-[var(--bg-primary)]
            text-[var(--text-primary)]
            border rounded-[var(--radius-md)]
            pr-10
            transition-all duration-[var(--duration-fast)]
            focus:outline-none focus:ring-2
            disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-[var(--slate-100)]
            ${stateBorderClasses[effectiveState]}
            ${sizeClasses[size]}
            ${className}
          `}
          {...rest}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((opt) => (
            <option key={opt.value} value={opt.value} disabled={opt.disabled}>
              {opt.label}
            </option>
          ))}
        </select>
        <ChevronDown
          className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-tertiary)] pointer-events-none"
          aria-hidden="true"
        />
      </div>
      {error && (
        <p id={`${selectId}-error`} className="body-sm text-[var(--danger-600)]" role="alert">
          {error}
        </p>
      )}
      {!error && hint && (
        <p id={`${selectId}-hint`} className="body-sm text-[var(--text-tertiary)]">
          {hint}
        </p>
      )}
    </div>
  );
});

Select.displayName = 'Select';

export default Select;
