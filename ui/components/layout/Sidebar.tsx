'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Wallet,
  Target,
  Sparkles,
  Landmark,
  History,
  Settings as SettingsIcon,
  HelpCircle,
  Bot,
  PanelLeftClose,
  PanelLeftOpen,
  Receipt,
  TrendingUp,
  TrendingDown,
  CreditCard,
  ChevronDown,
  Orbit,
  Newspaper,
} from 'lucide-react';
import { useSidebar } from './SidebarContext';

type IconType = React.ComponentType<{
  className?: string;
  'aria-hidden'?: boolean | 'true' | 'false';
}>;

interface NavItem {
  name: string;
  href: string;
  icon: IconType;
}

interface NavGroup {
  key: string;
  label: string;
  items: NavItem[];
}

const navGroups: NavGroup[] = [
  {
    key: 'money',
    label: 'Money',
    items: [
      { name: 'Overview', href: '/', icon: LayoutDashboard },
      { name: 'Budgeting', href: '/budgeting', icon: Receipt },
      { name: 'Income', href: '/income', icon: TrendingUp },
      { name: 'Expenses', href: '/expenses', icon: TrendingDown },
    ],
  },
  {
    key: 'wealth',
    label: 'Wealth',
    items: [
      { name: 'Portfolio', href: '/portfolio', icon: Wallet },
      { name: 'Goals', href: '/goals', icon: Target },
      { name: 'Debts', href: '/debts', icon: CreditCard },
      { name: 'Universe', href: '/universe', icon: Orbit },
    ],
  },
  {
    key: 'tools',
    label: 'Tools',
    items: [
      { name: 'Recommendations', href: '/recommendations', icon: Sparkles },
      { name: 'Market Briefs', href: '/market-briefs', icon: Newspaper },
      { name: 'Scout', href: '/assistant', icon: Bot },
      { name: 'Activity', href: '/activity', icon: History },
      { name: 'Accounts', href: '/accounts', icon: Landmark },
    ],
  },
  {
    key: 'system',
    label: 'System',
    items: [
      { name: 'Settings', href: '/settings', icon: SettingsIcon },
      { name: 'Help', href: '/help', icon: HelpCircle },
    ],
  },
];

function NavTooltip({ label, visible }: { label: string; visible: boolean }) {
  if (!visible) return null;
  return (
    <span
      className="absolute left-full ml-2 px-2 py-1 rounded-md bg-on-surface text-surface text-xs font-medium whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-[60] dark:bg-slate-800 dark:text-sidebar-text-active dark:shadow-lg"
    >
      {label}
    </span>
  );
}

export default function Sidebar() {
  const pathname = usePathname();
  const { collapsed, toggleCollapsed, groupStates, toggleGroup } = useSidebar();

  const sidebarWidth = collapsed ? '4.5rem' : '16rem';
  const logoAreaClass = collapsed
    ? 'flex items-center flex-col px-2 pt-4 mb-6'
    : 'flex items-center justify-between p-6 pb-0 mb-6';
  const navClass = collapsed
    ? 'flex-1 space-y-1 px-2 overflow-y-auto'
    : 'flex-1 space-y-1 px-3 overflow-y-auto';

  return (
    <aside
      className="h-screen fixed left-0 top-0 bg-surface-container-lowest shadow-sm flex flex-col border-r border-outline-variant/30 z-50 transition-all duration-300 ease-in-out dark:bg-sidebar-bg dark:border-white/[0.06]"
      style={{ width: sidebarWidth }}
    >
      {/* Logo + toggle */}
      <div className={logoAreaClass}>
        {collapsed ? (
          <span className="text-lg font-bold text-on-background dark:text-sidebar-text-active mb-2">
            AT
          </span>
        ) : (
          <div>
          <h1 className="text-3xl font-bold text-on-background dark:text-sidebar-text-active">
            Atlas
          </h1>
          <p className="text-xs uppercase tracking-wider text-on-surface-variant opacity-70 mt-1">
            Financial Copilot
          </p>
          </div>
        )}
        <button
          type="button"
          onClick={toggleCollapsed}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="p-2 rounded-lg text-on-surface-variant hover:bg-surface-container dark:text-sidebar-text-inactive dark:hover:bg-sidebar-hover transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary dark:focus-visible:outline-sidebar-brand"
        >
          {collapsed ? (
            <PanelLeftOpen className="w-5 h-5" aria-hidden="true" />
          ) : (
            <PanelLeftClose className="w-5 h-5" aria-hidden="true" />
          )}
        </button>
      </div>

      <nav className={navClass} aria-label="Primary">
        {navGroups.map((group, groupIdx) => {
          const isExpanded = groupStates[group.key] !== false;

          return (
            <div key={group.key}>
              {/* Group header — only visible when sidebar is expanded */}
              {!collapsed && (
                <button
                  type="button"
                  onClick={() => toggleGroup(group.key)}
                  className="w-full flex items-center justify-between px-4 pt-4 pb-1 text-[0.65rem] font-bold uppercase tracking-[0.12em] text-on-surface-variant/60 hover:text-on-surface-variant transition-colors dark:text-sidebar-text-inactive/40 dark:hover:text-sidebar-text-inactive/70"
                  aria-expanded={isExpanded}
                >
                  <span>{group.label}</span>
                  <ChevronDown
                    className={`w-3 h-3 transition-transform duration-200 ${
                      isExpanded ? '' : '-rotate-90'
                    }`}
                    aria-hidden="true"
                  />
                </button>
              )}

              {/* Divider between groups when collapsed */}
              {collapsed && groupIdx > 0 && (
                <div className="mx-2 my-2 border-t border-outline-variant/20 dark:border-white/[0.06]" />
              )}

              {/* Nav items */}
              {(collapsed || isExpanded) && (
                <div className="space-y-0.5">
                  {group.items.map((item) => {
                    const isActive = pathname === item.href;
                    const Icon = item.icon;
                    const linkClass = [
                      'group relative flex items-center rounded-lg transition-all',
                      'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
                      collapsed ? 'justify-center px-0 py-3' : 'gap-3 px-4 py-2.5',
                      isActive
                        ? 'bg-surface-container-high text-on-surface font-bold scale-[0.98] active:scale-95 dark:bg-sidebar-active dark:text-sidebar-text-active dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]'
                        : 'text-on-surface-variant hover:bg-surface-container dark:text-sidebar-text-inactive dark:hover:bg-sidebar-hover',
                    ].join(' ');

                    return (
                      <Link
                        key={item.name}
                        href={item.href}
                        aria-current={isActive ? 'page' : undefined}
                        title={collapsed ? item.name : undefined}
                        className={linkClass}
                      >
                        <Icon
                          className={`w-5 h-5 shrink-0 ${isActive ? 'dark:text-sidebar-text-active' : 'dark:text-sidebar-text-inactive'}`}
                          aria-hidden="true"
                        />
                        {!collapsed && (
                          <span className="text-xs font-bold uppercase tracking-wider">
                            {item.name}
                          </span>
                        )}
                        <NavTooltip label={item.name} visible={collapsed} />
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}
