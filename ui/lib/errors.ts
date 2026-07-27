/**
 * Centralized axios error classifier.
 *
 * Phase F2 #2 hard-fix: a Finlynq upstream 4xx now maps to OUR 502 on
 * the BE (see ``services/rules-service/app/routes/dashboard.py``) and
 * the FE no longer shows "Your session expired" for what is a
 * cross-service config drift. This file is the FE's source of truth
 * for the 401 / 502 / 5xx / network mapping; pages import
 * ``classifyError`` here instead of defining their own copy.
 *
 * Why centralize vs. the previous 3 per-page helpers:
 *   - Same friendly message shows up on Overview / Portfolio / Goals
 *     / Settings / Recommendations / Accounts / Activity / Help
 *     rather than 3 diverging wordings.
 *   - ``tests/__tests__/errors.test.ts`` exercises the function in
 *     one place — a future contract change updates one file.
 *   - Adds a ``ClassifiedError`` shape (status + category) so a future
 *     "auto-retry once on 502" hook (Phase 11+) can branch on the
 *     ``category`` field rather than re-deriving it inside the page.
 *
 * Status -> message mapping (Phase F2 #2):
 *   - 401    -> "Your session expired. Click Retry to sign in again."
 *             (local auth failed; the 401 retry interceptor will
 *             re-login transparently on the user-facing call)
 *   - 409    -> upstream detail ("That value is already taken...")
 *   - 502    -> "Downstream service unreachable. Try again in a
 *               moment." -- this is the FIX for the "Session expired"
 *               flash, because Finlynq 4xx now arrives as OUR 502.
 *   - 5xx    -> "The server hit an error. Please try again in a
 *               moment." (our own crash; operator intervention)
 *   - other  -> upstream detail
 *   - no res -> "Can't reach the backend. Start the rules-service on
 *               :8000 (bash scripts/start.sh)."
 */

/** Coarse-grained category for auto-retry / telemetry hooks. */
export type ErrorCategory =
  | 'session-expired'
  | 'downstream-unavailable'
  | 'validation'
  | 'server'
  | 'network'
  | 'unknown'

export interface ClassifiedError {
  /** User-facing message (safe to render in an ErrorBanner). */
  message: string
  /** Coarse-grained bucket — Phase 11+ retry hooks branch on this. */
  category: ErrorCategory
  /** Original axios/Network error, for logging + ref. */
  cause: unknown
}

/**
 * Classify an axios/Network error into a user-friendly shape.
 *
 * Mirrors the previous per-page ``classifyError`` helpers byte-for-byte
 * on the message strings so this drop-in replacement doesn't shift
 * any test assertion; the new wrapper just adds ``category``.
 */
export function classifyError(err: unknown): ClassifiedError {
  if (!err || typeof err !== 'object') {
    return {
      message: 'The server rejected the request.',
      category: 'unknown',
      cause: err,
    }
  }

  // Axios errors carry a ``response`` on HTTP failures and a
  // ``request`` only on transport-layer failures (no response).
  // ``err.response.status`` is the canonical HTTP status to branch on.
  const e = err as {
    response?: { status: number; data?: { detail?: string } }
    request?: unknown
    message?: string
    code?: string
  }

  if (e.response) {
    const status = e.response.status
    const detail = e.response.data?.detail

    if (status === 401) {
      return {
        message:
          'Your session expired. Click Retry to sign in again.',
        category: 'session-expired',
        cause: err,
      }
    }
    if (status === 409) {
      return {
        message:
          detail ?? 'That value is already taken — try a different one.',
        category: 'validation',
        cause: err,
      }
    }
    if (status === 502) {
      // Phase F2 #2 — downstream unavailable. Most common cause is a
      // Finlynq JWT_SECRET drift or a Finlynq outage; the operator's
      // uvicorn logs will pinpoint the real cause. The friendly
      // banner reassures the user the local session is still valid.
      return {
        message:
          'Downstream service is unavailable. Your session is fine — please try again in a moment.',
        category: 'downstream-unavailable',
        cause: err,
      }
    }
    if (status >= 500) {
      return {
        message:
          detail ?? 'The server hit an error. Please try again in a moment.',
        category: 'server',
        cause: err,
      }
    }
    return {
      message: detail ?? e.message ?? 'The server rejected the request.',
      category: 'unknown',
      cause: err,
    }
  }

  // No response object → real network failure (BE down, ECONNREFUSED, offline).
  return {
    message:
      "Can't reach the backend. Make sure the rules-service is running on :8000 (cd services/rules-service && .venv/bin/python -m uvicorn app.main:app).",
    category: 'network',
    cause: err,
  }
}

/**
 * String-only convenience wrapping ``classifyError``. Pages that want
 * just the message (the common case — 9 of 10 call sites) can use
 * this without the destructure.
 */
export function classifyErrorMessage(err: unknown): string {
  return classifyError(err).message
}
