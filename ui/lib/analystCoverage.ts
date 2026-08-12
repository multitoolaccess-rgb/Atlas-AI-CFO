export function analystCoverageEmptyMessage(requestErrors: number): string {
  return requestErrors > 0
    ? 'Analyst coverage could not be retrieved for one or more holdings. Check the provider connection and server configuration.'
    : 'Finnhub responded successfully, but did not publish analyst consensus for these holdings.'
}
