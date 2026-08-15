'use client'

import { CheckCircle2, CircleAlert, Database, ShieldCheck } from 'lucide-react'

export type ScenarioAvailability = 'loading' | 'ready' | 'unavailable' | 'disabled' | 'no-goal'

interface ScenarioReadinessProps {
  goalName?: string
  availability: ScenarioAvailability
  baseline?: { forecastId: string; version: number; currency: string; freshness: string } | null
}

const availabilityCopy: Record<ScenarioAvailability, { label: string; description: string }> = {
  loading: { label: 'Checking readiness', description: 'Atlas is checking the selected goal and server-owned Scenario Lab state.' },
  ready: { label: 'Available', description: 'Results are calculated by Rules Service against an immutable baseline. The browser does not calculate projections.' },
  unavailable: { label: 'Unavailable', description: 'The server did not make Scenario Lab available. No local estimate is shown.' },
  disabled: { label: 'Disabled by server', description: 'Scenario Lab is default-off and must be enabled by server configuration. No client override is available.' },
  'no-goal': { label: 'Goal required', description: 'Scenario Lab is goal-scoped. Choose an owned goal before requesting a server result.' },
}

export default function ScenarioReadiness({ goalName, availability, baseline }: ScenarioReadinessProps) {
  const copy = availabilityCopy[availability]
  const icon = availability === 'ready' ? <CheckCircle2 className="h-5 w-5 text-success-600" aria-hidden="true" /> : availability === 'loading' ? <Database className="h-5 w-5 text-primary-600" aria-hidden="true" /> : <CircleAlert className="h-5 w-5 text-warning-600" aria-hidden="true" />

  return (
    <section className="card overflow-hidden p-5" aria-labelledby="scenario-readiness-heading">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className="rounded-xl border border-primary-200 bg-primary-50 p-2">{icon}</div>
          <div className="min-w-0">
            <p className="label-md text-secondary">Baseline readiness</p>
            <h2 id="scenario-readiness-heading" className="mt-1 headline-sm text-primary">{goalName ?? 'No goal selected'}</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-secondary">{copy.description}</p>
          </div>
        </div>
        <span className="shrink-0 rounded-full border border-outline-variant px-3 py-1 text-xs font-semibold text-secondary">{copy.label}</span>
      </div>
      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg bg-surface-container p-3"><p className="text-xs text-tertiary">Goal scope</p><p className="mt-1 text-sm font-medium text-primary">{goalName ?? 'Required'}</p></div>
        <div className="rounded-lg bg-surface-container p-3"><p className="text-xs text-tertiary">Baseline</p><p className="mt-1 break-all font-mono text-sm text-primary">{baseline ? `${baseline.forecastId.slice(0, 12)} · v${baseline.version}` : 'Not confirmed yet'}</p></div>
        <div className="rounded-lg bg-surface-container p-3"><p className="text-xs text-tertiary">Currency</p><p className="mt-1 text-sm font-medium text-primary">{baseline?.currency ?? 'Server-selected'}</p></div>
        <div className="rounded-lg bg-surface-container p-3"><p className="text-xs text-tertiary">Freshness</p><p className="mt-1 text-sm font-medium text-primary">{baseline?.freshness ?? 'Checked with result'}</p></div>
      </div>
      <p className="mt-4 flex items-start gap-2 text-xs leading-5 text-tertiary"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary-600" aria-hidden="true" />Deterministic conservative, base, and optimistic bands are assumptions, not probabilities or guarantees.</p>
    </section>
  )
}
