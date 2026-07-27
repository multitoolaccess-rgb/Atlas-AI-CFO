'use client';

import React, { forwardRef, useId } from 'react';

type InputSize = 'sm' | 'md' | 'lg';
type InputState = 'default' | 'error' | 'success';

interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size'> {
  label?: string;
  hint?: string;
  error?: string;
  size?: InputSize;
  state?: InputState;
  leftIcon?: string;
  rightIcon?: string;
  containerClassName?: string;
}

const sizeClasses: Record<InputSize, string> = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2 text-base',
  lg: 'px-5 py-3 text-lg',
};

const stateBorderClasses: Record<InputState, string> = {
  default: 'border-[var(--border-color)] focus:border-[var(--primary-500)] focus:ring-[var(--primary-500)]',
  error:   'border-[var(--danger-500)] focus:border-[var(--danger-500)] focus:ring-[var(--danger-500)]',
  success: 'border-[var(--success-500)] focus:border-[var(--success-500)] focus:ring-[var(--success-500)]',
};

const Input = forwardRef<HTMLInputElement, InputProps>(({
  label,
  hint,
  error,
  size = 'md',
  state = 'default',
  leftIcon,
  rightIcon,
  disabled,
  className = '',
  containerClassName = '',
  id,
  ...rest
}, ref) => {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const effectiveState: InputState = error ? 'error' : state;
  const describedById = error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined;

  return (
    <div className={`flex flex-col gap-1.5 w-full ${containerClassName}`}>
      {label && (
        <label
          htmlFor={inputId}
          className="label-md text-[var(--text-secondary)]"
        >
          {label}
        </label>
      )}
      <div className="relative">
        {leftIcon && (
          <span
            className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)] pointer-events-none text-lg"
            aria-hidden="true"
          >
            {leftIcon}
          </span>
        )}
        <input
          id={inputId}
          ref={ref}
          disabled={disabled}
          aria-invalid={effectiveState === 'error'}
          aria-describedby={describedById}
          className={`
            w-full
            bg-[var(--bg-primary)]
            text-[var(--text-primary)]
            border rounded-[var(--radius-md)]
            placeholder:text-[var(--text-tertiary)]
            transition-all duration-[var(--duration-fast)]
            focus:outline-none focus:ring-2
            disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-[var(--slate-100)]
            ${stateBorderClasses[effectiveState]}
            ${sizeClasses[size]}
            ${leftIcon ? 'pl-10' : ''}
            ${rightIcon ? 'pr-10' : ''}
            ${className}
          `}
          {...rest}
        />
        {rightIcon && (
          <span
            className="material-symbols-outlined absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)] pointer-events-none text-lg"
            aria-hidden="true"
          >
            {rightIcon}
          </span>
        )}
      </div>
      {error && (
        <p id={`${inputId}-error`} className="body-sm text-[var(--danger-600)]" role="alert">
          {error}
        </p>
      )}
      {!error && hint && (
        <p id={`${inputId}-hint`} className="body-sm text-[var(--text-tertiary)]">
          {hint}
        </p>
      )}
    </div>
  );
});

Input.displayName = 'Input';

export default Input;
