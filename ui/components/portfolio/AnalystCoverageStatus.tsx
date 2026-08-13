import { analystCoverageEmptyMessage } from '@/lib/analystCoverage'

interface AnalystCoverageStatusProps {
  eligible: number
  covered: number
  requestErrors: number
  excluded: number
  loaded: boolean
  batchError: string | null
}

export default function AnalystCoverageStatus({
  eligible,
  covered,
  requestErrors,
  excluded,
  loaded,
  batchError,
}: AnalystCoverageStatusProps) {
  if (batchError || eligible <= 0) return null

  if (loaded && requestErrors > 0 && covered > 0) {
    return (
      <p
        className="text-sm text-[var(--warning-800)] mt-4 rounded-lg bg-[var(--warning-50)] px-3 py-2"
        role="status"
        aria-live="polite"
        data-testid="analyst-coverage-warning"
      >
        {analystCoverageEmptyMessage({ eligible, covered, requestErrors })}
      </p>
    )
  }

  if (covered !== 0) return null

  if (!loaded) {
    return (
      <p
        className="text-xs text-tertiary mt-3"
        role="status"
        aria-live="polite"
        data-testid="analyst-coverage-loading"
      >
        Loading coverage for {eligible} {eligible === 1 ? 'stock' : 'stocks'}…
      </p>
    )
  }

  return (
    <p
      className="text-xs text-tertiary mt-3"
      role="status"
      aria-live="polite"
      data-testid="analyst-coverage-empty"
    >
      {analystCoverageEmptyMessage({ eligible, covered, requestErrors })}
      {excluded > 0 && ` ${excluded} excluded (no consensus).`}
    </p>
  )
}
