'use client';

import { useEffect, useRef, useState } from 'react';
import { Search, Bell, Bot, X, CheckCheck, Trash2, AlertTriangle, CheckCircle2, Info, AlertOctagon } from 'lucide-react';
import { initHeadroom } from '@/lib/headroomInit';
import DarkModeToggle from '@/components/layout/DarkModeToggle';
import { useSidebar } from '@/components/layout/SidebarContext';
import { useNotifications, type Notification } from '@/components/providers/NotificationContext';
import type { Profile } from '@/lib/api';
import CommandPalette, { useCommandPalette } from '@/components/ui/CommandPalette';

interface HeaderProps {
  profile?: Profile | null;
  loading?: boolean;
}

function variantIcon(variant: Notification['variant']) {
  switch (variant) {
    case 'danger': return AlertOctagon
    case 'warning': return AlertTriangle
    case 'success': return CheckCircle2
    case 'info': return Info
  }
}

function variantColor(variant: Notification['variant']) {
  switch (variant) {
    case 'danger': return 'text-[var(--danger-600)]'
    case 'warning': return 'text-[var(--warning-600)]'
    case 'success': return 'text-[var(--success-600)]'
    case 'info': return 'text-[var(--primary-600)]'
  }
}

function timeAgo(ts: number): string {
  const sec = Math.floor((Date.now() - ts) / 1000)
  if (sec < 60) return 'just now'
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  return `${Math.floor(hr / 24)}d ago`
}

export default function Header({ profile, loading }: HeaderProps) {
  const initials = ((profile?.full_name || '') || 'Alex').slice(0, 2).toUpperCase();
  const { collapsed } = useSidebar();
  const { notifications, unreadCount, markAsRead, markAllAsRead, removeNotification, clearAll } = useNotifications();
  const [bellOpen, setBellOpen] = useState(false);
  const bellRef = useRef<HTMLDivElement>(null);
  const { open: paletteOpen, close: closePalette, toggle: togglePalette } = useCommandPalette();

  useEffect(() => {
    const headroom = initHeadroom('header', {
      offset: 0,
      tolerance: { up: 10, down: 0 },
      classes: { pinned: 'slide-down', unpinned: 'slide-up' },
    });
    return () => headroom?.destroy?.();
  }, []);

  // Close bell dropdown on outside click
  useEffect(() => {
    if (!bellOpen) return;
    const onPointer = (e: MouseEvent | TouchEvent) => {
      const target = e.target as Node | null;
      if (target && bellRef.current && !bellRef.current.contains(target)) {
        setBellOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setBellOpen(false);
    };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('touchstart', onPointer, { passive: true });
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('touchstart', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [bellOpen]);

  return (
    <header
      id="header"
      className="flex items-center px-6 py-4 sticky top-0 z-40 bg-background/80 backdrop-blur-md transition-all duration-300 ease-in-out ml-[var(--layout-ml)] w-[var(--layout-w)]"
      style={{
        '--layout-ml': collapsed ? '4.5rem' : '16rem',
        '--layout-w': collapsed ? 'calc(100vw - 4.5rem)' : 'calc(100vw - 16rem)',
      } as React.CSSProperties}
    >
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <div className="relative w-full max-w-sm">
          <button
            type="button"
            onClick={togglePalette}
            aria-label="Search (⌘K)"
            className="w-full flex items-center gap-3 pl-10 pr-4 py-2 bg-surface-container-low border border-outline-variant/50 dark:border-outline-variant/20 rounded-full text-on-surface-variant/50 hover:border-primary/50 focus:ring-2 focus:ring-primary focus:border-primary dark:focus:border-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary transition-all cursor-text"
          >
            <Search
              className="w-5 h-5 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
              aria-hidden="true"
            />
            <span className="flex-1 text-left text-sm">Search transactions, accounts, goals…</span>
            <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold bg-[var(--bg-tertiary)] text-[var(--text-tertiary)] border border-[var(--border-subtle)]">
              ⌘K
            </kbd>
          </button>
        </div>
      </div>

      <div className="flex items-center gap-1.5 shrink-0">
        {/* Notification bell with dropdown */}
        <div ref={bellRef} className="relative">
          <button
            type="button"
            aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
            aria-haspopup="dialog"
            aria-expanded={bellOpen}
            onClick={() => setBellOpen((o) => !o)}
            className="relative p-2 text-on-surface-variant hover:text-primary rounded-md transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            data-testid="header-notification-bell"
          >
            <Bell className="w-5 h-5" aria-hidden="true" />
            {unreadCount > 0 && (
              <span
                className="absolute -top-0.5 -right-0.5 flex items-center justify-center min-w-[1.1rem] h-[1.1rem] px-1 rounded-full bg-[var(--danger-500)] text-white text-[10px] font-bold"
                data-testid="header-notification-badge"
              >
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </button>

          {bellOpen && (
            <div
              role="dialog"
              aria-label="Notifications"
              className="absolute right-0 top-full mt-2 z-50 w-96 max-h-[28rem] overflow-hidden bg-[var(--bg-primary)] border border-[var(--border-color)] rounded-[var(--radius-lg)] shadow-[var(--shadow-4)] animate-fadeIn"
              data-testid="header-notification-dropdown"
            >
              {/* Header */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-outline-variant/20">
                <h3 className="label-md font-semibold text-on-surface">Notifications</h3>
                <div className="flex items-center gap-1">
                  {unreadCount > 0 && (
                    <button
                      type="button"
                      onClick={markAllAsRead}
                      className="p-1.5 rounded-[var(--radius-sm)] text-tertiary hover:text-primary hover:bg-[var(--bg-tertiary)] transition-colors"
                      aria-label="Mark all as read"
                      title="Mark all as read"
                      data-testid="notification-mark-all-read"
                    >
                      <CheckCheck className="w-4 h-4" />
                    </button>
                  )}
                  {notifications.length > 0 && (
                    <button
                      type="button"
                      onClick={clearAll}
                      className="p-1.5 rounded-[var(--radius-sm)] text-tertiary hover:text-primary hover:bg-[var(--bg-tertiary)] transition-colors"
                      aria-label="Clear all notifications"
                      title="Clear all"
                      data-testid="notification-clear-all"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>

              {/* Notification list */}
              <div className="overflow-y-auto max-h-[22rem]">
                {notifications.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
                    <Bell className="w-8 h-8 text-tertiary mb-2" aria-hidden="true" />
                    <p className="text-sm text-tertiary">No notifications yet</p>
                  </div>
                ) : (
                  <ul role="list" className="divide-y divide-outline-variant/10">
                    {notifications.map((n) => {
                      const Icon = variantIcon(n.variant);
                      return (
                        <li
                          key={n.id}
                          className={`
                            flex items-start gap-3 px-4 py-3 transition-colors
                            ${n.read ? 'opacity-70' : 'bg-[var(--primary-50)]/30'}
                            hover:bg-[var(--bg-tertiary)]
                          `}
                          data-testid={`notification-item-${n.id}`}
                        >
                          <Icon
                            className={`w-4 h-4 mt-0.5 shrink-0 ${variantColor(n.variant)}`}
                            aria-hidden="true"
                          />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-semibold text-on-surface truncate">{n.title}</p>
                            <p className="text-xs text-secondary mt-0.5 line-clamp-2">{n.message}</p>
                            <p className="text-[10px] text-tertiary mt-1">{timeAgo(n.timestamp)}</p>
                          </div>
                          <div className="flex items-center gap-1 shrink-0">
                            {!n.read && (
                              <button
                                type="button"
                                onClick={() => markAsRead(n.id)}
                                className="p-1 rounded text-tertiary hover:text-primary transition-colors"
                                aria-label="Mark as read"
                                title="Mark as read"
                              >
                                <CheckCheck className="w-3.5 h-3.5" />
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => removeNotification(n.id)}
                              className="p-1 rounded text-tertiary hover:text-primary transition-colors"
                              aria-label="Dismiss"
                              title="Dismiss"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </div>
          )}
        </div>

        <button
          type="button"
          aria-label="Open Scout"
          className="p-2 text-on-surface-variant hover:text-primary rounded-md transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          <Bot className="w-5 h-5" aria-hidden="true" />
        </button>
        <div className="relative">
          <DarkModeToggle />
        </div>
        <div
          aria-label={loading ? 'Loading user profile' : profile ? `Signed in as ${profile.full_name}` : 'Signed in as Alex'}
          className="h-9 w-9 rounded-full bg-primary text-on-primary flex-center font-bold ml-1 ring-2 ring-surface-container text-sm"
        >
          {initials}
        </div>
      </div>

      {/* Command palette — global Cmd+K search overlay */}
      <CommandPalette open={paletteOpen} onClose={closePalette} onNavigate={(href) => { window.location.assign(href) }} />
    </header>
  );
}
