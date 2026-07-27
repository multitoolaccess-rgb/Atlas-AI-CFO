// =============================================================================
// Phase 48 — per-browser UX preference for the /portfolio auto-refresh
// interval. Persisted in localStorage (NOT in the BE users row) because
// the auto-refresh cadence is a single-browser UX concern, not a
// multi-device finance data fact. A user who has /portfolio open in
// Chrome + Safari picks the cadence independently per browser.
//
// The BE has no equivalent setting because the BE's
// ``POST /api/holdings/refresh-prices`` is a stateless on-demand
// RPC — there's no cron / scheduler / background job to configure
// server-side. All cadence lives in the page that runs the timer.
//
// Bound rationale:
//   - ``0`` is a sentinel for "off" (no auto-refresh). The user can
//     disable the loop without removing the UI affordance.
//   - ``5`` is the floor (anything <5 risks a Finnhub 429 storm
//     on the free tier; the 60/min cap means a 1-minute tick
//     against a 30-symbol portfolio refreshes the upstream API
//     30x/minute which is the entire budget).
//   - ``1440`` is the ceiling (24h; the imported ``last_price`` is
//     always available as a graceful fallback if the user wants
//     "essentially never" — values above this are visually
//     indistinguishable from off).
// =============================================================================

/** localStorage key. Scoped to the fc_ namespace used elsewhere
 *  (``fc_session_token`` for the JWT in api.ts). */
const KEY = 'fc_holdings_auto_refresh_minutes'

/** Floor (excluding the 0=off sentinel). */
export const MIN_REFRESH_MINUTES = 5
/** 24h ceiling. */
export const MAX_REFRESH_MINUTES = 1440
/** Default when the localStorage key is missing or invalid. */
export const DEFAULT_REFRESH_MINUTES = 60

/**
 * Clamp a candidate value to the allowed range.
 * ``0`` is preserved as a sentinel for "auto-refresh disabled";
 * any other value below ``MIN_REFRESH_MINUTES`` is clamped up to
 * ``MIN_REFRESH_MINUTES`` (fat-finger protection).
 */
export function clampAutoRefreshMinutes(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_REFRESH_MINUTES
  if (value === 0) return 0
  if (value < MIN_REFRESH_MINUTES) return MIN_REFRESH_MINUTES
  if (value > MAX_REFRESH_MINUTES) return MAX_REFRESH_MINUTES
  return Math.floor(value)
}

/** Read the current preference. Returns the default when:
 *  - the localStorage key is unset (fresh user),
 *  - the stored value is non-numeric (corrupted),
 *  - the value is outside the clamp bounds (clamped in place).
 *
 *  SSR-safe: returns the default when ``window`` is undefined so
 *  Next.js server-rendering never reads localStorage.
 */
export function getAutoRefreshMinutes(): number {
  if (typeof window === 'undefined') return DEFAULT_REFRESH_MINUTES
  const raw = window.localStorage.getItem(KEY)
  if (raw === null) return DEFAULT_REFRESH_MINUTES
  const parsed = Number(raw)
  if (!Number.isFinite(parsed)) return DEFAULT_REFRESH_MINUTES
  return clampAutoRefreshMinutes(parsed)
}

/**
 * Persist a new preference. Always writes the CLAMPED value so
 * the read path never sees an out-of-bounds value. Returns the
 * clamped value so the caller can sync its React state to the
 * same value the storage just stored (avoids a UI/storage drift
 * when the user types 1 and we silently store 5).
 */
export function setAutoRefreshMinutes(minutes: number): number {
  const clamped = clampAutoRefreshMinutes(minutes)
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(KEY, String(clamped))
  }
  return clamped
}
