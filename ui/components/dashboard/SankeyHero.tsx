'use client'

import { useState, useMemo, useContext } from 'react'
import { GitBranch } from 'lucide-react'
import SankeyFlow from '@/components/charts/SankeyFlow'
import CountUp from '@/components/ui/CountUp'
import TimeRangeSelector from '@/components/ui/TimeRangeSelector'
import { AtlasFilterContext, type AtlasFilterState } from '@/components/ui/AtlasFilterContext'
import type { DashboardFlowsResponse, CashflowRole } from '@/lib/api'
import { ROLE_COLORS, ROLE_LABELS } from '@/lib/api'
import { DashboardFocusLayer, DashboardFocusToggle, useDashboardFocus } from '@/components/dashboard/ExpandableCard'

/** Range state from the unified filter context, with a no-op fallback so
 *  the component also renders standalone (unit tests) without a provider. */
function useFocusRange(): Pick<AtlasFilterState, 'timeRange' | 'setTimeRange'> {
  const ctx = useContext(AtlasFilterContext)
  return ctx ?? { timeRange: '30D' as const, setTimeRange: () => {} }
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface SankeyHeroProps {
  flows: DashboardFlowsResponse | null
  /** Label for the shared Cash Flow range. */
  rangeLabel?: string
  loading?: boolean
  className?: string
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function SankeyHero({ flows, rangeLabel, loading, className }: SankeyHeroProps) {
  const [activeNode, setActiveNode] = useState<string | null>(null)
  // In focus mode the card renders its OWN range selector (so the range
  // controls are always visible inside the focused layer, regardless of
  // the floating bar's behavior); the extra class scopes CSS to hide the
  // floating bar and reclaim its reserved space.
  const { focused, setFocused } = useDashboardFocus('dashboard-focus-sankey')
  const { timeRange, setTimeRange } = useFocusRange()

  const handleNodeClick = (nodeName: string) => {
    setActiveNode(prev => (prev === nodeName ? null : nodeName))
  }

  // Derive period label
  const periodLabel = useMemo(() => {
    if (!flows?.period_start) return ''
    const start = new Date(flows.period_start + 'T00:00:00')
    return start.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
  }, [flows?.period_start])

  const totalIncome = flows?.total_income ?? 0

  // Derive retained / overspend from the links.
  // Recharts may mutate source/target from indices to node objects after layout.
  // Phase C — Retained/Overspend links now originate from 'Total Income' (L1 node).
  const retainedLink = flows?.links.find(l => {
    const srcName = typeof l.source === 'object' ? (l.source as any).name : flows?.nodes[l.source]?.name
    const tgtName = typeof l.target === 'object' ? (l.target as any).name : flows?.nodes[l.target]?.name
    return srcName === 'Total Income' && tgtName === 'Retained'
  })
  const overspendLink = flows?.links.find(l => {
    const srcName = typeof l.source === 'object' ? (l.source as any).name : flows?.nodes[l.source]?.name
    const tgtName = typeof l.target === 'object' ? (l.target as any).name : flows?.nodes[l.target]?.name
    // Phase C: Overspend flows INTO Total Income (source=Overspend, target=Total Income)
    return srcName === 'Overspend' && tgtName === 'Total Income'
  })
  const retainedValue = retainedLink?.value ?? 0
  const overspendValue = overspendLink?.value ?? 0

  // Active roles for legend
  const activeRoles = useMemo<CashflowRole[]>(() => {
    if (!flows?.nodes.length) return []
    const seen = new Set<CashflowRole>()
    for (const n of flows.nodes) {
      const r = (n.role ?? n.node_type) as string
      if (r in ROLE_COLORS) seen.add(r as CashflowRole)
    }
    return Array.from(seen)
  }, [flows])

  if (loading) {
    return (
      <div className={`card p-6 ${className}`} aria-busy="true">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="skeleton w-8 h-8" />
            <div className="skeleton h-6 w-48" />
          </div>
          <div className="skeleton h-5 w-32" />
        </div>
        <div className="skeleton h-[400px] w-full" />
      </div>
    )
  }

  return (
    <DashboardFocusLayer focused={focused} title="Money Flow Engine">
      <div
        className={`card p-6 ${focused ? 'min-h-[calc(100vh-3rem)]' : ''} ${className}`}
        data-testid="sankey-hero"
      >
      {/* Header row — title, range, summary chips, and focus mode */}
      <div className="flex items-center justify-between gap-4 mb-2">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-[var(--primary-50)] border border-[var(--primary-200)] flex-shrink-0">
            <GitBranch className="w-4 h-4 text-[var(--primary-600)]" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-[var(--text-primary)]">Money Flow Engine</h2>
            <p className="text-xs text-[var(--text-tertiary)] truncate">
              {flows ? (rangeLabel ?? periodLabel) : 'No data yet'}
              {flows && flows.nodes.length > 0 && ' · click a node to drill down'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4 flex-shrink-0">
          {/* Focus mode carries its own range selector inside the card, so
              the range controls are always visible over the focused chart. */}
          {focused && (
            <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
          )}
          {/* Summary chips — earned income stays separate from balancing overspend. */}
          {flows && flows.nodes.length > 0 && (
            <div className="hidden md:flex items-center gap-4" data-testid="sankey-summary-chips">
              <div className="text-right">
                <p className="text-[11px] text-[var(--text-tertiary)] font-medium">Total Income</p>
                <p className="font-mono font-bold text-sm tabular-nums text-[var(--success-500)]" data-testid="sankey-total-income">
                  <span aria-hidden="true">$</span><CountUp end={Math.round(totalIncome)} duration={1000} />
                </p>
              </div>
              {retainedValue > 0 && (
                <div className="text-right">
                  <p className="text-[11px] text-[var(--text-tertiary)] font-medium">Retained</p>
                  <p className="font-mono font-bold text-sm tabular-nums text-[var(--info-500)]" data-testid="sankey-retained">
                    <span aria-hidden="true">$</span><CountUp end={Math.round(retainedValue)} duration={1000} />
                  </p>
                </div>
              )}
              {overspendValue > 0 && (
                <div className="text-right" title="Balancing flow for spending above earned income; not additional income">
                  <p className="text-[11px] text-[var(--text-tertiary)] font-medium">Overspend</p>
                  <p className="font-mono font-bold text-sm tabular-nums text-[var(--warning-500)]" data-testid="sankey-overspend">
                    <span aria-hidden="true">$</span><CountUp end={Math.round(overspendValue)} duration={1000} />
                  </p>
                </div>
              )}
            </div>
          )}
          <DashboardFocusToggle focused={focused} onToggle={() => setFocused((value) => !value)} />
        </div>
      </div>      {overspendValue > 0 && (
        <p className="mb-3 text-xs text-[var(--text-tertiary)]" data-testid="sankey-overspend-note">
          Overspend is a balancing flow for spending above earned income; it is not counted as earned income.
        </p>
      )}

      {/* Column section labels — Phase C: 4-stage hierarchical layout */}
      {flows && flows.nodes.length > 0 && (
        <div className="flex items-center justify-between mb-1 px-6">
          <span className="text-xs font-semibold text-[var(--success-500)]" style={{ fontFamily: 'var(--font-mono)' }}>
            Sources
          </span>
          <span className="text-xs font-semibold text-[var(--text-tertiary)]" style={{ fontFamily: 'var(--font-mono)' }}>
            Groups
          </span>
          <span className="text-xs font-semibold text-[var(--danger-500)]" style={{ fontFamily: 'var(--font-mono)' }}>
            Categories
          </span>
        </div>
      )}

      {/* Sankey chart */}
      {flows && flows.nodes.length > 0 ? (
        <SankeyFlow
          nodes={flows.nodes}
          links={flows.links}
          displayValues={{ 'Total Income': totalIncome, Overspend: overspendValue }}
          height={420}
          onNodeClick={handleNodeClick}
          activeNode={activeNode}
          fitViewport={focused}
        />
      ) : (
        <div className="flex items-center justify-center h-[400px] text-[var(--text-tertiary)]">
          <div className="text-center">
            <p className="text-sm font-medium mb-1">No flow data for this period.</p>
            <p className="text-xs">Upload statements or connect accounts to see your money flow.</p>
          </div>
        </div>
      )}

      {/* Role legend */}
      {activeRoles.length > 0 && (
        <div className="flex items-center gap-4 mt-4 pt-3 border-t border-[var(--border-subtle)]">
          {activeRoles.map((role) => (
            <div key={role} className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-[2px]" style={{ backgroundColor: ROLE_COLORS[role] }} />
              <span className="text-[11px] text-[var(--text-tertiary)] font-medium">{ROLE_LABELS[role]}</span>
            </div>
          ))}
        </div>
      )}

      {/* Active filter chip */}
      {activeNode && (
        <div className="mt-3 flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">
            Filtered: {activeNode}
            <button
              onClick={() => setActiveNode(null)}
              className="ml-1 text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
              aria-label="Clear filter"
            >
              ×
            </button>
          </span>
        </div>
      )}
      </div>
    </DashboardFocusLayer>
  )
}
