'use client'

import { RotateCcw, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'
import { Button, Input } from '@/components/ui'
import type { ScenarioInput } from '@/lib/api_scenarios'

interface ScenarioBuilderProps {
  disabled?: boolean
  mutating?: boolean
  serverError?: string | null
  onGenerate: (input: ScenarioInput) => void
}

const DECIMAL_RE = /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/

function validateInput(input: ScenarioInput): string | null {
  if (!input.monthly_contribution_delta && !input.contribution_start_date && !input.contribution_stop_date && !input.one_time_outflow) return 'Enter at least one supported change.'
  if (input.monthly_contribution_delta && !DECIMAL_RE.test(input.monthly_contribution_delta)) return 'Monthly contribution change must be a canonical decimal string.'
  if (input.one_time_outflow && (!input.one_time_outflow.date || !input.one_time_outflow.amount)) return 'Enter both a date and amount for the one-time outflow.'
  if (input.one_time_outflow && (!DECIMAL_RE.test(input.one_time_outflow.amount) || input.one_time_outflow.amount.startsWith('-') || input.one_time_outflow.amount === '0')) return 'One-time outflow must be a positive canonical decimal string.'
  if (input.contribution_start_date && input.contribution_stop_date && input.contribution_start_date > input.contribution_stop_date) return 'Contribution start date cannot be after the stop date.'
  return null
}

export default function ScenarioBuilder({ disabled = false, mutating = false, serverError, onGenerate }: ScenarioBuilderProps) {
  const [delta, setDelta] = useState('')
  const [startDate, setStartDate] = useState('')
  const [stopDate, setStopDate] = useState('')
  const [outflowDate, setOutflowDate] = useState('')
  const [outflowAmount, setOutflowAmount] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)

  const input: ScenarioInput = {
    ...(delta.trim() ? { monthly_contribution_delta: delta.trim() } : {}),
    ...(startDate ? { contribution_start_date: startDate } : {}),
    ...(stopDate ? { contribution_stop_date: stopDate } : {}),
    ...(outflowDate || outflowAmount ? { one_time_outflow: { date: outflowDate, amount: outflowAmount } } : {}),
  }

  const reset = () => {
    setDelta(''); setStartDate(''); setStopDate(''); setOutflowDate(''); setOutflowAmount(''); setValidationError(null)
  }

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const error = validateInput(input)
    setValidationError(error)
    if (!error) onGenerate(input)
  }

  return (
    <form onSubmit={submit} className="card p-5" aria-labelledby="scenario-builder-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><div className="flex items-center gap-2"><SlidersHorizontal className="h-5 w-5 text-primary-600" aria-hidden="true" /><h2 id="scenario-builder-heading" className="headline-sm text-primary">Build one bounded change</h2></div><p className="mt-2 max-w-2xl text-sm leading-6 text-secondary">The server accepts a monthly contribution delta, optional dated start and stop, and one dated outflow. Leave unsupported life events and assumptions out of this model.</p></div>
        <Button type="button" variant="tertiary" size="sm" onClick={reset} disabled={mutating} icon={<RotateCcw className="h-4 w-4" aria-hidden="true" />}>Reset</Button>
      </div>
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <Input id="scenario-monthly-delta" label="Monthly contribution change" value={delta} onChange={(event) => setDelta(event.target.value)} placeholder="e.g. 250.00 or -100.00" hint="A Decimal string; the server keeps the baseline contribution outside any dated window." inputMode="decimal" />
        <div className="grid gap-4 sm:grid-cols-2"><Input id="scenario-start-date" label="Change starts" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /><Input id="scenario-stop-date" label="Change stops" type="date" value={stopDate} onChange={(event) => setStopDate(event.target.value)} /></div>
        <Input id="scenario-outflow-date" label="One-time outflow date" type="date" value={outflowDate} onChange={(event) => setOutflowDate(event.target.value)} />
        <Input id="scenario-outflow-amount" label="One-time outflow amount" value={outflowAmount} onChange={(event) => setOutflowAmount(event.target.value)} placeholder="e.g. 1000.00" hint="Positive Decimal string; fails closed if liquidity is insufficient." inputMode="decimal" />
      </div>
      <div className="mt-5 rounded-lg border border-outline-variant bg-surface-container p-4"><p className="text-xs font-semibold uppercase tracking-wide text-tertiary">Before you submit</p><p className="mt-1 text-sm text-secondary">{delta || startDate || stopDate || outflowDate || outflowAmount ? 'Atlas will send only the supported fields above and show the returned server result.' : 'Add a contribution change or one-time outflow to preview the request summary.'}</p></div>
      {(validationError || serverError) && <p className="mt-4 text-sm text-danger" role="alert">{validationError ?? serverError}</p>}
      <div className="mt-5 flex flex-wrap items-center gap-3"><Button type="submit" variant="primary" disabled={disabled || mutating}>{mutating ? 'Requesting server result…' : 'Generate scenario'}</Button><span className="text-xs text-tertiary">No browser projection, probability, tax, optimization, or execution is performed.</span></div>
    </form>
  )
}
