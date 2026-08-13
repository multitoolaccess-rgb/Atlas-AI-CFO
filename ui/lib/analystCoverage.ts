export interface AnalystCoverageSummary {
  eligible: number
  covered: number
  requestErrors: number
}

function countLabel(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`
}

export function analystCoverageEmptyMessage({
  eligible,
  covered,
  requestErrors,
}: AnalystCoverageSummary): string {
  const eligibleLabel = countLabel(eligible, 'eligible holding')

  if (requestErrors > 0 && covered > 0) {
    return `Analyst coverage is partial. Atlas received consensus for ${covered} of ${eligibleLabel}; ${countLabel(requestErrors, 'holding')} did not return usable analyst data. Review those holdings or retry later.`
  }

  if (requestErrors > 0) {
    return `Analyst coverage could not be retrieved for any of the ${eligibleLabel}. ${countLabel(requestErrors, 'request')} did not return usable analyst data. Review holding symbols or retry later.`
  }

  return 'Finnhub responded successfully, but did not publish analyst consensus for these holdings.'
}
