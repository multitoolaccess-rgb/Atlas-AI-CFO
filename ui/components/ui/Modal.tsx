'use client';

import React, {
  useEffect,
  useRef,
  useCallback,
  KeyboardEvent,
  ReactNode,
  MouseEvent,
} from 'react';
import { createPortal } from 'react-dom';

type ModalSize = 'sm' | 'md' | 'lg' | 'xl';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  footer?: ReactNode;
  size?: ModalSize;
  /** Close when the backdrop is clicked (default true). */
  closeOnBackdropClick?: boolean;
  /** Close when the Escape key is pressed (default true). */
  closeOnEscape?: boolean;
  className?: string;
}

const sizeClasses: Record<ModalSize, string> = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
};

// Selector for focusable elements inside the modal.
const FOCUSABLE = [
  'button:not([disabled])',
  '[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

const Modal: React.FC<ModalProps> = ({
  open,
  onClose,
  title,
  children,
  footer,
  size = 'md',
  closeOnBackdropClick = true,
  closeOnEscape = true,
  className = '',
}) => {
  const modalRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  // Body scroll lock + restore previous focus + focus first element on open.
  useEffect(() => {
    if (!open) return;

    // Only retain focusable HTML elements (e.g. body / svg elements are skipped).
    const ae = document.activeElement;
    previouslyFocused.current = ae instanceof HTMLElement ? ae : null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    // Focus first focusable child after the modal mounts.
    const focusables = modalRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE);
    focusables?.[0]?.focus();

    return () => {
      document.body.style.overflow = prevOverflow;
      previouslyFocused.current?.focus?.();
    };
  }, [open]);

  // Trap Tab focus inside the modal and handle Escape.
  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLDivElement>) => {
    if (closeOnEscape && e.key === 'Escape') {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== 'Tab') return;
    const focusables = Array.from(
      modalRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []
    );
    if (!focusables.length) {
      e.preventDefault();
      return;
    }
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }, [closeOnEscape, onClose]);

  const handleBackdropClick = (e: MouseEvent<HTMLDivElement>) => {
    if (!closeOnBackdropClick) return;
    // Only close if the click is on the backdrop itself, not bubbling from content.
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  if (!open) return null;
  if (typeof document === 'undefined') return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex-center bg-[var(--bg-overlay)] animate-fadeIn"
      onClick={handleBackdropClick}
      aria-hidden="false"
    >
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? 'modal-title' : undefined}
        onKeyDown={handleKeyDown}
        className={`
          relative
          w-full ${sizeClasses[size]}
          mx-4
          bg-[var(--bg-primary)]
          rounded-[var(--radius-xl)]
          shadow-[var(--shadow-5)]
          animate-scaleIn
          focus:outline-none
          ${className}
        `}
      >
        {(title || closeOnBackdropClick || closeOnEscape) && (
          <div className="flex-between p-6 border-b border-[var(--border-subtle)]">
            {title && (
              <h2
                id="modal-title"
                className="headline-md text-[var(--text-primary)]"
              >
                {title}
              </h2>
            )}
            <button
              type="button"
              onClick={onClose}
              aria-label="Close modal"
              className="
                p-2 rounded-[var(--radius-md)]
                text-[var(--text-tertiary)]
                hover:text-[var(--text-primary)] hover:bg-[var(--slate-100)]
                focus:outline-2 focus:outline-offset-2 focus:outline-[var(--primary-500)]
                transition-colors duration-[var(--duration-fast)]
                ml-auto
              "
            >
              <span className="material-symbols-outlined text-lg leading-none" aria-hidden="true">
                close
              </span>
            </button>
          </div>
        )}

        <div className="p-6 text-[var(--text-primary)] max-h-[70vh] overflow-y-auto">
          {children}
        </div>

        {footer && (
          <div className="flex justify-end gap-3 p-4 border-t border-[var(--border-subtle)] bg-[var(--bg-secondary)] rounded-b-[var(--radius-xl)]">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body
  );
};

export default Modal;
