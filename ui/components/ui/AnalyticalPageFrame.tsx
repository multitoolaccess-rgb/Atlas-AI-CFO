import type { ReactNode } from 'react'

export type AnalyticalPageState = 'loading' | 'empty' | 'partial' | 'stale' | 'error' | 'ready'

export interface DrilldownContract { title: string; preserveFilterContext: true; evidenceLabel?: string }
export interface AnalyticalPageFrameProps {
  header: ReactNode; tabs?: ReactNode; contextBar?: ReactNode; positionStrip?: ReactNode; primaryVisualization?: ReactNode; attentionRail?: ReactNode; supportingModules?: ReactNode; drilldown?: DrilldownContract; state?: AnalyticalPageState; stateSlot?: ReactNode
}

/** Slot-only layout contract; it owns no data query, route, or financial calculation. */
export default function AnalyticalPageFrame({ header, tabs, contextBar, positionStrip, primaryVisualization, attentionRail, supportingModules, drilldown, state = 'ready', stateSlot }: AnalyticalPageFrameProps) {
  return <section data-analytical-state={state} data-drilldown-preserves-context={drilldown?.preserveFilterContext ?? false} className="space-y-4"><header>{header}{tabs}</header>{contextBar}{state === 'ready' ? <><section>{positionStrip}</section><div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]"><section>{primaryVisualization}</section>{attentionRail && <aside aria-label="Needs attention">{attentionRail}</aside>}</div>{supportingModules && <section>{supportingModules}</section>}</> : <section role={state === 'error' ? 'alert' : 'status'}>{stateSlot}</section>}</section>
}
