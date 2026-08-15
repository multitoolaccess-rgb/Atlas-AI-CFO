'use client'

import { Archive, ChevronRight, History, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui'
import { formatDecimalString } from '@/lib/format'
import type { ScenarioListItem } from '@/lib/api_scenarios'

interface ScenarioHistoryProps {
  items: ScenarioListItem[]
  selectedId: string | null
  loading?: boolean
  onSelect: (id: string) => void
  onArchive: (id: string) => void
  mutating?: boolean
}

export default function ScenarioHistory({ items, selectedId, loading = false, onSelect, onArchive, mutating = false }: ScenarioHistoryProps) {
  return <section className="card p-5" aria-labelledby="scenario-history-heading"><div className="flex items-start gap-3"><History className="mt-1 h-5 w-5 shrink-0 text-primary-600" aria-hidden="true" /><div><h2 id="scenario-history-heading" className="headline-sm text-primary">Immutable scenario history</h2><p className="mt-1 text-sm leading-6 text-secondary">Archive changes the active lifecycle only. It does not delete the immutable server version or its evidence.</p></div></div>{loading ? <p className="mt-5 text-sm text-secondary" role="status">Loading saved scenarios…</p> : items.length === 0 ? <p className="mt-5 rounded-lg border border-dashed border-outline-variant p-4 text-sm text-secondary">No saved scenarios for this goal yet.</p> : <ul className="mt-5 space-y-2" aria-label="Saved scenarios">{items.map((item) => <li key={item.scenario_id}><div className={`flex flex-wrap items-center gap-3 rounded-lg border p-4 ${selectedId === item.scenario_id ? 'border-primary-500 bg-primary-50 dark:bg-primary-950/20' : 'border-outline-variant'}`}><button type="button" className="min-w-0 flex-1 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary" onClick={() => onSelect(item.scenario_id)} aria-current={selectedId === item.scenario_id ? 'true' : undefined}><span className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs text-tertiary">{item.scenario_id.slice(0, 8)} · v{item.version_number}</span><span className="rounded-full border border-outline-variant px-2 py-0.5 text-[11px] font-semibold text-secondary">{item.lifecycle_state}</span></span><span className="mt-2 block text-sm font-semibold text-primary">Ending net worth {formatDecimalString(item.ending_net_worth)}</span><span className="mt-1 block text-xs text-secondary">Difference {formatDecimalString(item.difference_from_baseline)} · {item.target_reached === null ? 'Target not provided' : item.target_reached ? 'Target reached' : 'Target not reached'} · {item.created_at ?? 'Timestamp unavailable'}</span></button><ChevronRight className="h-4 w-4 shrink-0 text-tertiary" aria-hidden="true" />{item.lifecycle_state === 'active' && <Button type="button" variant="tertiary" size="sm" onClick={() => onArchive(item.scenario_id)} disabled={mutating} aria-label={`Archive scenario ${item.scenario_id.slice(0, 8)}`} icon={mutating ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Archive className="h-4 w-4" aria-hidden="true" />}>Archive</Button>}</div></li>)}</ul>}</section>
}
