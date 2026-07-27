'use client';

import React, { useId, useState, KeyboardEvent, useRef } from 'react';

type TabsVariant = 'underline' | 'pill';

export interface TabsGroupItem {
  id: string;
  label: string;
  icon?: string;
  content: React.ReactNode;
  disabled?: boolean;
}

interface TabsGroupProps {
  items: TabsGroupItem[];
  /** Initial active tab id for uncontrolled mode. Ignored when `activeId` is provided. */
  defaultActiveId?: string;
  /** Active tab id for controlled mode. */
  activeId?: string;
  onChange?: (id: string) => void;
  variant?: TabsVariant;
  className?: string;
}

const TabsGroup: React.FC<TabsGroupProps> = ({
  items,
  defaultActiveId,
  activeId,
  onChange,
  variant = 'underline',
  className = '',
}) => {
  const baseId = useId();
  const [internalActive, setInternalActive] = useState<string>(
    activeId ?? defaultActiveId ?? items[0]?.id ?? ''
  );
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const isControlled = activeId !== undefined;
  const currentId = isControlled ? activeId : internalActive;

  const activate = (id: string, item: TabsGroupItem) => {
    if (item.disabled) return;
    if (!isControlled) setInternalActive(id);
    onChange?.(id);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft' && e.key !== 'Home' && e.key !== 'End') {
      return;
    }
    e.preventDefault();
    let next = index;
    if (e.key === 'ArrowRight') next = (index + 1) % items.length;
    if (e.key === 'ArrowLeft')  next = (index - 1 + items.length) % items.length;
    if (e.key === 'Home')       next = 0;
    if (e.key === 'End')        next = items.length - 1;
    const nextItem = items[next];
    activate(nextItem.id, nextItem);
    tabRefs.current[nextItem.id]?.focus();
  };

  const tablistClass = variant === 'pill'
    ? 'inline-flex p-1 bg-[var(--slate-100)] rounded-[var(--radius-md)] gap-1'
    : 'flex border-b border-[var(--border-color)] gap-1';

  const tabClass = (item: TabsGroupItem, isActive: boolean) => {
    if (variant === 'pill') {
      return `
        inline-flex items-center justify-center gap-2
        px-4 py-2
        text-sm font-medium
        rounded-[var(--radius-sm)]
        transition-all duration-[var(--duration-fast)]
        focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--primary-500)]
        disabled:opacity-50 disabled:cursor-not-allowed
        ${isActive
          ? 'bg-[var(--bg-primary)] text-[var(--text-primary)] shadow-[var(--shadow-1)]'
          : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}
      `;
    }
    // underline variant
    return `
      inline-flex items-center justify-center gap-2
      px-4 py-3
      text-sm font-medium
      border-b-2
      transition-all duration-[var(--duration-fast)]
      focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--primary-500)]
      disabled:opacity-50 disabled:cursor-not-allowed
      ${isActive
        ? 'border-[var(--primary-500)] text-[var(--primary-600)]'
        : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--slate-300)]'}
    `;
  };

  return (
    <div className={className}>
      <div
        role="tablist"
        aria-orientation="horizontal"
        className={tablistClass}
      >
        {items.map((item, idx) => {
          const isActive = item.id === currentId;
          return (
            <button
              key={item.id}
              id={`${baseId}-tab-${item.id}`}
              role="tab"
              type="button"
              tabIndex={isActive ? 0 : -1}
              aria-selected={isActive}
              aria-controls={`${baseId}-panel-${item.id}`}
              aria-disabled={item.disabled}
              disabled={item.disabled}
              ref={(el) => { tabRefs.current[item.id] = el; }}
              onClick={() => activate(item.id, item)}
              onKeyDown={(e) => handleKeyDown(e, idx)}
              className={tabClass(item, isActive)}
            >
              {item.icon && (
                <span className="material-symbols-outlined text-base leading-none" aria-hidden="true">
                  {item.icon}
                </span>
              )}
              {item.label}
            </button>
          );
        })}
      </div>

      {items.map((item) => {
        const isActive = item.id === currentId;
        return (
          <div
            key={item.id}
            id={`${baseId}-panel-${item.id}`}
            role="tabpanel"
            aria-labelledby={`${baseId}-tab-${item.id}`}
            hidden={!isActive}
            tabIndex={isActive ? 0 : -1}
            className="py-4 focus-visible:outline-none"
          >
            {item.content}
          </div>
        );
      })}
    </div>
  );
};

export default TabsGroup;
