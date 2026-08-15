'use client';

import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import {
  LayoutDashboard,
  Wallet,
  Target,
  Landmark,
  BrainCircuit,
  Settings as SettingsIcon,
  HelpCircle,
  PanelLeftClose,
  PanelLeftOpen,
  ChevronDown,
  Newspaper,
  Orbit,
  ArrowDownUp,
  CalendarDays,
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
    key: 'home',
    label: 'Home',
    items: [
      { name: 'Mission Control', href: '/', icon: LayoutDashboard },
    ],
  },
  {
    key: 'money',
    label: 'Money',
    items: [
      { name: 'Cash Flow', href: '/cash-flow', icon: ArrowDownUp },
      { name: 'Plan', href: '/plan', icon: CalendarDays },
    ],
  },
  {
    key: 'wealth',
    label: 'Wealth',
    items: [
      { name: 'Wealth', href: '/wealth', icon: Landmark },
      { name: 'Portfolio', href: '/portfolio', icon: Wallet },
      { name: 'Goals', href: '/goals', icon: Target },
    ],
  },
  {
    key: 'intelligence',
    label: 'Intelligence',
    items: [
      { name: 'Decisions', href: '/decisions', icon: BrainCircuit },
      { name: 'Market Intelligence', href: '/market-intelligence', icon: Newspaper },
      { name: 'Scenario Lab', href: '/scenario-lab', icon: Orbit },
    ],
  },
  {
    key: 'system',
    label: 'System',
    items: [
      { name: 'Data Connections', href: '/data-connections', icon: Landmark },
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
  const searchParams = useSearchParams();
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
      className="atlas-sidebar h-dvh min-h-dvh fixed left-0 top-0 flex flex-col border-r z-50 transition-[width,background-color,border-color] duration-300 ease-out"
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
          <h1 className="text-[1.65rem] font-semibold tracking-[-0.04em] text-on-background dark:text-sidebar-text-active">
            Atlas
          </h1>
          <p className="sidebar-label mt-1 text-sm text-on-surface-variant opacity-80">
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
                  className="sidebar-group-label w-full flex items-center justify-between px-4 pt-5 pb-2 text-[0.8125rem] font-semibold text-on-surface-variant/75 hover:text-on-surface-variant transition-colors dark:text-sidebar-text-inactive/75 dark:hover:text-sidebar-text-inactive"
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
                    const [itemPath] = item.href.split('?');
                    const itemView = new URLSearchParams(item.href.split('?')[1] ?? '').get('view');
                    const isActive = pathname === itemPath && (!itemView || searchParams.get('view') === itemView);
                    const Icon = item.icon;
                    const linkClass = [
                      'group relative flex items-center rounded-[var(--radius-md)] transition-[color,background-color,box-shadow] duration-200',
                      'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
                      collapsed ? 'justify-center px-0 py-3' : 'gap-3 px-4 py-2.5',
                      isActive
                        ? 'nav-active text-on-surface font-semibold dark:text-sidebar-text-active'
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
                          <span className="sidebar-label text-[0.875rem] font-medium">
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
