/**
 * Cross-page data-refresh bus.
 *
 * After any data mutation (upload, delete batch, delete all data, etc.)
 * the mutating component fires ``fireDataRefresh()``.  Every page that
 * displays accounts, transactions, or dashboard summaries listens via
 * ``useOnDataRefresh(callback)`` and re-fetches its data when the event
 * arrives.  This replaces the ad-hoc ``onImportComplete`` callback
 * pattern that only worked inside the Accounts page.
 *
 * Implementation: a plain CustomEvent on ``window`` — zero dependencies,
 * survives Next.js page transitions, and doesn't need a React context
 * (which would require wrapping every page in yet another provider).
 */

const DATA_REFRESH_EVENT = 'fc:data-refresh'

/** Fire from any component after a successful mutation. */
export function fireDataRefresh(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(DATA_REFRESH_EVENT))
  }
}

/** Subscribe in a useEffect; the returned unsubscribe is safe to call
 *  in the effect's cleanup. */
export function onDataRefresh(handler: () => void): () => void {
  if (typeof window === 'undefined') return () => {}
  window.addEventListener(DATA_REFRESH_EVENT, handler)
  return () => window.removeEventListener(DATA_REFRESH_EVENT, handler)
}
