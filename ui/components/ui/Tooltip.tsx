'use client';

import React, { useState, useRef, useId, cloneElement, isValidElement } from 'react';

type TooltipPosition = 'top' | 'bottom' | 'left' | 'right';

interface TooltipProps {
  /** Content displayed inside the tooltip pop-up. */
  content: React.ReactNode;
  /** Tooltip position relative to its trigger. */
  position?: TooltipPosition;
  /** Show delay in ms before the tooltip appears on hover/focus. */
  delay?: number;
  /** The element that triggers the tooltip. Must accept refs. */
  children: React.ReactElement;
  className?: string;
}

const positionClasses: Record<TooltipPosition, string> = {
  top:    'bottom-full left-1/2 -translate-x-1/2 mb-2',
  bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
  left:   'right-full top-1/2 -translate-y-1/2 mr-2',
  right:  'left-full top-1/2 -translate-y-1/2 ml-2',
};

const arrowClasses: Record<TooltipPosition, string> = {
  top:    'top-full left-1/2 -translate-x-1/2 border-l-transparent border-r-transparent border-b-transparent border-t-[var(--text-primary)]',
  bottom: 'bottom-full left-1/2 -translate-x-1/2 border-l-transparent border-r-transparent border-t-transparent border-b-[var(--text-primary)]',
  left:   'left-full top-1/2 -translate-y-1/2 border-t-transparent border-b-transparent border-r-transparent border-l-[var(--text-primary)]',
  right:  'right-full top-1/2 -translate-y-1/2 border-t-transparent border-b-transparent border-l-transparent border-r-[var(--text-primary)]',
};

const Tooltip: React.FC<TooltipProps> = ({
  content,
  position = 'top',
  delay = 200,
  children,
  className = '',
}) => {
  const [isVisible, setIsVisible] = useState(false);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const wrapperRef = useRef<HTMLSpanElement>(null);
  // Stable id per tooltip instance — used to wire aria-describedby to the popup.
  const tooltipId = useId();

  const show = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setIsVisible(true), delay);
  };

  const hide = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setIsVisible(false);
  };

  // Cast children to a typed React element so props retain their
  // HTMLAttributes shape (otherwise TS infers `unknown` for cloneElement props).
  const childElement = children as React.ReactElement<React.HTMLAttributes<HTMLElement>>;

  // Clone the child to attach event handlers and aria-describedby.
  // Only HTMLElement children are supported (Tooltip needs a real DOM ref).
  const trigger = isValidElement(childElement) ? cloneElement(childElement, {
    onMouseEnter: (e: React.MouseEvent<HTMLElement>) => {
      show();
      childElement.props.onMouseEnter?.(e);
    },
    onMouseLeave: (e: React.MouseEvent<HTMLElement>) => {
      hide();
      childElement.props.onMouseLeave?.(e);
    },
    onFocus: (e: React.FocusEvent<HTMLElement>) => {
      show();
      childElement.props.onFocus?.(e);
    },
    onBlur: (e: React.FocusEvent<HTMLElement>) => {
      hide();
      childElement.props.onBlur?.(e);
    },
    'aria-describedby': isVisible ? tooltipId : undefined,
  } as Partial<React.HTMLAttributes<HTMLElement>>) : children;

  return (
    <span ref={wrapperRef} className={`relative inline-flex ${className}`}>
      {trigger}
      {isVisible && (
        <span
          id={tooltipId}
          role="tooltip"
          className={`
            absolute z-50
            px-3 py-1.5
            rounded-[var(--radius-md)]
            bg-[var(--text-primary)]
            text-[var(--bg-primary)]
            text-xs font-medium
            whitespace-nowrap
            shadow-[var(--shadow-3)]
            animate-fadeIn
            pointer-events-none
            ${positionClasses[position]}
          `}
        >
          {content}
          <span
            className={`absolute w-0 h-0 border-4 ${arrowClasses[position]}`}
            aria-hidden="true"
          />
        </span>
      )}
    </span>
  );
};

export default Tooltip;
