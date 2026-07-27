'use client'

import { useState, useMemo } from 'react'
import { GitBranch } from 'lucide-react'
import SankeyFlow from '@/components/charts/SankeyFlow'
import CountUp from '@/components/ui/CountUp'
import type { DashboardFlowsResponse, CashflowRole } from '@/lib/api'
import { ROLE_COLORS, ROLE_LABELS } from '@/lib/api'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface SankeyHeroProps {
  flows: DashboardFlowsResponse | null
  loading?: boolean
  className?: string
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function SankeyHero({ flows, loading, className }: SankeyHeroProps) {
  const [activeNode, setActiveNode] = useState<string | null>(null)

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
    <div
      className={`card p-6 ${className}`}
      data-testid="sankey-hero"
    >
      {/* Header row — Phase 3: more prominent title, CountUp summary chips */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          {/* Icon container — token-driven tint with no inline style.
              Tailwind opacity overlay (`bg-{n}/40`) gives the alpha tint
              without depending on color-mix() (Safari < 16.2 fallback). */}
          <div className="w-9 h-9 rounded-lg flex items-center justify-center bg-[var(--primary-100)] ring-1 ring-[var(--primary-500)]/40 dark:bg-[var(--primary-900)]">
            <GitBranch className="w-4 h-4 text-[var(--primary-600)]" aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              Money Flow Engine
            </h2>
            <p className="text-xs text-[var(--text-tertiary)]">
              {flows ? `${periodLabel}` : 'No data yet'}
              {flows && flows.nodes.length > 0 && ' · click a node to drill down'}
            </p>
          </div>
        </div>

        {/* Summary chips — Phase 3: CountUp for premium number animation */}
        {flows && flows.nodes.length > 0 && (
          <div className="hidden md:flex items-center gap-4" data-testid="sankey-summary-chips">
            <div className="text-right">
              <p className="text-[11px] text-[var(--text-tertiary)] font-medium">Total Income</p>
              <p
                className="font-mono font-bold text-sm tabular-nums text-[var(--success-500)]"
                data-testid="sankey-total-income"
              >
                <CountUp end={Math.round(totalIncome)} duration={1000} />
              </p>
            </div>
            {retainedValue > 0 && (
              <div className="text-right">
                <p className="text-[11px] text-[var(--text-tertiary)] font-medium">Retained</p>
                <p
                  className="font-mono font-bold text-sm tabular-nums text-[var(--info-500)]"
                  data-testid="sankey-retained"
                >
                  <CountUp end={Math.round(retainedValue)} duration={1000} />
                </p>
              </div>
            )}
            {overspendValue > 0 && (
              <div className="text-right">
                <p className="text-[11px] text-[var(--text-tertiary)] font-medium">Overspend</p>
                <p
                  className="font-mono font-bold text-sm tabular-nums text-[var(--warning-500)]"
                  data-testid="sankey-overspend"
                >
                  <CountUp end={Math.round(overspendValue)} duration={1000} />
                </p>
              </div>
            )}
          </div>
        )}
      </div>

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
          height={420}
          onNodeClick={handleNodeClick}
          activeNode={activeNode}
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
  )
}
