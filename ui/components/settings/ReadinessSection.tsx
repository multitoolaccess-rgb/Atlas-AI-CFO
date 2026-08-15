'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import Card from '@/components/ui/Card'
import { rulesService, type ReadinessComponent, type ReadinessResponse } from '@/lib/api'
import { classifyErrorMessage } from '@/lib/errors'

const LABELS: Record<string, string> = {
  runtime: 'Runtime',
  storage: 'Storage and migrations',
  financial_authority: 'Financial authority',
  forecasts: 'Forecast baseline',
  decision_history: 'Decision history',
  market_intelligence: 'Market Intelligence',
  scenario_lab: 'Scenario Lab',
  privacy_safety: 'Privacy and safety boundaries',
}

const STATE_LABELS: Record<ReadinessComponent['state'], string> = {
  ready: 'Ready',
  unavailable: 'Unavailable',
  blocked: 'Blocked',
  degraded: 'Degraded',
  disabled: 'Disabled',
}

const STATE_CLASSES: Record<ReadinessComponent['state'], string> = {
  ready: 'border-success-200 bg-success-50 text-success-800',
  unavailable: 'border-danger-200 bg-danger-50 text-danger-800',
  blocked: 'border-warning-200 bg-warning-50 text-warning-800',
  degraded: 'border-warning-200 bg-warning-50 text-warning-800',
  disabled: 'border-outline-variant/40 bg-surface-container text-secondary',
}

function overallLabel(state: ReadinessResponse['overall_state']): string {
  switch (state) {
    case 'ready': return 'Ready for the reviewed local profile'
    case 'ready_with_blocked_optional_capabilities': return 'Ready with optional capabilities blocked'
    case 'configuration_failure': return 'Configuration requires attention'
    case 'unsafe_state': return 'Unsafe configuration'
  }
}

export default function ReadinessSection() {
  const [snapshot, setSnapshot] = useState<ReadinessResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    rulesService.getReadiness()
      .then((value) => {
        if (!cancelled) {
          setSnapshot(value)
          setError(null)
          setLoading(false)
        }
      })
      .catch((cause) => {
        if (!cancelled) {
          setError(classifyErrorMessage(cause))
          setLoading(false)
        }
      })
    return () => { cancelled = true }
  }, [])

  return (
    <section aria-labelledby="readiness-title" className="mt-8 max-w-4xl" data-testid="readiness-section">
      <div className="mb-4">
        <p className="label-sm text-accent-primary">System / local operations</p>
        <h2 id="readiness-title" className="headline-md text-primary mt-1">Readiness</h2>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-secondary">
          Server-owned checks for this local installation. This surface observes configuration; it never enables a feature or changes financial data.
        </p>
      </div>

      {loading && <Card padding="default"><p className="text-sm text-secondary" role="status">Checking local readiness…</p></Card>}
      {error && !loading && (
        <Card variant="warning" padding="default">
          <p className="text-sm font-semibold text-primary">Readiness is unavailable</p>
          <p className="mt-1 text-sm text-secondary" role="alert">{error}</p>
          <p className="mt-3 text-sm text-secondary">Refresh the page after the Rules Service is healthy. No configuration was changed.</p>
        </Card>
      )}

      {snapshot && !loading && !error && (
        <>
          <Card padding="default" data-testid="readiness-summary">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="label-sm text-tertiary">Overall local readiness</p>
                <h3 className="headline-sm text-primary mt-1">{overallLabel(snapshot.overall_state)}</h3>
              </div>
              <span className="rounded-full border border-accent-border bg-accent-subtle px-3 py-1 text-xs font-semibold text-accent-primary" data-testid="readiness-overall-state">
                {snapshot.overall_state.replaceAll('_', ' ')}
              </span>
            </div>
            <p className="mt-3 text-xs text-tertiary">Last checked {new Date(snapshot.checked_at).toLocaleString()}</p>
          </Card>

          <div className="mt-4 grid gap-3 md:grid-cols-2" data-testid="readiness-checks">
            {snapshot.checks.map((check) => (
              <ReadinessCard key={check.component} check={check} />
            ))}
          </div>

          <Card padding="default" className="mt-4" data-testid="readiness-boundaries">
            <h3 className="headline-sm text-primary">Disabled capabilities</h3>
            <p className="mt-1 text-sm text-secondary">These boundaries are reported by the server. Browser controls cannot override them.</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {Object.entries(snapshot.prohibited_capabilities).map(([name, state]) => (
                <span key={name} className="rounded-full border border-outline-variant/40 bg-surface-container px-3 py-1.5 text-xs text-secondary">
                  {name.replaceAll('_', ' ')} · {state}
                </span>
              ))}
            </div>
          </Card>

          <p className="mt-4 text-sm text-secondary">
            Need recovery guidance? <Link href="/help" className="font-semibold text-accent-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2">Open Help</Link> for the local activation runbook.
          </p>
        </>
      )}
    </section>
  )
}

function ReadinessCard({ check }: { check: ReadinessComponent }) {
  return (
    <Card padding="compact" className={`border ${STATE_CLASSES[check.state]}`} data-testid={`readiness-${check.component}`}>
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-sm font-semibold text-primary">{LABELS[check.component] ?? check.component}</h3>
        <span className="shrink-0 text-xs font-semibold">{STATE_LABELS[check.state]}</span>
      </div>
      <p className="mt-2 text-xs font-semibold uppercase tracking-[0.08em] text-current">{check.reason_code.replaceAll('_', ' ')}</p>
      <p className="mt-2 text-sm text-secondary">{check.recovery_action}</p>
      {check.version && <p className="mt-2 text-xs text-tertiary">Contract: {check.version}</p>}
    </Card>
  )
}
