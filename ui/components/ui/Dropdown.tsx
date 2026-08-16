'use client';

import React, { useState, useRef, useEffect, useCallback, KeyboardEvent, cloneElement, isValidElement } from 'react';

export interface DropdownItem {
  id: string;
  label: string;
  icon?: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  destructive?: boolean;
  /** Renders a thin divider above this item (item still clickable). */
  divider?: boolean;
}

type DropdownAlign = 'left' | 'right';

interface DropdownProps {
  /** The clickable element that opens the menu. Any focusable element. */
  trigger: React.ReactElement;
  items: DropdownItem[];
  align?: DropdownAlign;
  className?: string;
}

const Dropdown: React.FC<DropdownProps> = ({
  trigger,
  items,
  align = 'left',
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  // Index of the first focusable (non-disabled) item within the items list.
  const enabledIndices = items
    .map((it, i) => (it.disabled ? -1 : i))
    .filter((i) => i !== -1);

  // Close on outside click.
  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  // Reset focus index when the menu opens.
  useEffect(() => {
    if (isOpen) {
      setFocusedIndex(enabledIndices[0] ?? -1);
    } else {
      setFocusedIndex(-1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  // Focus management: when focusedIndex changes, focus the matching item.
  useEffect(() => {
    if (!isOpen || focusedIndex < 0 || !menuRef.current) return;
    const node = menuRef.current.querySelector<HTMLButtonElement>(
      `[data-dropdown-index="${focusedIndex}"]`
    );
    node?.focus();
  }, [focusedIndex, isOpen]);

  const open = () => setIsOpen(true);
  const close = () => {
    setIsOpen(false);
    triggerRef.current?.focus();
  };

  const handleTriggerKey = (e: KeyboardEvent) => {
    if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      open();
    }
  };

  const handleMenuKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      close();
      return;
    }
    if (e.key === 'Tab' || e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      const dir = e.key === 'ArrowUp' ? -1 : 1;
      const currentPos = enabledIndices.indexOf(focusedIndex);
      let next = currentPos + dir;
      if (next < 0) next = enabledIndices.length - 1;
      if (next >= enabledIndices.length) next = 0;
      setFocusedIndex(enabledIndices[next]);
      return;
    }
    if (e.key === 'Home') {
      e.preventDefault();
      setFocusedIndex(enabledIndices[0] ?? -1);
      return;
    }
    if (e.key === 'End') {
      e.preventDefault();
      setFocusedIndex(enabledIndices[enabledIndices.length - 1] ?? -1);
      return;
    }
  };

  const handleItemClick = (item: DropdownItem) => {
    if (item.disabled) return;
    item.onClick?.();
    close();
  };

  // Cast trigger to a typed element so its props retain HTMLAttributes shape.
  const triggerElement = trigger as React.ReactElement<React.HTMLAttributes<HTMLElement>>;
  const triggerProps = triggerElement.props;

  // Hold the caller's ref in a stable ref-object so the merged ref callback
  // can keep a stable identity (useCallback) without putting the original
  // ref in its dependency array.
  const originalRefRef = useRef<React.Ref<HTMLElement> | undefined>(
    (triggerElement as React.ReactElement & { ref?: React.Ref<HTMLElement> }).ref
  );
  originalRefRef.current = (triggerElement as React.ReactElement & { ref?: React.Ref<HTMLElement> }).ref;

  const mergedRef = useCallback((node: HTMLElement | null) => {
    triggerRef.current = node;
    const originalRef = originalRefRef.current;
    if (typeof originalRef === 'function') {
      originalRef(node);
    } else if (originalRef && typeof originalRef === 'object' && 'current' in originalRef) {
      (originalRef as React.MutableRefObject<HTMLElement | null>).current = node;
    }
  }, []);

  // Augment the trigger element with click + keyboard handlers and ARIA.
  const triggerEl = isValidElement(triggerElement) ? cloneElement(triggerElement, {
    ref: mergedRef,
    onClick: (e: React.MouseEvent<HTMLElement>) => {
      e.stopPropagation();
      open();
      triggerProps.onClick?.(e);
    },
    onKeyDown: (e: KeyboardEvent<HTMLElement>) => {
      handleTriggerKey(e);
      triggerProps.onKeyDown?.(e);
    },
    'aria-haspopup': 'menu',
    'aria-expanded': isOpen,
  } as Partial<React.HTMLAttributes<HTMLElement>>) : trigger;

  const menuAlignClass = align === 'right' ? 'right-0' : 'left-0';

  return (
    <div ref={wrapperRef} className={`relative inline-block ${className}`}>
      {triggerEl}
      {isOpen && (
        <div
          ref={menuRef}
          role="menu"
          aria-orientation="vertical"
          onKeyDown={handleMenuKey}
          className={`
            absolute top-full mt-1
            ${menuAlignClass}
            z-50
            min-w-[12rem]
            bg-[var(--bg-primary)]
            border border-[var(--border-color)]
            rounded-[var(--radius-md)]
            shadow-[var(--shadow-4)]
            py-1
            animate-fadeIn
          `}
        >
          {items.map((item, idx) => (
            <React.Fragment key={item.id}>
              {item.divider && (
                <div
                  role="separator"
                  className="my-1 border-t border-[var(--border-subtle)]"
                />
              )}
              <button
                role="menuitem"
                type="button"
                tabIndex={focusedIndex === idx ? 0 : -1}
                disabled={item.disabled}
                data-dropdown-index={idx}
                onClick={() => handleItemClick(item)}
                className={`
                  w-full
                  flex items-center gap-2
                  px-3 py-2
                  text-sm text-left
                  transition-colors duration-[var(--duration-fast)]
                  focus-visible:outline-none
                  disabled:opacity-50 disabled:cursor-not-allowed
                  ${item.destructive
                    ? 'text-[var(--danger-600)] hover:bg-[var(--danger-50)] focus:bg-[var(--danger-50)]'
                    : 'text-[var(--text-primary)] hover:bg-[var(--slate-100)] focus:bg-[var(--slate-100)]'}
                `}
              >
                {item.icon && (
                  <span className="text-base leading-none" aria-hidden="true">
                    {item.icon}
                  </span>
                )}
                {item.label}
              </button>
            </React.Fragment>
          ))}
        </div>
      )}
    </div>
  );
};

export default Dropdown;
