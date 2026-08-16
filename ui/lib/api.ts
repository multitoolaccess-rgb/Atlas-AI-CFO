import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios';

// ---- Local-first auth helper -------------------------------------------
// The rules-service issues a JWT for `settings.local_user` via
// `POST /api/auth/devlogin`. The token is stored in localStorage so the
// UI survives a Next.js dev-server restart; the service's
// `app.auth.require_user` dependency validates it via the `sub` claim.

const TOKEN_KEY = 'fc_session_token'
const WARM_KEY = 'fc_bootstrap_warm_at'
/** A previously-completed bootstrap counts as "still warm" for this
 *  many minutes. After the window passes we re-show the splash so a
 *  stale JWT (server secret rotation, browser cleared cookies) still
 *  surfaces visibly. 60 minutes was chosen empirically: long enough
 *  for a normal coding session to span many reloads without flicker,
 *  short enough that a stale token is likely to fail and re-warm. */
export const WARM_WINDOW_MS = 60 * 60 * 1000

export function getStoredToken(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(TOKEN_KEY)
}

export function setStoredToken(token: string): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(TOKEN_KEY, token)
}

export function clearStoredToken(): void {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(TOKEN_KEY)
}

/** Mark the bootstrap as completed-or-skipped recently so subsequent
 *  loads can skip the splash. The stored value is the WALL CLOCK
 *  timestamp (ms) of the warm event; consumers compare against
 *  ``Date.now()`` to decide if the warm flag is still within the
 *  WARM_WINDOW_MS window. */
export function markBootstrapWarm(): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(WARM_KEY, String(Date.now()))
}

/** Returns true iff the warm flag exists AND the recorded warm
 *  timestamp is within WARM_WINDOW_MS of now. Used by
 *  AuthBootstrapProvider to skip the splash on warm reloads. */
export function isBootstrapWarm(): boolean {
  if (typeof window === 'undefined') return false
  const raw = window.localStorage.getItem(WARM_KEY)
  if (!raw) return false
  const ts = Number(raw)
  if (!Number.isFinite(ts)) return false
  return Date.now() - ts < WARM_WINDOW_MS
}

/** Clear the warm flag. Called by the "Clear session & reload"
 *  recovery button together with ``clearStoredToken`` so the next
 *  load re-shows the splash from scratch. */
export function clearBootstrapWarm(): void {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(WARM_KEY)
}

// ---- 401 auto-recovery factory -----------------------------------------
// If the server returns 401 (e.g. settings.jwt_secret rotated mid-
// session, or browser cleared the cookie somehow), the stored token
// is stale. We catch 401 once, drop the token, re-login, and retry
// the failed call. The second 401 (genuine failure) bubbles up.
//
// The factory form lets tests build a custom instance with a mock
// loginFn (no module-level spyOn dance) and removes the circular
// dep that the previous implementation had between `api` and
// `rulesService` at module load time.

/**
 * Auth routes that MUST NOT trigger the 401 retry path — listing them
 * explicitly (instead of a `/api/auth/` prefix) so a future route in
 * that namespace can opt in to retry by NOT being listed here.
 */
const NON_RETRYABLE_AUTH_ROUTES: readonly string[] = [
  '/api/auth/devlogin',
  '/api/auth/logout',
]

function isAuthRoute(url: string | undefined): boolean {
  if (!url) return false
  return NON_RETRYABLE_AUTH_ROUTES.some((path) => url.includes(path))
}

export interface AuthRetryDeps {
  /** Reads the current bearer token (defaults to `getStoredToken`). */
  readToken?: () => string | null
  /** Re-authenticates and persists the new token. */
  loginFn: () => Promise<{ token: string; subject: string }>
  /** Called when a 401 forces a token clear (e.g. for telemetry). */
  onTokenClear?: () => void
  /** Called after a successful re-login (e.g. for telemetry). */
  onTokenRefresh?: (token: string) => void
}

export interface AuthRetryOptions {
  baseURL: string
  deps: AuthRetryDeps
  /** Shared client name used for logging only. */
  clientName?: string
}

export function createApiWithAuthRetry(options: AuthRetryOptions): AxiosInstance {
  const { baseURL, deps, clientName = 'cashflix' } = options
  const readToken = deps.readToken ?? getStoredToken
  const inflightLogin: { current: Promise<{ token: string; subject: string }> | null } = {
    current: null,
  }

  const client = axios.create({
    baseURL,
    headers: { 'Content-Type': 'application/json' },
    withCredentials: true,
  })

  client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = readToken()
    if (token) {
      // Axios v1 wraps headers in AxiosHeaders; `.set()` writes to the
      // normalized map (direct `.Authorization =` assignments no-op).
      config.headers.set('Authorization', `Bearer ${token}`)
    }
    return config
  })

  client.interceptors.response.use(
    (response) => response,
    async (error: unknown) => {
      const err = error as {
        response?: { status: number; data: unknown }
        config?: {
          url?: string
          method?: string
          _retried?: boolean
          headers?: { set?: (k: string, v: string) => void }
        }
        request?: unknown
        message?: string
      }
      if (err.response) {
        const url = err.config?.url ?? ''
        const responseData = err.response.data as { code?: unknown; reason_code?: unknown } | null
        const responseCode = typeof responseData?.code === 'string'
          ? responseData.code
          : typeof responseData?.reason_code === 'string'
            ? responseData.reason_code
            : null
        const isKnownRecoveryRoute = (
          url.includes('/api/v1/market-briefs') ||
          url.includes('/api/v1/goals/') && url.includes('/scenarios') ||
          url.includes('/api/v1/goals/') && url.includes('/decision-history') ||
          url.includes('/api/v1/scenarios') ||
          url.includes('/api/v1/forecasts') ||
          url.includes('/api/v1/recommendations') ||
          url.includes('/api/v1/decision-history') ||
          url.includes('/api/system/readiness')
        )
        // Dashboard 502 is an intentional, classified downstream-recovery
        // state rendered by Mission Control. Keep it observable as a bounded
        // info diagnostic without treating it as an unexpected browser error;
        // other 5xx responses remain errors.
        const isDashboardDownstreamRecovery = url.includes('/api/dashboard/summary') && err.response.status === 502
        const isHandledRecovery = (
          (isKnownRecoveryRoute && [401, 404, 409, 412, 422, 503].includes(err.response.status)) ||
          isDashboardDownstreamRecovery
        )
        if (typeof window !== 'undefined' && isHandledRecovery) {
          // Recovery responses are rendered as explicit UI states by the
          // owning route. Keep diagnostics bounded: response bodies can
          // contain provider details, financial values, or credentials.
          // eslint-disable-next-line no-console
          console.info(`[${clientName}] handled response`, responseCode ?? 'unknown', err.response.status)
        } else if (typeof window !== 'undefined') {
          // Unexpected server failures remain observable, but never log the
          // raw response body or request object into the browser console.
          // eslint-disable-next-line no-console
          console.error(`[${clientName}] unexpected API response`, err.response.status, responseCode ?? 'unknown')
        }
        if (
          err.response.status === 401 &&
          !err.config?._retried &&
          // CRITICAL: never retry the auth routes themselves. If
          // /devlogin returns 401, the interceptor would otherwise
          // call deps.loginFn() (= devLogin) to refresh the token,
          // but that fresh request also passes through this
          // interceptor. With inflightLogin.current still pointing
          // at it, the second request does `await inflightLogin.current`
          // — deadlocking on itself, freezing the splash, and
          // preventing the user from ever reaching the error UI. The
          // same trap applies to /logout (it's documented to
          // invalidate the token on the next request anyway, so
          // retrying it just succeeds once then breaks).
          //
          // Explicit allowlist rather than a `/api/auth/` prefix so
          // a future `/api/auth/refresh` (which DOES need 401 retry)
          // doesn't silently get skipped.
          !isAuthRoute(err.config?.url) &&
          typeof window !== 'undefined'
        ) {
          try {
            if (!inflightLogin.current) {
              clearStoredToken()
              deps.onTokenClear?.()
              inflightLogin.current = deps.loginFn().finally(() => {
                inflightLogin.current = null
              })
            }
            await inflightLogin.current
            const newToken = readToken()
            if (newToken) deps.onTokenRefresh?.(newToken)
            if (!err.config?.headers?.set) return Promise.reject(error)
            err.config._retried = true // second 401 falls through to original reject
            if (newToken) {
              err.config.headers.set('Authorization', `Bearer ${newToken}`)
            }
            return client.request(err.config as InternalAxiosRequestConfig)
          } catch {
            // eslint-disable-next-line no-console
            console.warn(`[${clientName}] re-login refused; staying logged out`)
          }
        }
      } else if (err.request) {
        // eslint-disable-next-line no-console
        console.error(`[${clientName}] request failed without response`)
      } else {
        // eslint-disable-next-line no-console
        console.error(`[${clientName}] request setup failed`)
      }
      return Promise.reject(error)
    },
  )

  return client
}

// ---- Type shapes (mirrors app/schemas/__init__.py) ---------------------
/** Phase 9 — analyst-ratings response shapes. Shared between
 *  ``getAnalystRatings`` (single-ticker) and ``getBatchAnalystRatings``
 *  (per-row batch wrapper) so the two endpoints can never silently
 *  drift apart. The previous inline-typed ``data?: unknown`` on the
 *  batch accumulator paired against a detailed Promise return type
 *  tripped TSC at line ~1262 with TS2322; extracting ``AnalystRatingsData``
 *  kills that whole class of bug. */
export interface AnalystRatingsPeriod {
  period: string
  strongBuy: number
  buy: number
  hold: number
  sell: number
  strongSell: number
}

export interface AnalystRatingsPriceTarget {
  targetMean: number
  targetMedian: number
  targetHigh: number
  targetLow: number
}

export interface AnalystRatingsData {
  symbol: string
  recommendation_trends: AnalystRatingsPeriod[]
  /** ``null`` when Finnhub returned no price-target row (newly listed,
   *  OTC, etc.) — the FE renders the "No price target consensus"
   *  empty card on this signal. */
  price_target: AnalystRatingsPriceTarget | null
}

// Phase 52+ — account-type classification sets. Mirrors the backend's
// canonical `app/account_types.py` constants so the FE's income/expense
// computation (Activity page summary strip) stays in lockstep with the
// dashboard backend. When a new type is added to the BE, update these
// sets as well.

/** Account types where a positive transaction amount is NOT income
 *  (payments/credits to a credit card, loan, or mortgage are balance
 *  transfers, not earnings). */
export const CREDIT_ACCOUNT_TYPES = new Set([
  'credit_card',
  'loan',
  'mortgage',
])

/** Account types where money movement is capital flow (not simple
 *  P&L). Excluded from both income and expense totals — these
 *  appear in the Portfolio section instead. */
export const INVESTMENT_ACCOUNT_TYPES = new Set([
  'investment',
  'hsa',
  '529',
  '401k',
  'ira',
  'crypto',
])

// ---- Phase 52+ — cashflow classification ------------------------------------
// Every account type has distinct financial semantics. A credit-card purchase
// IS an expense, a savings transfer IS a balance move, and a 401(k) contribution
// IS savings — not spending. This module classifies every transaction into a
// deterministic FinancialEffect + CashflowRole pair using account-type-aware
// rules and description-based keyword detection.

/** Granular financial effect of a transaction. Mirrors the spec's 14-value
 *  enum covering all account types. */
export type FinancialEffect =
  | 'income'
  | 'expense'
  | 'transfer'
  | 'expense_reversal'
  | 'income_reversal'
  | 'fee'
  | 'interest'
  | 'investment_buy'
  | 'investment_sell'
  | 'contribution'
  | 'withdrawal'
  | 'principal_payment'
  | 'ignored'
  | 'needs_review'

/** High-level cashflow bucket for the Sankey/dashboard flow model.
 *  Each account type's transactions map to one of these roles. */
export type CashflowRole =
  | 'spend'   // expenses, fees, purchases
  | 'earn'    // income, dividends, interest, staking rewards
  | 'save'    // contributions, principal payments
  | 'invest'  // investment buys/sells
  | 'debt'    // debt service (interest/fees on loans)
  | 'transfer' // internal money movement

/** Cashflow classification for a single transaction. */
export interface CashflowClassification {
  /** Granular effect — the most specific classification. */
  effect: FinancialEffect
  /** High-level bucket for Sankey/dashboard rolls. */
  role: CashflowRole
  /** How much this transaction contributes to income (deposits, dividends). */
  incomeEffect: number
  /** How much this transaction contributes to expenses (purchases, fees).
   *  Refunds set this negative to reduce the expense total. */
  expenseEffect: number
  /** How much of this transaction is a balance transfer (excluded from P&L). */
  transferEffect: number
  /** DEPRECATED — kept for backward compat. Use `effect` instead. */
  bucket: 'income' | 'expense' | 'transfer' | 'reversal' | 'ignored'
  /** When true, the transaction needs manual review ("other" account type). */
  needsReview: boolean
  /** Human-readable reason when needsReview is true. */
  reviewReason?: string
}

// ---- Keyword pattern sets (ordered by priority within each group) --------
// These patterns are tested in priority order within each account-type
// switch branch. The FIRST match wins. Patterns use word-boundary regex
// to avoid "REPAYMENT" matching "PAYMENT".

/** Bill-pay phrases — internal transfers, not income or expense. */
const _PAYMENT_PATTERNS: RegExp[] = [
  /\bONLINE\s*PAYMENT\b/i, /\bMOBILE\s*PAYMENT\b/i,
  /\bAUTOMATIC\s*PAYMENT\b/i, /\bELECTRONIC\s*PAYMENT\b/i,
  /\bPAYMENT\s+THANK\s+YOU\b/i, /\bPAYMENT\s+RECEIVED\b/i,
  /\bAUTOPAY\b/i, /\bSCHEDULED\s*PAYMENT\b/i,
  /\bBILL\s*PAY\b/i, /\bPAYMENT\s+FROM\b/i,
]

/** Refund / return / reversal phrases — reduce expenses. */
const _REFUND_PATTERNS: RegExp[] = [
  /\bREFUND\b/i, /\bRETURN\b/i, /\bREVERSAL\b/i,
  /\bCASHBACK\b/i, /\bSTATEMENT\s*CREDIT\b/i,
  /\bCREDIT\s*ADJUSTMENT\b/i, /\bREWARD\s*REDEMPTION\b/i,
]

/** Income patterns — payroll, salary, direct deposit, dividends, interest. */
const _INCOME_PATTERNS: RegExp[] = [
  /\bPAYROLL\b/i, /\bDIRECT\s*DEPOSIT\b/i, /\bSALARY\b/i,
  /\bDIVIDEND\b/i, /\bCAPITAL\s*GAIN/i,
]

/** Interest-earned patterns (savings account interest, not credit card interest). */
const _INTEREST_EARNED_PATTERNS: RegExp[] = [
  /\bINTEREST\s*(?:EARNED|PAID|CREDIT)\b/i,
  /\bDIVIDEND\s*(?:EARNED|PAID|CREDIT)\b/i,
  /\bAPY\b/i, /\bANNUAL\s*PERCENTAGE\s*YIELD\b/i,
]

/** Fee / charge patterns (bank fees, late fees, overdraft, trading fees). */
const _FEE_PATTERNS: RegExp[] = [
  /\b(?:MONTHLY|SERVICE|MAINTENANCE|ANNUAL|LATE|OVERDRAFT|ATM|WIRE|TRANSACTION)\s*FEE\b/i,
  /\bFEE\b/i, /\bCHARGE\b/i, /\bNETWORK\s*FEE\b/i,
  /\bINTEREST\s*CHARGE\b/i, /\bFINANCE\s*CHARGE\b/i,
]

/** Contribution patterns (401k, IRA, HSA, 529 contributions). */
const _CONTRIBUTION_PATTERNS: RegExp[] = [
  /\bCONTRIBUTION\b/i, /\bCONTRIB\b/i,
  /\bEMPLOYEE\s*(?:CONTRIB|DEFERRAL)\b/i,
]

/** Employer match patterns. */
const _MATCH_PATTERNS: RegExp[] = [
  /\b(?:EMPLOYER|COMPANY)\s*(?:MATCH|CONTRIB)\b/i,
  /\bMATCH\b/i,
]

/** Rollover patterns (IRA/401k). */
const _ROLLOVER_PATTERNS: RegExp[] = [
  /\bROLLOVER\b/i, /\bDIRECT\s*ROLLOVER\b/i,
  /\bTRUSTEE[\s-]*TO[\s-]*TRUSTEE\b/i,
]

/** Staking / crypto reward patterns. */
const _STAKING_PATTERNS: RegExp[] = [
  /\bSTAKING\b/i, /\bSTAKE\s*REWARD/i, /\bREWARD\b/i,
  /\bAIRDROP\b/i, /\bYIELD\s*FARM/i,
]

/** Trade buy patterns — investment/crypto purchases. */
const _TRADE_BUY_PATTERNS: RegExp[] = [
  /\b(?:BUY|PURCHASE|BOUGHT|YOU\s*BOUGHT)\b/i,
  /\bTRADE\s*DATE.*BUY\b/i, /\bBUY\s*(?:ORDER|TRADE)\b/i,
]

/** Trade sell patterns — investment/crypto sales. */
const _TRADE_SELL_PATTERNS: RegExp[] = [
  /\b(?:SELL|SOLD|YOU\s*SOLD)\b/i,
  /\bTRADE\s*DATE.*SELL\b/i, /\bSELL\s*(?:ORDER|TRADE)\b/i,
]

/** Escrow patterns (mortgage-specific: escrow, property tax, insurance). */
const _ESCROW_PATTERNS: RegExp[] = [
  /\bESCROW\b/i, /\bPROPERTY\s*TAX\b/i,
  /\bHAZARD\s*INSURANCE\b/i, /\bPMI\b/i,
]

/** Principal payment patterns (loan/mortgage). */
const _PRINCIPAL_PATTERNS: RegExp[] = [
  /\bPRINCIPAL\b/i, /\bPRINCIPAL\s*PAYMENT\b/i,
  /\bPRINCIPAL\s*REDUCTION\b/i,
]

/** Internal transfer patterns — money moving between owned accounts.
 *  NOTE: "ACH debit" and "ACH credit" are deliberately EXCLUDED — they
 *  often represent external bill payments (expenses) and deposits (income),
 *  not internal transfers. "ACH transfer" is specific enough for internal moves. */
const _TRANSFER_PATTERNS: RegExp[] = [
  /\b(?:SCHEDULED|ONLINE|AUTOMATIC|RECURRING|INTERNAL)\s*TRANSFER\b/i,
  /\bTRANSFER\s+(?:FROM|TO)\b/i,
  /\bWIRE\s*(?:TRANSFER|OUT|IN)\b/i,
  /\bACH\s*TRANSFER\b/i,
]

/** Medical / healthcare spend patterns (HSA-specific). */
const _MEDICAL_PATTERNS: RegExp[] = [
  /\b(?:MEDICAL|PHARMACY|HOSPITAL|DOCTOR|DENTAL|VISION|OPTICAL|CLINIC|HEALTH)\b/i,
  /\b(?:COPAY|CO[\s-]PAY|DEDUCTIBLE)\b/i,
  /\bPRESCRIPTION\b/i, /\bRX\b/i,
]

/** Distribution / withdrawal patterns (IRA, 401k). */
const _WITHDRAWAL_PATTERNS: RegExp[] = [
  /\b(?:DISTRIBUTION|WITHDRAWAL|DISBURSEMENT)\b/i,
  /\bRMD\b/i, /\bREQUIRED\s*MINIMUM\b/i,
]

/** Helper: test any pattern in a list against description text. */
function _matchAny(desc: string, patterns: RegExp[]): boolean {
  return patterns.some((re) => re.test(desc))
}

/** Helper: build a classification result with consistent effect computations. */
function _result(
  absAmt: number,
  effect: FinancialEffect,
  role: CashflowRole,
  needsReview: boolean = false,
  reason?: string,
): CashflowClassification {
  let income = 0, expense = 0, transfer = 0
  let bucket: CashflowClassification['bucket'] = 'ignored'

  switch (effect) {
    case 'income':
    case 'interest':
      income = absAmt; bucket = 'income'; break
    case 'expense':
    case 'fee':
      expense = absAmt; bucket = 'expense'; break
    case 'expense_reversal':
      expense = -absAmt; bucket = 'reversal'; break
    case 'income_reversal':
      income = -absAmt; bucket = 'reversal'; break
    case 'transfer':
    case 'contribution':
    case 'withdrawal':
    case 'investment_buy':
    case 'investment_sell':
    case 'principal_payment':
    case 'ignored':
      transfer = absAmt; bucket = 'transfer'; break
    case 'needs_review':
      transfer = absAmt; bucket = 'ignored'; break
  }

  return {
    effect, role,
    incomeEffect: income,
    expenseEffect: expense,
    transferEffect: transfer,
    bucket,
    needsReview,
    reviewReason: reason,
  }
}

/**
 * Classify a transaction into its financial effect + cashflow role.
 *
 * Uses account-type-aware rules with description-based keyword detection.
 * The FIRST matching pattern in each branch wins — order matters.
 *
 * This is a PURE function (no DB reads, no side effects) so it works
 * identically in the frontend (Activity page) and backend (dashboard
 * aggregation). The backend mirrors this logic in `account_types.py`.
 */
export function classifyCashflow(txn: {
  amount: number
  account_type?: string | null
  description?: string | null
}): CashflowClassification {
  const at = (txn.account_type ?? '').trim().toLowerCase()
  const desc = (txn.description ?? '').trim()
  const absAmt = Math.abs(txn.amount)
  const isPos = txn.amount > 0
  const isNeg = txn.amount < 0

  // ---- CREDIT CARD ----
  // Liability ledger. A charge increases what you owe (expense); a payment
  // reduces what you owe (transfer, not income); a refund reverses a charge.
  if (at === 'credit_card') {
    if (_matchAny(desc, _PAYMENT_PATTERNS))
      return _result(absAmt, 'transfer', 'transfer')
    if (_matchAny(desc, _REFUND_PATTERNS))
      return _result(absAmt, 'expense_reversal', 'earn')
    if (_matchAny(desc, _FEE_PATTERNS))
      return _result(absAmt, 'fee', 'spend')
    // Default: charge → expense (use absAmt because banks report signs differently)
    return _result(absAmt, 'expense', 'spend')
  }

  // ---- LOAN ----
  // Liability. Disbursements are transfers; payments split principal/interest.
  if (at === 'loan') {
    if (_matchAny(desc, _PRINCIPAL_PATTERNS))
      return _result(absAmt, 'principal_payment', 'debt')
    if (_matchAny(desc, _FEE_PATTERNS) || _matchAny(desc, _INTEREST_EARNED_PATTERNS))
      return _result(absAmt, 'fee', 'spend')
    if (_matchAny(desc, _PAYMENT_PATTERNS))
      return _result(absAmt, 'transfer', 'transfer')
    // Loan disbursement (positive) or blind P&I payment (negative)
    if (isPos) return _result(absAmt, 'transfer', 'transfer')
    return _result(absAmt, 'principal_payment', 'debt')
  }

  // ---- MORTGAGE ----
  // Similar to loan but with escrow awareness.
  if (at === 'mortgage') {
    if (_matchAny(desc, _ESCROW_PATTERNS))
      return _result(absAmt, 'transfer', 'save')
    if (_matchAny(desc, _PRINCIPAL_PATTERNS))
      return _result(absAmt, 'principal_payment', 'debt')
    if (_matchAny(desc, _FEE_PATTERNS) || _matchAny(desc, _INTEREST_EARNED_PATTERNS))
      return _result(absAmt, 'fee', 'spend')
    if (_matchAny(desc, _PAYMENT_PATTERNS))
      return _result(absAmt, 'transfer', 'transfer')
    // Blind P&I payment — treat as principal (debt reduction)
    if (isPos) return _result(absAmt, 'transfer', 'transfer')
    return _result(absAmt, 'principal_payment', 'debt')
  }

  // ---- INVESTMENT ----
  // Capital asset. Buys/sells are investment activity; dividends are income;
  // funding/withdrawal are transfers.
  if (at === 'investment') {
    if (_matchAny(desc, _TRADE_BUY_PATTERNS))
      return _result(absAmt, 'investment_buy', 'invest')
    if (_matchAny(desc, _TRADE_SELL_PATTERNS))
      return _result(absAmt, 'investment_sell', 'invest')
    if (_matchAny(desc, [/\bDIVIDEND\b|\bDIV\b/i]) || _matchAny(desc, _INTEREST_EARNED_PATTERNS))
      return _result(absAmt, 'income', 'earn')
    if (_matchAny(desc, _FEE_PATTERNS))
      return _result(absAmt, 'fee', 'spend')
    // Funding/withdrawal → transfer
    return _result(absAmt, 'transfer', 'transfer')
  }

  // ---- CRYPTO ----
  // Volatile investment asset. Trades are investment activity; staking is
  // income; wallet transfers are transfers.
  if (at === 'crypto') {
    if (_matchAny(desc, _TRADE_BUY_PATTERNS))
      return _result(absAmt, 'investment_buy', 'invest')
    if (_matchAny(desc, _TRADE_SELL_PATTERNS))
      return _result(absAmt, 'investment_sell', 'invest')
    if (_matchAny(desc, _STAKING_PATTERNS))
      return _result(absAmt, 'income', 'earn')
    if (_matchAny(desc, _FEE_PATTERNS))
      return _result(absAmt, 'fee', 'spend')
    // Wallet transfer / funding
    return _result(absAmt, 'transfer', 'transfer')
  }

  // ---- 401(k) ----
  // Retirement investment. Contributions are savings; trades are investment;
  // employer match is special; rollovers are transfers.
  if (at === '401k') {
    if (_matchAny(desc, _ROLLOVER_PATTERNS))
      return _result(absAmt, 'transfer', 'transfer')
    if (_matchAny(desc, _MATCH_PATTERNS))
      return _result(absAmt, 'contribution', 'save')
    if (_matchAny(desc, _CONTRIBUTION_PATTERNS))
      return _result(absAmt, 'contribution', 'save')
    if (_matchAny(desc, _TRADE_BUY_PATTERNS))
      return _result(absAmt, 'investment_buy', 'invest')
    if (_matchAny(desc, _TRADE_SELL_PATTERNS))
      return _result(absAmt, 'investment_sell', 'invest')
    if (_matchAny(desc, [/\bDIVIDEND\b|\bDIV\b/i]) || _matchAny(desc, _INTEREST_EARNED_PATTERNS))
      return _result(absAmt, 'income', 'earn')
    if (_matchAny(desc, _FEE_PATTERNS))
      return _result(absAmt, 'fee', 'spend')
    // Payroll contribution (positive = money arriving in 401k) or loan repayment
    if (isPos) return _result(absAmt, 'contribution', 'save')
    return _result(absAmt, 'ignored', 'invest')
  }

  // ---- IRA ----
  // Retirement investment. Similar to 401k but simpler source types.
  if (at === 'ira') {
    if (_matchAny(desc, _ROLLOVER_PATTERNS))
      return _result(absAmt, 'transfer', 'transfer')
    if (_matchAny(desc, _CONTRIBUTION_PATTERNS))
      return _result(absAmt, 'contribution', 'save')
    if (_matchAny(desc, _WITHDRAWAL_PATTERNS))
      return _result(absAmt, 'withdrawal', 'transfer')
    if (_matchAny(desc, _TRADE_BUY_PATTERNS))
      return _result(absAmt, 'investment_buy', 'invest')
    if (_matchAny(desc, _TRADE_SELL_PATTERNS))
      return _result(absAmt, 'investment_sell', 'invest')
    if (_matchAny(desc, [/\bDIVIDEND\b|\bDIV\b/i]) || _matchAny(desc, _INTEREST_EARNED_PATTERNS))
      return _result(absAmt, 'income', 'earn')
    if (_matchAny(desc, _FEE_PATTERNS))
      return _result(absAmt, 'fee', 'spend')
    if (isPos) return _result(absAmt, 'contribution', 'save')
    return _result(absAmt, 'ignored', 'invest')
  }

  // ---- HSA ----
  // Tax-advantaged health account. Contributions are savings; medical payments
  // are expenses; investment activity is investment.
  if (at === 'hsa') {
    if (_matchAny(desc, _CONTRIBUTION_PATTERNS) || _matchAny(desc, _MATCH_PATTERNS))
      return _result(absAmt, 'contribution', 'save')
    if (_matchAny(desc, _TRADE_BUY_PATTERNS))
      return _result(absAmt, 'investment_buy', 'invest')
    if (_matchAny(desc, _TRADE_SELL_PATTERNS))
      return _result(absAmt, 'investment_sell', 'invest')
    if (_matchAny(desc, _INTEREST_EARNED_PATTERNS))
      return _result(absAmt, 'income', 'earn')
    if (_matchAny(desc, _FEE_PATTERNS))
      return _result(absAmt, 'fee', 'spend')
    if (_matchAny(desc, _MEDICAL_PATTERNS))
      return _result(absAmt, 'expense', 'spend')
    // HSA debit for medical (negative) or contribution (positive)
    if (isPos) return _result(absAmt, 'contribution', 'save')
    return _result(absAmt, 'expense', 'spend')
  }

  // ---- 529 ----
  // Education investment. Contributions are savings; qualified withdrawals
  // are goal spending.
  if (at === '529') {
    if (_matchAny(desc, _CONTRIBUTION_PATTERNS))
      return _result(absAmt, 'contribution', 'save')
    if (_matchAny(desc, _WITHDRAWAL_PATTERNS))
      return _result(absAmt, 'withdrawal', 'transfer')
    if (_matchAny(desc, _TRADE_BUY_PATTERNS))
      return _result(absAmt, 'investment_buy', 'invest')
    if (_matchAny(desc, _TRADE_SELL_PATTERNS))
      return _result(absAmt, 'investment_sell', 'invest')
    if (_matchAny(desc, _FEE_PATTERNS))
      return _result(absAmt, 'fee', 'spend')
    if (isPos) return _result(absAmt, 'contribution', 'save')
    return _result(absAmt, 'ignored', 'invest')
  }

  // ---- CHECKING ----
  // Cash asset. Payroll/deposit = income; purchases/ACH = expense;
  // transfers to other accounts = transfer; fees = fee.
  if (at === 'checking') {
    if (isPos && _matchAny(desc, _INCOME_PATTERNS))
      return _result(absAmt, 'income', 'earn')
    if (isPos && _matchAny(desc, _INTEREST_EARNED_PATTERNS))
      return _result(absAmt, 'interest', 'earn')
    if (isNeg && _matchAny(desc, _FEE_PATTERNS))
      return _result(absAmt, 'fee', 'spend')
    if (_matchAny(desc, _TRANSFER_PATTERNS))
      return _result(absAmt, 'transfer', 'transfer')
    if (_matchAny(desc, _REFUND_PATTERNS))
      return _result(absAmt, 'expense_reversal', 'earn')
    // Standard sign-based fallback
    if (isPos) return _result(absAmt, 'income', 'earn')
    return _result(absAmt, 'expense', 'spend')
  }

  // ---- SAVINGS ----
  // Cash asset, low transaction volume. Interest = income; transfers = transfer;
  // fees = fee; merchant-like activity = needs_review.
  if (at === 'savings') {
    if (_matchAny(desc, _INTEREST_EARNED_PATTERNS))
      return _result(absAmt, 'interest', 'earn')
    if (_matchAny(desc, _TRANSFER_PATTERNS))
      return _result(absAmt, 'transfer', 'transfer')
    if (_matchAny(desc, _FEE_PATTERNS))
      return _result(absAmt, 'fee', 'spend')
    // Merchant-like debit from savings — flag for review
    if (isNeg && !_matchAny(desc, _TRANSFER_PATTERNS))
      return _result(absAmt, 'needs_review', 'transfer', true, 'Savings account debit without transfer pattern — may be a merchant purchase or fee.')
    if (isPos) return _result(absAmt, 'transfer', 'transfer')
    return _result(absAmt, 'transfer', 'transfer')
  }

  // ---- DEBIT CARD ----
  // Cash-spend rail. Purchase = expense; refund = expense_reversal;
  // deposit = income; ATM = transfer.
  if (at === 'debit_card') {
    if (_matchAny(desc, _REFUND_PATTERNS))
      return _result(absAmt, 'expense_reversal', 'earn')
    if (_matchAny(desc, _INCOME_PATTERNS))
      return _result(absAmt, 'income', 'earn')
    if (_matchAny(desc, _TRANSFER_PATTERNS))
      return _result(absAmt, 'transfer', 'transfer')
    if (_matchAny(desc, _FEE_PATTERNS))
      return _result(absAmt, 'fee', 'spend')
    if (isPos) return _result(absAmt, 'income', 'earn')
    return _result(absAmt, 'expense', 'spend')
  }

  // ---- OTHER ----
  // Unknown semantics — flag for manual review.
  if (at === 'other') {
    return _result(absAmt, 'needs_review', 'transfer', true, `Unknown account type "other" — manually classify this transaction.`)
  }

  // ---- Fallback (unrecognized account type) ----
  return _result(absAmt, 'needs_review', 'transfer', true, `Unrecognized account type "${at}" — add classification rules for this type.`)
}

export type ReadinessState = 'ready' | 'unavailable' | 'blocked' | 'degraded' | 'disabled'
export type OverallReadinessState = 'ready' | 'ready_with_blocked_optional_capabilities' | 'configuration_failure' | 'unsafe_state'

export interface ReadinessComponent {
  component: string
  state: ReadinessState
  reason_code: string
  recovery_action: string
  last_checked: string
  dependencies: Record<string, boolean>
  version?: string | null
}

export interface ReadinessResponse {
  schema_version: 'atlas-readiness/v1'
  overall_state: OverallReadinessState
  checked_at: string
  checks: ReadinessComponent[]
  feature_flags: Record<string, boolean>
  credentials: Record<string, boolean>
  prohibited_capabilities: Record<string, 'disabled' | 'not_configured'>
}

export interface Profile {
  id: number
  email: string
  full_name: string
  currency_preference?: string
  /** Free-form string the user types in Settings ("15M", "$15,000,000",
   *  "15000000"). Mirrors the BE ``users.target_net_worth`` String column. */
  target_net_worth?: string | null
  /** User-set default horizon (years). ``null`` when unset; the FE
   *  falls back to the hardcoded 20y constant in FinancialPlans. */
  time_horizon_years?: number | null
}

export interface Account {
  id: number
  account_name: string
  account_type: string
  account_subtype?: string | null
  account_number?: string | null
  current_balance: number
  is_active: boolean
  last_sync?: string | null
  // Phase 16 — every account belongs to a FamilyMember. The
  // route layer defaults to the local user's Self row on POST
  // when the FE omits this field, so the field is always
  // populated for active accounts. The Accounts page select
  // uses it to render the per-account family-member chip.
  family_member_id: number
  // Phase 40 — coarse provenance (manual / imported / plaid) auto-
  // stamped by the route layer at every create path. The FE renders
  // a chip per value (see ``ACCOUNT_SOURCE_LABELS``).
  source?: AccountSource
  // Phase 40 — free-text note. Auto-filled by the BE with a parser
  // diagnostic on import; user-editable via the Edit modal.
  description?: string | null
}

/** Phase 40 — coarse provenance + free-text note on every account. The
 *  FE renders a per-source chip (Manual / Imported / Plaid) below the
 *  account-type sub-line on the Accounts page; the free-text
 *  ``description`` is auto-filled at every BE create-path with a
 *  parser-aware diagnostic (e.g. "Fidelity Investment Report: 4
 *  accounts from Portfolio_Positions.csv") and editable via the Edit
 *  modal. Three values — any new value (e.g. ``"brokerage-api"``)
 *  requires a coordinated schema + UI change. */
export const ACCOUNT_SOURCE_LABELS = [
  { value: 'manual', label: 'Manual' },
  { value: 'imported', label: 'Imported' },
  { value: 'plaid', label: 'Plaid' },
] as const

export type AccountSource =
  (typeof ACCOUNT_SOURCE_LABELS)[number]['value']

/** Phase 16+ — house-wide profile field enums. Mirrors the Pydantic
 *  ``Literal[...]`` sets on the BE so the FE's <select> options stay
 *  in lockstep. A value the BE doesn't recognise 422s at create /
 *  update time, so the FE can never accidentally widen the enum.
 *  The canonical ordering matches the BE schema (Self is reserved
 *  for the per-user Self row; the other 5 buckets are user-pickable). */
export const RELATIONSHIP_OPTIONS = [
  { value: 'Self', label: 'Self' },
  { value: 'Spouse', label: 'Spouse' },
  { value: 'Child', label: 'Child' },
  { value: 'Parent', label: 'Parent' },
  { value: 'Sibling', label: 'Sibling' },
  { value: 'Other', label: 'Other' },
] as const

export const WORKING_STATUS_OPTIONS = [
  { value: 'Employed', label: 'Employed' },
  { value: 'Unemployed', label: 'Unemployed' },
  { value: 'Student', label: 'Student' },
  { value: 'Retired', label: 'Retired' },
  { value: 'Homemaker', label: 'Homemaker' },
  { value: 'Other', label: 'Other' },
] as const

export type Relationship =
  (typeof RELATIONSHIP_OPTIONS)[number]['value']
export type WorkingStatus =
  (typeof WORKING_STATUS_OPTIONS)[number]['value']

/** Phase 24 + Phase 27 — DB-backed substring merchant rule.
 *  Mirrors the BE shape ``MerchantRuleResponse`` exactly so a
 *  single cast covers the FE row. ``category_name`` is denormalised
 *  on the BE so the FE can render the per-category chip without
 *  an N+1 lookup.
 *
 *  ``priority`` controls the order the categorizer scans rules within
 *  a single category — lower numbers hit FIRST. The Settings UI lets
 *  the user re-prioritise via PUT (a future quick-action "Move up /
 *  down" affordance would also edit this column).
 *
 *  ``is_archived`` is the canonical DELETE path (soft-delete). The
 *  row stays in the DB so the boot-time seed helper SKIPS it on
 *  subsequent cold starts — a hard delete would let the helper
 *  re-INSERT the system keyword, silently undoing the user's delete.
 *
 *  ``source`` (Phase 27) is the immutable provenance. The Settings
 *  UI renders a per-source chip (system / manual / tag-rule / llm /
 *  imported) so the user can answer "did this come from the seed
 *  ("fizzy") or from a Tag Rule or from an import?" at a glance.
 */
export interface MerchantRule {
  id: number
  category_id: number
  category_name: string | null
  keyword: string
  priority: number
  is_archived: boolean
  source: MerchantRuleSource
  created_at?: string | null
  updated_at?: string | null
}

export const MERCHANT_RULE_SOURCE_OPTIONS = [
  { value: 'system', label: 'System seed (fizzy)' },
  { value: 'manual', label: 'Manual (Settings)' },
  { value: 'tag-rule', label: 'Tag rule (Activity)' },
  { value: 'llm', label: 'LLM-suggested' },
  { value: 'imported', label: 'Imported (CSV)' },
] as const

export type MerchantRuleSource =
  (typeof MERCHANT_RULE_SOURCE_OPTIONS)[number]['value']

/** Phase 27 — per-row summary returned by
 *  ``POST /api/merchant-rules/import``. The FE renders
 *  ``"Imported 47 rules — 3 already existed, 2 had errors"`` from
 *  this shape without a follow-up GET. ``errors`` items carry a
 *  row number + a human-readable reason so a user can open the
 *  CSV in Excel and fix line 6 / line 9 directly. */
export interface MerchantRuleImportError {
  row: number
  reason: string
}

export interface MerchantRuleImportResult {
  inserted: number
  skipped_existing: number
  errors: MerchantRuleImportError[]
}

export interface FamilyMember {
  id: number
  name: string
  /** Hex color string `#RRGGBB`. Validated server-side by Pydantic. */
  color: string
  /** True for the per-user Self row (bootstrapped by the BE on
   *  first authenticated request, NOT POSTable). The Settings
   *  Family Members card renders a "(Self)" badge next to it. */
  is_self: boolean
  is_archived: boolean
  /** Phase 16+ — household profile. All three are nullable on the
   *  BE so a freshly-created row normally has them unset; the
   *  Settings card prompts the user to fill them in via the PUT
   *  path. The Self row's ``relationship`` is hard-coded to
   *  ``'Self'`` on the BE and is NOT user-editable. */
  relationship?: Relationship | null
  working_status?: WorkingStatus | null
  /** Current age in years. ``null`` when unset; the FE renders this
   *  with a ``" yrs"`` suffix on the Settings card sub-line. */
  age?: number | null
  created_at?: string | null
  updated_at?: string | null
}

export interface DashboardSummary {
  total_balance: number
  total_income_month: number
  total_expenses_month: number
  accounts_count: number
  transactions_count: number
  last_sync?: string | null
  import_batches_count: number
  last_import_at?: string | null
  /** Phase 8 — the local user's non-archived goals, ordered by priority
   *  DESC then created_at ASC. The FE's ``FinancialPlans`` component
   *  replaces the hardcoded $15M constant with this list, rendering one
   *  card per goal. Empty list = no goals configured. */
  user_goals?: Goal[]/** Default goal anchor — derived from ``user_goals[0]`` on the
 *  BE. Phase 15 removed the separate ``User.target_net_worth``
 *  / ``User.time_horizon_years`` profile columns and the
 *  ``default_goal_target`` / ``default_goal_horizon_years``
 *  forwarder enrichment (the Goals page now seeds a goal on first
 *  list so ``user_goals`` is never empty for a returning user). */
}

// Phase 35 — Dashboard Redesign: Money Flow types
// Phase 52+ — node_type now accepts CashflowRole values for role-aware Sankey
// rendering. Legacy values ('income'/'expense'/'allocation'/'outcome') are
// still accepted for backward compat with the current backend /api/dashboard/flows.
export interface SankeyNode {
  name: string
  node_type: 'income' | 'expense' | 'allocation' | 'outcome' | CashflowRole
  color?: string | null
  /** Phase 52+ — optional role tag for Sankey coloring. When set, overrides
   *  the legacy node_type for visual treatment. */
  role?: CashflowRole
  /** Phase C — hierarchical group tag for group-aware coloring. */
  group?: string | null
  /** Phase C — Sankey depth level (0=income sources, 1=total income pool,
   *  2=group nodes, 3=subcategory leaves). */
  level?: number | null
}

/** Phase 52+ — canonical colors for each CashflowRole. Used by the Sankey
 *  and Breakdown components to render consistent role-based visuals. */
export const ROLE_COLORS: Record<CashflowRole, string> = {
  spend:    '#DC2626', // crimson — expenses, fees, purchases
  earn:     '#059669', // emerald — income, dividends, interest
  save:     '#6366F1', // indigo — contributions, principal payments
  invest:   '#0EA5E9', // sky — investment buys/sells
  debt:     '#F59E0B', // amber — interest on loans, fees
  transfer: '#9CA3AF', // slate — internal money movement
}

// Phase D — Hierarchical category group constants.
// Canonical color + label for each of the 5 category groups.
// Shared across SpendingByCategory, SpendByCategoryBar, BreakdownPanel,
// Activity filter, Settings merchant rules, Income/Expenses pages.
export const CATEGORY_GROUP_COLORS: Record<string, string> = {
  Income:       '#059669', // emerald
  Expenses:     '#DC2626', // crimson
  Debt:         '#F59E0B', // amber
  Investments:  '#0EA5E9', // sky
  Transfer:     '#9CA3AF', // slate
}

export const CATEGORY_GROUP_LABELS: Record<string, string> = {
  Income:       'Income',
  Expenses:     'Expenses',
  Debt:         'Debt',
  Investments:  'Investments',
  Transfer:     'Transfers',
}

/** Group display order — Income first, then Expenses, Debt, Investments, Transfer. */
export const CATEGORY_GROUP_ORDER = ['Income', 'Expenses', 'Debt', 'Investments', 'Transfer'] as const

// Phase E — CashflowRole → Category Group mapping.
// Maps the high-level cashflow classification role to the corresponding
// hierarchical category group. Used for consistent visual alignment between
// the Sankey/dashboard cashflow model and the category group taxonomy.
//
// The mapping is:
//   earn (income, dividends, interest)     → Income
//   spend (expenses, fees, purchases)      → Expenses
//   save (contributions, principal pay)    → Investments
//   invest (investment buys/sells)         → Investments
//   debt (debt service)                    → Debt
//   transfer (internal money movement)     → Transfer
export const CASHFLOW_ROLE_TO_GROUP: Record<CashflowRole, string> = {
  earn:     'Income',
  spend:    'Expenses',
  save:     'Investments',
  invest:   'Investments',
  debt:     'Debt',
  transfer: 'Transfer',
}

/** Phase 52+ — human-readable labels for each CashflowRole. */
export const ROLE_LABELS: Record<CashflowRole, string> = {
  spend:    'Spend',
  earn:     'Earn',
  save:     'Save',
  invest:   'Invest',
  debt:     'Debt',
  transfer: 'Transfer',
}

export interface SankeyLink {
  source: number
  target: number
  value: number
}

export interface DashboardFlowsResponse {
  nodes: SankeyNode[]
  links: SankeyLink[]
  period_start: string
  period_end: string
  total_income: number
}

export interface TrendDataPoint {
  month: string
  income: number
  spend: number
  retained: number
}

export interface DashboardTrendsResponse {
  trends: TrendDataPoint[]
}

// Phase 35 (Phase 2) — Dashboard Breakdown
export interface BreakdownBucket {
  label: string
  amount: number
  color: string
  percentage: number
}

export interface DashboardBreakdownResponse {
  buckets: BreakdownBucket[]
  total_spend: number
  period: string
}

// ---- Atlas Phase 1 — Budget types ----

export interface Budget {
  id: number
  user_id: number
  category_id: number | null
  category_name: string | null
  amount: number
  period: string
  created_at?: string | null
  updated_at?: string | null
}

export interface BudgetCategoryStatus {
  category_id: number
  category_name: string
  budget_group: string
  planned: number
  actual: number
  remaining: number
  percent_used: number
}

export interface BudgetStatusResponse {
  period: string
  categories: BudgetCategoryStatus[]
  totals: {
    planned: number
    actual: number
    remaining: number
    percent_used: number
  }
}

// ---- Atlas Phase 2 — Income/Expense/Debt breakdown types ----

export interface BreakdownByGroup {
  group: string
  amount: number
  percentage: number
}

export interface BreakdownByCategory {
  category_id: number
  category_name: string
  budget_group: string
  amount: number
}

export interface BreakdownTrendPoint {
  month: string
  amount: number
}

export interface IncomeBreakdownResponse {
  period_start: string
  period_end: string
  total_income: number
  by_group: BreakdownByGroup[]
  by_category: BreakdownByCategory[]
  trend: BreakdownTrendPoint[]
}

export interface ExpenseBreakdownResponse {
  period_start: string
  period_end: string
  total_expenses: number
  by_group: BreakdownByGroup[]
  by_category: BreakdownByCategory[]
  trend: BreakdownTrendPoint[]
}

export interface DebtItem {
  account_id: number
  account_name: string
  account_type: string
  balance: number
  interest_rate: number | null
  minimum_payment: number | null
  credit_limit: number | null
  term_months: number | null
  utilization: number | null
}

export interface DebtsSummaryResponse {
  total_debt: number
  blended_apr: number
  total_monthly_minimum: number
  debts: DebtItem[]
}

export interface InsightItem {
  type: 'warning' | 'info' | 'success'
  category: string
  message: string
  current: number
  previous: number
  change_pct: number
}

export interface InsightsResponse {
  insights: InsightItem[]
}

// Phase 3 — Alert types (anomalies + upcoming bills)
export interface AnomalyItem {
  transaction_id: number
  merchant: string
  amount: number
  median: number
  multiplier: number
  date?: string | null
}

export interface AnomaliesResponse {
  anomalies: AnomalyItem[]
  count: number
}

export interface UpcomingBillItem {
  merchant: string
  median_amount: number
  median_interval_days: number
  last_date?: string | null
  predicted_next_date?: string | null
  confidence: number
  hit_count: number
}

export interface UpcomingBillsResponse {
  bills: UpcomingBillItem[]
  count: number
}

// Phase 4 — Recommendation approval workflow types
export interface RecommendationLogItem {
  id: number
  user_id: number
  title: string
  description: string
  priority: 'high' | 'medium' | 'low'
  status: 'pending' | 'approved' | 'denied' | 'dismissed'
  category: string
  impact?: string | null
  metadata_json?: string | null
  created_at: string
  resolved_at?: string | null
  resolved_by?: string | null
}

export interface RecommendationLogListResponse {
  items: RecommendationLogItem[]
  total: number
  pending_count: number
}

export interface RecommendationLogCreate {
  title: string
  description?: string
  priority?: 'high' | 'medium' | 'low'
  category?: string
  impact?: string | null
  metadata_json?: string | null
}

export interface RecommendationStatsResponse {
  total: number
  pending: number
  approved: number
  denied: number
  dismissed: number
}

export interface Goal {
  id: number
  name: string
  /** Target dollar amount the user is saving toward. */
  target_amount: number
  /** ISO date string (YYYY-MM-DD) for an explicit deadline. May be
   *  null if the user expressed the deadline as ``horizon_years`` instead. */
  target_date?: string | null
  /** Number of years from today. May be null if the user expressed
   *  the deadline as ``target_date``. Used as the projection horizon
   *  in ``FinancialPlans``. */
  horizon_years?: number | null
  /** User-controlled sort priority. Higher numbers render first.
   *  Used by the BE to sort the list + dashboard summary top-down. */
  priority: number
  is_archived: boolean
  /** Free-text annotation; rendered as a tooltip on the GoalManager card. */
  notes?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface Category {
  id: number
  name: string
  description?: string | null
  icon?: string | null
  color?: string | null
  /** Atlas Phase 1 — budget classification: fixed, flexible, debt, savings, other. */
  budget_group?: string | null
  /** Phase A — hierarchical taxonomy group: Income, Expenses, Debt, Investments, Transfer. */
  group?: string | null
}

export interface Transaction {
  id: number
  description: string
  amount: number
  transaction_date: string
  merchant_name?: string | null
  is_pending: boolean
  // Phase 11 — flattened account + category info so the activity page
  // can filter/sort/render without N+1 follow-up reads. ``None``
  // when the FK row is missing (defensive; should never happen).
  account_id?: number | null
  account_name?: string | null
  account_type?: string | null
  category_id?: number | null
  category_name?: string | null
  // Phase 52+ — dual-column Debit/Credit bookkeeping for credit-card
  // statements. Banks report purchases as `Debit` (charge against the
  // account — money that LEFT) and payments as `Credit` (payment
  // APPLIED to the account — money that ENTERED). The signed `amount`
  // above is preserved for sort + compatibility; ``amount =
  // credit - debit`` is the bank-statement invariant.
  //
  // Both are ``null`` for amount=0 (FX-neutral) rows AND for
  // non-credit-card accounts (the BE only persisted them when the
  // source statement had a debit/credit column; checking/savings rows
  // use the legacy single-column path and both fields stay NULL).
  // The Activity page renders dedicated Debit / Credit columns that
  // surface these as two side-by-side figures.
  debit?: number | null
  credit?: number | null
  // Phase 54+ — duplicate tracking. When a transaction was flagged
  // as a duplicate during import, ``is_duplicate=true`` and
  // ``duplicate_of_id`` points to the original. The Activity page
  // renders a duplicate badge and resolve action.
  is_duplicate?: boolean
  duplicate_of_id?: number | null
}

export interface ImportBatch {
  id: number
  filename: string
  file_type: string
  record_count: number
  account_id: number
  saved_transactions: number
  created_at?: string | null
  processed_at?: string | null
  // Phase 11 — first N text lines the parser captured at upload time.
  // Lets the FE render a preview panel for historical PDF / OCR imports
  // where ``saved_transactions == 0`` (the user's "nothing loads"
  // complaint on Phase 10 PDF batches).
  preview_lines?: any[] | null
  // Phase 39 — when a multi-account import split transactions across
  // several accounts, the FE's import-history table renders "2 accounts"
  // instead of just one account name. ``null`` for single-account batches.
  multi_account_ids?: number[] | null
}

// Phase 39 — Portfolio Holdings (positions import + live pricing).
export interface Holding {
  id: number
  account_id: number
  account_name?: string | null
  symbol?: string | null
  description?: string | null
  quantity?: number | null
  last_price?: number | null
  current_value: number
  cost_basis_total?: number | null
  type?: string | null
  live_price?: number | null
  live_value?: number | null
  day_change_pct?: number | null
}

export interface PortfolioImportResult {
  holdings_count: number
  accounts_created: number
  accounts_updated: number
  total_value: number
  warnings: string[]
  account_ids: number[]
}

/** Phase 41 — request body for `POST /api/holdings/`. Mirrors the BE
 *  `HoldingManualCreate` Pydantic schema. Provide EITHER an existing
 *  `account_id` OR a new `account_name` (auto-creates a 'Portfolio'
 *  account). The route recomputes `current_value = last_price *
 *  quantity` when only `last_price` is set; if both are omitted it
 *  400s so the FE surfaces a clean validation message instead of an
 *  opaque 500. */
export interface HoldingManualCreate {
  account_id?: number | null
  account_name?: string | null
  symbol: string
  description?: string | null
  quantity: number
  last_price?: number | null
  current_value?: number | null
  cost_basis_total?: number | null
  type?: string | null
}

/** Phase 47 — partial-update body for `PUT /api/holdings/{id}`. Mirrors
 *  the BE `HoldingUpdate` Pydantic schema exactly. Every field is
 *  optional (PATCH semantics) so the FE's Edit modal can build a
 *  multi-field patch in one round-trip. The BE uses
 *  `model_dump(exclude_unset=True)` so an omitted key from the FE
 *  payload leaves the underlying row alone (the Omit = leave alone
 *  contract).
 *
 *  ``account_id`` is INTENTIONALLY NOT in this shape so a FE bug
 *  cannot accidentally desync two account balances via a quiet
 *  cross-account transfer. A future "Transfer" affordance owns
 *  that — Phase 48+.
 *
 *  When the patch includes ``quantity``, the BE auto-derives
 *  ``current_value = last_price * quantity`` (so the user just
 *  types the new share count). When the patch does NOT include
 *  ``quantity``, ``current_value`` is left alone — a single-field
 *  price correction never silently zeroes the position value.
 */
export interface HoldingUpdate {
  symbol?: string | null
  description?: string | null
  quantity?: number | null
  last_price?: number | null
  current_value?: number | null
  cost_basis_total?: number | null
  type?: string | null
}

export interface HoldingsRefreshResult {
  holdings: Holding[]
  warning?: string | null
  prices_updated: number
}

/** Pairs with `POST /api/imports/upload` — mirrors `ImportResponse` in
 *  `services/rules-service/app/schemas/__init__.py`. The CSV/OFX
 *  server-side parse returns the first 5 records as `preview` (CSV rows
 *  are objects, PDF/OFX lines are strings). */
// Phase 30c — Assistant conversation + message types.
export interface AssistantMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  tool_used?: string | null
  tool_result?: Record<string, unknown> | null
  follow_ups?: string[]
  status: 'ok' | 'offline' | 'error'
  created_at: string
}

export interface AssistantConversation {
  id: number
  title: string
  created_at: string
  updated_at: string
  messages: AssistantMessage[]
}

export interface ImportResult {
  filename: string
  file_type: string
  record_count: number
  preview: any[]
  /** Server-resolved account id that received the rows.
   *  Be sure `account_id` matches `services/.../schemas/__init__.py::ImportResponse`
   *  which declares it `Optional[int] = None`. The component renders it with
   *  `?? '—'` so the field must allow undefined/null at the type level. */
  account_id?: number | null
  batch_id: number
  saved_transactions: number
  /** Phase 12 — raw row count before filtering. When > saved_transactions,
   *  the FE renders a warning so the user sees exactly how many rows were
   *  dropped. */
  expected_row_count?: number | null
  /** Phase 12 — human-readable warnings from the parser (e.g.
   *  "34 of 415 rows could not be imported"). */
  warnings?: string[]
  /** Phase 39 — when a multi-account import split transactions across
   *  several accounts (e.g. Fidelity Investment Report → brokerage + HSA),
   *  the FE renders "Imported into 2 accounts" instead of showing only
   *  the ``account_id``. ``null`` for single-account imports. */
  multi_account_ids?: number[] | null
  /** Phase 52 — the account type the parser auto-detected from the
   *  statement content (e.g. "credit_card", "checking", "investment").
   *  When non-null and the user has no explicit account selected,
   *  the FE can prompt to confirm before completing the import.
   *  ``null`` when detection was uncertain or the user selected a
   *  specific account. */
  suggested_account_type?: string | null
  /** Phase 17 — auto-categorize summary surfaced to the FE so the
   *  ImportStatementUpload success toast can render "Auto-tagged N of
   *  M" without bouncing the user to the Activity page's manual
   *  categorize button. ``auto_categorize_total`` is the count of
   *  NOT-YET-categorized rows at import time (= ``saved_transactions``
   *  if every row was uncategorized; < ``saved_transactions`` if some
   *  rows had manual pre-tags, e.g. an OCR re-import that didn't wipe
   *  ``category_id``). ``auto_categorized`` is the count of rows that
   *  received a category id via the heuristic during the per-batch
   *  post-commit pass. ``auto_categorize_no_match`` is the count of
   *  rows where the heuristic ran but didn't match any keyword
   *  (``auto_categorize_total - auto_categorized - already_correct``)
   *  — surfaces the third bucket so the success message can warn
   *  "K need a manual pick" instead of leaving the user to discover
   *  un-tagged rows later. All three are ``null`` for legacy callers. */
  auto_categorized?: number | null
  auto_categorize_total?: number | null
  auto_categorize_no_match?: number | null
}

// ---- Default singleton ------------------------------------------------
// The ``api`` singleton is built by calling the factory with a
// loginFn that calls the (module-local) ``rulesService.devLogin``.
// This breaks the previous circular dep: ``api`` no longer needs to
// reference ``rulesService`` at interceptor-registration time.
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8888'
const api = createApiWithAuthRetry({
  // Keep the browser API host on the same host string as the UI origin
  // so the `fc_session` SameSite=Lax cookie can be sent on XHR requests.
  // Only apply the `localhost -> 127.0.0.1` patch on the server side
  // where Node 18+ DNS resolution can otherwise choose IPv6 and fail.
  baseURL:
    typeof window === 'undefined'
      ? apiBaseUrl.replace('localhost', '127.0.0.1')
      : apiBaseUrl,
  deps: {
    loginFn: async () => {
      // The factory defers this to first-401, by which time
      // ``rulesService.devLogin`` is bound to the same ``api``
      // instance — closing the loop without a static cycle.
      return rulesService.devLogin()
    },
  },
})

// ---- Service methods ---------------------------------------------------
export const rulesService = {
  // Auth + profile
  devLogin: async (sub?: string): Promise<{ token: string; subject: string }> => {
    const params = sub ? `?sub=${encodeURIComponent(sub)}` : ''
    const response = await api.post(`/api/auth/devlogin${params}`)
    setStoredToken(response.data.token)
    return response.data
  },

  logout: async (): Promise<{ logged_out: boolean }> => {
    const response = await api.post('/api/auth/logout')
    clearStoredToken()
    return response.data
  },

  getProfile: async (): Promise<Profile> => {
    const response = await api.get('/api/profile/')
    return response.data
  },

  getReadiness: async (): Promise<ReadinessResponse> => {
    const response = await api.get('/api/system/readiness')
    return response.data
  },

  updateProfile: async (patch: Partial<Profile>): Promise<Profile> => {
    const response = await api.put('/api/profile/', patch)
    return response.data
  },

  // Dashboard
  getDashboardSummary: async (): Promise<DashboardSummary> => {
    const response = await api.get('/api/dashboard/summary')
    return response.data
  },

  // Phase 35 — Dashboard Redesign: Money Flow
  // Accepts either a single month (period) or a full date range.
  getDashboardFlows: async (rangeOrPeriod?: string, toDate?: string): Promise<DashboardFlowsResponse> => {
    const params: Record<string, string> = {}
    if (rangeOrPeriod && toDate) {
      params.from_date = rangeOrPeriod
      params.to_date = toDate
    } else if (rangeOrPeriod) {
      params.period = rangeOrPeriod
    }
    const response = await api.get('/api/dashboard/flows', { params })
    return response.data
  },

  getDashboardTrends: async (months?: number): Promise<DashboardTrendsResponse> => {
    const params = months ? { months } : {}
    const response = await api.get('/api/dashboard/trends', { params })
    return response.data
  },

  // Phase 35 (Phase 2) — Dashboard Breakdown
  // Accepts either a single month (period) or a full date range.
  getDashboardBreakdown: async (rangeOrPeriod?: string, toDate?: string): Promise<DashboardBreakdownResponse> => {
    const params: Record<string, string> = {}
    if (rangeOrPeriod && toDate) {
      params.from_date = rangeOrPeriod
      params.to_date = toDate
    } else if (rangeOrPeriod) {
      params.period = rangeOrPeriod
    }
    const response = await api.get('/api/dashboard/breakdown', { params })
    return response.data
  },

  // Accounts
  listAccounts: async (): Promise<Account[]> => {
    const response = await api.get('/api/accounts/')
    return response.data
  },

  createAccount: async (payload: {
    account_name: string
    account_type: string
    institution_name: string
    current_balance?: number
    family_member_id?: number
    /** Optional last-4-or-full account number. When set, the Accounts
     *  page's "Show numbers" toggle will reveal it; when omitted /
     *  null, the toggle is a no-op for that card (existing card
     *  behavior). Mirrors ``AccountCreate.account_number`` on the BE. */
    account_number?: string | null
    /** Phase 40 — free-text note. The route layer stamps
     *  ``source='manual'`` regardless of what the FE sends on this
     *  path; the upload routes overwrite with ``"imported"`` and
     *  Plaid with ``"plaid"``. ``description`` is whatever the user
     *  typed in the Add-Account textarea (None when left empty). */
    description?: string | null
  }): Promise<Account> => {
    const response = await api.post('/api/accounts/', payload)
    return response.data
  },

  /** Partial update — pairs with `PUT /api/accounts/{id}`. Only declared
   *  fields on the BE's `AccountUpdate` schema are accepted; unknown keys
   *  are silently dropped server-side (Phase 7 whitelist contract). */
  updateAccount: async (
    id: number,
    patch: Partial<{
      account_name: string
      account_type: string
      institution_name: string
      current_balance: number
      family_member_id?: number
      /** Optional. Send ``null`` to CLEAR the stored account number
       *  (the next render of the card no longer shows the masked-
       *  last4 footer and the "Show numbers" toggle effectively
       *  has no effect on that card). Omit to leave untouched. */
      account_number?: string | null
      /** Phase 40 — free-text note. Optional; the Edit modal
       *  textarea can amend the auto-filled import description
       *  (e.g. "Roth IRA, maxed out 2024") without re-running
       *  the upload. Omit to leave untouched; send ``null`` to
       *  clear. ``source`` is INTENTIONALLY NOT in the patch
       *  shape — provenance is immutable past creation (Phase
       *  27 precedent on ``merchant_rules.source``). */
      description?: string | null
    }>,
  ): Promise<Account> => {
    const response = await api.put(`/api/accounts/${id}`, patch)
    return response.data
  },

  /** Soft-delete — pairs with `DELETE /api/accounts/{id}`. The server flips
   *  `is_active=False` (preserves FKs for transactions + import_batches);
   *  the row stops appearing in `listAccounts` and can be reactivated via
   *  `updateAccount(..., { is_active: true })`. */
  deleteAccount: async (id: number): Promise<void> => {
    await api.delete(`/api/accounts/${id}`)
  },

  /** Create with explicit family member — pairs with
   *  ``POST /api/accounts/`` plus the optional ``family_member_id``
   *  field. The route defaults to the local user's Self row when
   *  omitted. The Accounts page select uses this hook to attach
   *  new accounts to a non-Self member (Spouse / Kid). */
  createAccountFor: async (
    payload: {
      account_name: string
      account_type: string
      institution_name: string
      current_balance?: number
      family_member_id?: number
      account_number?: string | null
      description?: string | null
    },
  ): Promise<Account> => {
    const response = await api.post('/api/accounts/', payload)
    return response.data
  },

  // Phase 16 — family members (per-user grouping of accounts).
  listFamilyMembers: async (): Promise<FamilyMember[]> => {
    const response = await api.get('/api/family-members/')
    return response.data
  },

  createFamilyMember: async (payload: {
    name: string
    /** Hex color string `#RRGGBB` enforced server-side. */
    color: string
    /** Phase 16+ — household profile. All optional on POST so the
     *  user can land a Spouse row in two clicks (name + color)
     *  and fill out the rest later via ``updateFamilyMember``. */
    relationship?: Relationship | null
    working_status?: WorkingStatus | null
    age?: number | null
  }): Promise<FamilyMember> => {
    const response = await api.post('/api/family-members/', payload)
    return response.data
  },

  updateFamilyMember: async (
    id: number,
    patch: Partial<{
      name: string
      color: string
      /** Phase 16+ — see ``createFamilyMember``. Note: the BE
       *  force-overrides ``relationship`` to ``'Self'`` when patching
       *  the per-user Self row, regardless of what the client sends
       *  (defence-in-depth). The Settings card already disables the
       *  <select> while editing the Self row so the user NEVER sees
       *  an auto-reverted ``relationship`` value. */
      relationship?: Relationship | null
      working_status?: WorkingStatus | null
      age?: number | null
    }>,
  ): Promise<FamilyMember> => {
    const response = await api.put(`/api/family-members/${id}`, patch)
    return response.data
  },

  /** Soft-archive — pairs with ``DELETE /api/family-members/{id}``.
   *  The server flips ``is_archived=True`` if zero active accounts
   *  are linked; otherwise returns 409 with a "Cannot archive:
   *  N active account(s)" detail. Archiving the Self row 400s. */
  deleteFamilyMember: async (id: number): Promise<void> => {
    await api.delete(`/api/family-members/${id}`)
  },

  // Transactions
  // Phase 11 — extended query params so the activity page issues ONE
  // request with account/date/category/account_type filters + sort +
  // search rather than client-side post-processing a giant payload.
  // Phase 28 — added ``uncategorized: true`` shortcut so the
  // Activity page's "Untagged" status filter can pull every
  // ``category_id IS NULL`` row in one round-trip without a
  // synthetic "uncategorized" Category row.
  listTransactions: async (params?: {
    account_id?: number
    account_type?: string
    from_date?: string
    to_date?: string
    category_id?: number
    is_pending?: boolean
    /** Phase 28 — when true, restrict to rows with category_id IS
     *  NULL. Mutually exclusive with ``category_id`` on the BE:
     *  ``uncategorized`` wins. Pairs with the Activity page's
     *  "Untagged" status filter. */
    uncategorized?: boolean
    search?: string
    sort_by?: 'transaction_date' | 'amount' | 'description' | 'created_at'
    sort_dir?: 'asc' | 'desc'
    limit?: number
  }): Promise<Transaction[]> => {
    // Drop undefined keys so axios doesn't serialize `undefined` in
    // the URL — some servers tolerate it but axios sometimes sends
    // `foo=undefined` which never matches a backend Optional query.
    const cleaned: Record<string, unknown> = {}
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null && v !== '') {
          cleaned[k] = v
        }
      }
    }
    const response = await api.get('/api/transactions/', { params: cleaned })
    return response.data
  },

  /** Partial update — pairs with ``PUT /api/transactions/{id}``.
   *  Only fields declared on the BE's ``TransactionUpdate`` schema are
   *  accepted; unknown keys are silently dropped server-side. The
   *  current mutable fields are ``category_id`` (manual override
   *  after auto-categorize) + ``merchant_name`` (correct a parser
   *  guess, e.g. ``"SQ *STARBUCKS"`` → ``"Starbucks"``). */
  updateTransaction: async (
    id: number,
    patch: Partial<{
      category_id: number | null
      merchant_name: string | null
    }>,
  ): Promise<Transaction> => {
    const response = await api.put(`/api/transactions/${id}`, patch)
    return response.data
  },

  /** Bulk auto-categorize — pairs with ``POST /api/transactions/categorize``.
   *  Returns ``{categorized, skipped, total}`` so the FE can render
   *  a "tagged N of M" toast without a follow-up GET. Pure substring
   *  heuristic on the BE; no LLM call. */
  /** Phase 54+ — resolve ALL duplicate transactions at once.
   *  Pairs with `POST /api/transactions/resolve-duplicates`.
   *  Three actions: 'keep_all' (accept both), 'keep_original'
   *  (delete duplicates), 'keep_this' (delete originals). */
  resolveAllDuplicates: async (
    action: 'keep_all' | 'keep_original' | 'keep_this' = 'keep_all',
  ): Promise<{ action: string; message: string }> => {
    const response = await api.post(`/api/transactions/resolve-duplicates?action=${action}`)
    return response.data
  },

  /** Phase 54+ — resolve a SINGLE duplicate transaction.
   *  Pairs with `POST /api/transactions/{id}/resolve-duplicate`.
   *  Three actions: 'keep_both' (accept both), 'keep_original'
   *  (delete this duplicate), 'keep_this' (delete the original). */
  resolveDuplicate: async (
    id: number,
    action: 'keep_both' | 'keep_original' | 'keep_this',
  ): Promise<{ action: string; message: string }> => {
    const response = await api.post(`/api/transactions/${id}/resolve-duplicate?action=${action}`)
    return response.data
  },

  autoCategorizeAll: async (): Promise<{
    categorized: number
    skipped: number
    total: number
  }> => {
    const response = await api.post('/api/transactions/categorize')
    return response.data
  },

  /** Phase 22 — Pass 4 LLM-categorize. Pairs with
   *  ``POST /api/categorize/llm-batch`` on the BE. Takes a list of
   *  ``{transaction_id, merchant_name?, description?, amount?}``
   *  rows (≤20 per user's spec) and returns the LLM suggestions
   *  with a cooldown cache so repeat runs are free.
   *
   *  Response errors map to status codes that the FE surfaces
   *  through a retry banner:
   *
   *  - **422** — over the 20-row cap; the FE should chunk its picker.
   *  - **502** — Ollama returned invalid JSON (probably ignored the
   *    JSON-mode grammar). Retry once with a smaller batch.
   *  - **503** — Ollama unreachable (process not running). Banner
   *    says "Pass 4 is offline; the heuristic button still works".
   *  - **504** — Ollama timed out (model is slow). Banner says
   *    "Try a smaller batch or a faster model".
   *
   *  Successful rows include ``cached: boolean`` so the FE's preview
   *  panel can render a small "from cache" pill on free second-pass
   *  recategorizations (saves users the "did this eat compute?"
   *  worry). ``coerced: boolean`` marks rows the BE snapped to
   *  ``Other`` because the LLM hallucinated a non-canonical name
   *  — those are pre-ticked for the user to eyeball.
   *
   *  Pure read-side: this method does NOT mutate the local user's
   *  ``Transaction`` rows. The FE's preview/accept panel loops
   *  ``updateTransaction({ category_id })`` for each Accept click.
   */
  categorizeWithLlm: async (
    transactions: Array<{
      transaction_id: number
      merchant_name?: string | null
      description?: string | null
      amount?: number | null
    }>,
  ): Promise<{
    suggestions: Array<{
      txn_id: number
      suggested_category: string
      confidence: number
      coerced?: boolean
      cached?: boolean
    }>
  }> => {
    // Drop undefined keys so the BE's Pydantic model sees clean
    // values (a habit used on listTransactions; mirrors the same
    // backend-upgrade failover the FE has for every other RPC).
    const cleaned = transactions.map((t) => {
      const o: Record<string, unknown> = { transaction_id: t.transaction_id }
      if (t.merchant_name) o.merchant_name = t.merchant_name
      if (t.description) o.description = t.description
      if (t.amount !== undefined && t.amount !== null) o.amount = t.amount
      return o
    })
    const response = await api.post('/api/categorize/llm-batch', {
      transactions: cleaned,
    })
    return response.data
  },

  // Imports
  listBatches: async (): Promise<ImportBatch[]> => {
    const response = await api.get('/api/imports/batches')
    return response.data
  },

  uploadStatement: async (file: File, accountId?: number): Promise<ImportResult> => {
    const form = new FormData()
    form.append('file', file)
    if (accountId !== undefined) form.append('account_id', String(accountId))
    const response = await api.post('/api/imports/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  },

  /** Phase 52 — upload with an explicit account type override.
   *  When the auto-detection returns ``suggested_account_type`` and
   *  the user confirms (or picks a different type), this method sends
   *  the type hint so the BE creates the account with the right type.
   *
   *  The BE uses the ``account_type_hint`` field from the multipart
   *  form to override the auto-detected type before account creation.
   *  When omitted, the BE falls back to its own detection logic. */
  uploadStatementWithType: async (
    file: File,
    accountType: string,
  ): Promise<ImportResult> => {
    const form = new FormData()
    form.append('file', file)
    form.append('account_type_hint', accountType)
    const response = await api.post('/api/imports/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  },

  /** Fetches every transaction saved for a given import batch id.
   *  Pairs with `GET /api/imports/batches/{batch_id}/transactions`. */
  listBatchTransactions: async (batchId: number): Promise<Transaction[]> => {
    const response = await api.get(`/api/imports/batches/${batchId}/transactions`)
    return response.data
  },

  /** Hard-deletes an import batch AND cascades the associated
   *  transactions. Pairs with `DELETE /api/imports/batches/{batch_id}`.
   *
   *  Phase 9: previously the upload history rendered a View button
   *  only — no way to undo a mistaken upload. We add this method on
   *  the same singleton so the 401-token-refresh interceptor we use
   *  everywhere else covers deletes too (no special-case handling).
   *
   *  Returns nothing on success (the BE responds with 204 No Content
   *  via the goals/accounts pattern). The FE surfaces the failure
   *  path on the caller side via the rejected AxiosError. */
  deleteBatch: async (batchId: number): Promise<void> => {
    await api.delete(`/api/imports/batches/${batchId}`)
  },

  // Phase 11 — categories (for activity-page filter + auto-categorize).
  listCategories: async (): Promise<Category[]> => {
    const response = await api.get('/api/categories/')
    return response.data
  },

  createCategory: async (payload: {
    name: string
    description?: string | null
    icon?: string | null
    color?: string | null
  }): Promise<Category> => {
    const response = await api.post('/api/categories/', payload)
    return response.data
  },

  // Atlas Phase 2 — Domain breakdown endpoints.
  getIncomeBreakdown: async (fromDate: string, toDate: string): Promise<IncomeBreakdownResponse> => {
    const response = await api.get('/api/dashboard/income-breakdown', {
      params: { from_date: fromDate, to_date: toDate },
    })
    return response.data
  },

  getExpenseBreakdown: async (fromDate: string, toDate: string): Promise<ExpenseBreakdownResponse> => {
    const response = await api.get('/api/dashboard/expense-breakdown', {
      params: { from_date: fromDate, to_date: toDate },
    })
    return response.data
  },

  getDebtsSummary: async (): Promise<DebtsSummaryResponse> => {
    const response = await api.get('/api/debts/summary')
    return response.data
  },

  getDashboardInsights: async (): Promise<InsightsResponse> => {
    const response = await api.get('/api/dashboard/insights')
    return response.data
  },

  // Phase 3 — Alerts: anomalies + upcoming bills
  getDashboardAnomalies: async (): Promise<AnomaliesResponse> => {
    const response = await api.get('/api/dashboard/anomalies')
    return response.data
  },

  getDashboardUpcomingBills: async (): Promise<UpcomingBillsResponse> => {
    const response = await api.get('/api/dashboard/upcoming-bills')
    return response.data
  },

  // Phase 4 — Recommendation approval workflow
  listRecommendations: async (params?: {
    status?: string
    limit?: number
    offset?: number
  }): Promise<RecommendationLogListResponse> => {
    const cleaned: Record<string, unknown> = {}
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null && v !== '') cleaned[k] = v
      }
    }
    const response = await api.get('/api/recommendations/', { params: cleaned })
    return response.data
  },

  createRecommendation: async (
    body: RecommendationLogCreate,
  ): Promise<RecommendationLogItem> => {
    const response = await api.post('/api/recommendations/', body)
    return response.data
  },

  takeRecommendationAction: async (
    id: number,
    action: 'approve' | 'deny' | 'dismiss',
  ): Promise<RecommendationLogItem> => {
    const response = await api.post(`/api/recommendations/${id}/action`, { action })
    return response.data
  },

  getRecommendationStats: async (): Promise<RecommendationStatsResponse> => {
    const response = await api.get('/api/recommendations/stats')
    return response.data
  },

  // Phase 5 — AI Copilot: trigger smart recommendation generation.
  generateSmartRecommendations: async (): Promise<{ inserted: number }> => {
    const response = await api.post('/api/recommendations/generate')
    return response.data
  },

  // Atlas Phase 1 — Budget CRUD.
  listBudgets: async (params?: { period?: string }): Promise<Budget[]> => {
    const cleaned: Record<string, string> = {}
    if (params?.period) cleaned.period = params.period
    const response = await api.get('/api/budgets/', { params: cleaned })
    return response.data
  },

  createBudget: async (payload: {
    category_id?: number | null
    amount: number
    period: string
  }): Promise<Budget> => {
    const response = await api.post('/api/budgets/', payload)
    return response.data
  },

  updateBudget: async (
    id: number,
    patch: Partial<{ amount: number; period: string; category_id: number | null }>,
  ): Promise<Budget> => {
    const response = await api.put(`/api/budgets/${id}`, patch)
    return response.data
  },

  deleteBudget: async (id: number): Promise<void> => {
    await api.delete(`/api/budgets/${id}`)
  },

  getBudgetStatus: async (period: string): Promise<BudgetStatusResponse> => {
    const response = await api.get('/api/budgets/status', { params: { period } })
    return response.data
  },

  // Phase 8 — multi-goal financial planning.
  listGoals: async (): Promise<Goal[]> => {
    const response = await api.get('/api/goals/')
    return response.data
  },

  createGoal: async (payload: {
    name: string
    target_amount: number
    target_date?: string | null
    horizon_years?: number | null
    priority?: number
    notes?: string | null
  }): Promise<Goal> => {
    const response = await api.post('/api/goals/', payload)
    return response.data
  },

  /** Partial update — pairs with `PUT /api/goals/{id}`. Only declared
   *  fields on the BE's ``GoalUpdate`` schema are accepted; unknown keys
   *  are silently dropped server-side (Phase 8 whitelist contract).
   *  ``is_archived=true`` un-archives a previously soft-deleted row. */
  updateGoal: async (
    id: number,
    patch: Partial<{
      name: string
      target_amount: number
      target_date: string | null
      horizon_years: number | null
      priority: number
      notes: string | null
      is_archived: boolean
    }>,
  ): Promise<Goal> => {
    const response = await api.put(`/api/goals/${id}`, patch)
    return response.data
  },

  /** Soft-archive — pairs with `DELETE /api/goals/{id}`. The server flips
   *  ``is_archived=True`` (preserves any future FK-bearing references);
   *  the row stops appearing in ``listGoals`` and can be reactivated via
   *  ``updateGoal(..., { is_archived: false })``. */
  deleteGoal: async (id: number): Promise<void> => {
    await api.delete(`/api/goals/${id}`)
  },

  // Phase 24 + 27 — merchant rules (DB-backed substring categorizer
  // keywords + provenance + CSV import/export). Mirrors
  // ``GET/POST/PUT/DELETE /api/merchant-rules/*`` on the BE. The
  // Settings Merchant Rules card calls these so the user can
  // add/remove/disable keywords without redeploying the BE.
  listMerchantRules: async (params?: {
    category_id?: number
    /** Phase 27 — filter to one provenance ('system' | 'manual' |
     *  'tag-rule' | 'llm' | 'imported'); combined with the other
     *  filters via AND. */
    source?: MerchantRuleSource
    include_archived?: boolean
  }): Promise<MerchantRule[]> => {
    const cleaned: Record<string, unknown> = {}
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null) cleaned[k] = v
      }
    }
    const response = await api.get('/api/merchant-rules/', { params: cleaned })
    return response.data
  },

  createMerchantRule: async (payload: {
    category_id: number
    /** Keyword pattern, always uppercased + stripped server-side. */
    keyword: string
    /** Defaults to 100 on the BE (LAST per category); the FE omits
     *  this for the common "add rule" flow so the rule falls to
     *  the bottom of the scan order without displacing system rules. */
    priority?: number
    /** Phase 27 — provenance. Server defaults to 'manual' when
     *  omitted; the Activity page's Promote-to-Rule flow passes
     *  'tag-rule'; an import flow passes 'imported'. The BE rejects
     *  'system' with a 400 because only the boot-time seed may
     *  stamp that value. */
    source?: MerchantRuleSource
  }): Promise<MerchantRule> => {
    const response = await api.post('/api/merchant-rules/', payload)
    return response.data
  },

  updateMerchantRule: async (
    id: number,
    patch: Partial<{
      category_id: number
      keyword: string
      priority: number
      is_archived: boolean
    }>,
  ): Promise<MerchantRule> => {
    const response = await api.put(`/api/merchant-rules/${id}`, patch)
    return response.data
  },

  deleteMerchantRule: async (id: number): Promise<void> => {
    await api.delete(`/api/merchant-rules/${id}`)
  },

  /** CSV download of every merchant rule — pairs with
   *  ``GET /api/merchant-rules/export``. Phase 27. Returns a
   *  ``Blob`` + a filename so the caller can either pipe to
   *  ``URL.createObjectURL`` (the Settings page's Export button)
   *  or write-then-parse-then-re-import (a future test harness).
   *  The BE always includes archived rules by default; pass
   *  ``includeArchived: false`` for a "live rules only" export
   *  (mirrors the same Query flag the BE exposes). */
  exportMerchantRules: async (
    includeArchived: boolean = true,
  ): Promise<{ blob: Blob; filename: string }> => {
    const params: Record<string, unknown> = { include_archived: includeArchived }
    const response = await api.get('/api/merchant-rules/export', {
      params,
      responseType: 'blob',
    })
    // Filename comes from Content-Disposition so a future BE
    // rename (e.g. backend version suffix) lands automatically.
    const cd = (response.headers['content-disposition'] as string) ?? ''
    const match = cd.match(/filename\s*=\s*"?([^";]+)"?/i)
    const filename = match ? match[1] : 'merchant-rules.csv'
    return { blob: response.data as Blob, filename }
  },

  /** Multipart CSV upload — pairs with ``POST /api/merchant-rules/import``.
   *  Returns the per-row summary so the Settings page can render
   *  "Imported N — K already existed — M had errors" inline without
   *  a follow-up GET. The BE silently OVERRIDES any ``source``
   *  column in the CSV to ``'imported'`` on every row (audit-trail
   *  correctness; provenance is the import event itself). */
  importMerchantRules: async (
    file: File,
  ): Promise<MerchantRuleImportResult> => {
    const form = new FormData()
    form.append('file', file)
    const response = await api.post(
      '/api/merchant-rules/import',
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
    return response.data
  },

  /** Diagnostic — returns ``{active, archived, by_source}`` so the
   *  Settings card can render a small footer ("117 active, 2
   *  archived") plus a per-provenance breakdown bucket for the
   *  Source column section header. Locks the Phase 27 shape
   *  (pre-Phase 27 was just ``{active, archived}``). */
  reloadMerchantRules: async (): Promise<{
    active: number
    archived: number
    /** Phase 27 — ``by_source[source_name]`` => ``{active, archived}``.
     *  ``source_name`` is one of: 'system', 'manual', 'tag-rule',
     *  'llm', 'imported'. */
    by_source?: Record<string, { active: number; archived: number }>
  }> => {
    const response = await api.post('/api/merchant-rules/reload')
    return response.data
  },

  // Accounts — reconcile balances safety valve.
  reconcileBalances: async (): Promise<{ reconciled: number }> => {
    const response = await api.post('/api/accounts/reconcile')
    return response.data
  },

  // Data management — nuke-orbit.
  deleteAllData: async (): Promise<{
    deleted_transactions: number
    deleted_import_batches: number
    deleted_budgets: number
    deleted_goals: number
    deleted_accounts: number
  }> => {
    const response = await api.delete('/api/data/')
    return response.data
  },

  // Phase 8: direct /health probe used by monitoring/uptime checks.
  health: async (): Promise<{ status: string }> => {
    const response = await api.get('/health')
    return response.data
  },

  /**
   * Phase 9 analyst-ratings lookup. Wraps
   * ``GET /api/analyst-ratings/{ticker}`` which in turn fans out to
   * Finnhub's free ``/stock/recommendation`` and ``/stock/price-target``
   * endpoints via a 24-hour in-memory TTLCache on the BE.
   *
   * Pass an uppercased, alphanumeric ticker (e.g. ``'AAPL'``); the BE
   * uppercases case-insensitively, but lowercased clients pay a
   * separate cache slot per variation. We normalise here so the FE
   * never accidentally explodes the BE cache.
   *
   * Response shape:
   *   { symbol: 'AAPL',
   *     recommendation_trends: [
   *       { period: '2025-05', strongBuy: 12, buy: 18, hold: 7,
   *         sell: 1, strongSell: 0 }, ... ],
   *     price_target: { targetMean: 232.10, targetMedian: 230.00,
   *                     targetHigh: 280.00, targetLow: 165.00 } }
   *
   * On a 502 (Finnhub upstream error) or 500 (missing API key) the
   * call rejects with the AxiosError so the FE surfaces a friendly
   * retry banner.
   */
  getAnalystRatings: async (
    ticker: string,
  ): Promise<AnalystRatingsData> => {
    const symbol = ticker.trim().toUpperCase()
    const response = await api.get(`/api/analyst-ratings/${encodeURIComponent(symbol)}`)
    return response.data
  },

  /**
   * Phase 42 -- batch analyst-ratings fetch for the /portfolio
   * coverage card + per-row chips. Wraps ``POST
   * /api/analyst-ratings/batch``.
   *
   * ``symbols`` is dedup'd + uppercased client-side BEFORE the POST
   * so the request body is the smallest possible payload. The BE
   * also dedups (server-side is the source of truth, but the FE
   * filter prevents an O(N) duplicated body for hot portfolios).
   *
   * Partial-success contract: 200 even if some tickers return 502
   * upstream (the FE renders an "Uncovered" chip for those rows).
   * Only WHOLE-batch errors (missing API key on the BE = 500,
   * oversized list = 422) reject the promise so the FE shows the
   * actual cause, not a misleading per-row error.
   */
  getBatchAnalystRatings: async (
    symbols: string[],
  ): Promise<{
    results: Array<{
      symbol: string
      status: 'ok' | 'error'
      /** Same shape as ``getAnalystRatings`` payload -- shared cache.
       *  Reuses the shared ``AnalystRatingsData`` interface (defined at
       *  module top) so the per-row ``data`` field NEVER drifts from
       *  the single-ticker endpoint's return type -- the previous
       *  ``data?: unknown`` accumulator forced TS2322 at the return
       *  boundary because the two shapes were declared separately. */
      data?: AnalystRatingsData | null
      /** User-readable detail for ``status='error'`` rows. */
      error?: string | null
    }>
  }> => {
    // Dedup + uppercase BEFORE the POST -- saves bytes on the wire +
    // matches the BE's server-side dedup as a defence-in-depth.
    const seen = new Set<string>()
    const cleaned: string[] = []
    for (const raw of symbols) {
      if (typeof raw !== 'string') continue
      const sym = raw.trim().toUpperCase()
      if (!sym || seen.has(sym)) continue
      seen.add(sym)
      cleaned.push(sym)
    }
    if (cleaned.length === 0) return { results: [] }
    // Server-side cap is 50; chunk if a future UI sends more.
    // Today's /portfolio only ever sends top-10 so this branch is
    // never hit, but defensible in case a Recommendations page later
    // asks for "every ticker in the watchlist" (50+).
    const chunkSize = 50
    const allResults: Array<{
      symbol: string
      status: 'ok' | 'error'
      data?: AnalystRatingsData | null
      error?: string | null
    }> = []
    for (let i = 0; i < cleaned.length; i += chunkSize) {
      const chunk = cleaned.slice(i, i + chunkSize)
      const response = await api.post('/api/analyst-ratings/batch', { tickers: chunk })
      allResults.push(...(response.data.results ?? []))
    }
    return { results: allResults }
  },

  // Phase 29 — duplicate detection (Settings → "Clean up duplicates").
  // L1-only (substring) and L1+L2 (semantic) variants are exposed as
  // two methods so the FE's wizard can render the L1 results
  // immediately (fast, offline) and layer L2 on top as the user
  // opts in. Mirrors `GET /api/merchant-rules/duplicates` and
  // `POST /api/merchant-rules/duplicates/llm` on the BE.
  findDuplicateMerchantRules: async (params?: {
    /** When true, layer the L2 (LLM semantic) pass on top of the
     *  L1 (substring) pass. Requires Ollama running on the BE
     *  host; on transport failure the BE returns the L1-only
     *  payload with ``l2_status='offline'`` so the FE can render
     *  a partial-success banner. */
    includeLlm?: boolean
  }): Promise<{
    groups: Array<{
      /** The rule to KEEP. */
      canonical: { id: number; keyword: string }
      /** The rules the Apply action will soft-delete. */
      candidates: Array<{
        id: number
        keyword: string
        /** 'substring' (L1, deterministic) or 'llm' (L2, semantic). */
        method: 'substring' | 'llm'
        /** 0.0-1.0; substring pairs are 1.0. */
        confidence: number
        rationale: string
      }>
    }>
    /** L1 hit count (substring pairs). */
    l1_count: number
    /** L2 hit count (LLM semantic pairs). 0 when Ollama is offline. */
    l2_count: number
    /** Phase 29 follow-up — tells the FE the OUTCOME of the L2
     *  pass so it can render an honest partial-success banner.
     *  Without this field the FE can't distinguish "L2 returned
     *  0 pairs" from "L2 never ran" (both surface as
     *  ``l2_count=0``), which was the silent-failure gap surfaced
     *  by the Phase 29 review. The four possible values:
     *  - 'ok' — L2 ran; ``l2_count`` is the number of pairs flagged.
     *  - 'offline' — Ollama unreachable (ConnectError/Timeout).
     *  - 'malformed' — Ollama returned non-JSON (JSON-mode ignored).
     *  - 'skipped' — the user didn't opt in (includeLlm=false). */
    l2_status: 'ok' | 'offline' | 'malformed' | 'skipped'
  }> => {
    if (params?.includeLlm) {
      const response = await api.post('/api/merchant-rules/duplicates/llm')
      return response.data
    }
    const response = await api.get('/api/merchant-rules/duplicates')
    return response.data
  },

  /** Soft-delete a batch of candidate rules (the Apply action in
   *  the dedup wizard). Pairs with `POST
   *  /api/merchant-rules/duplicates/apply`. The canonical of
   *  every active dedup group is NEVER touched — the route
   *  rejects mixed canonical+candidate ids with HTTP 400.
   *
   *  Idempotent: re-firing Apply on an already-archived row
   *  increments ``skipped`` instead of ``archived`` so the wizard
   *  can recover from a flaky network without double-archiving.
   *  An empty ``candidateIds`` is a no-op (returns
   *  ``{archived: 0, skipped: 0}`` with 200, never a 422 — a
   *  no-op click during a state-sync round-trip is a valid
   *  user action). */
  applyDuplicateMerchantRules: async (
    candidateIds: number[],
  ): Promise<{ archived: number; skipped: number }> => {
    const response = await api.post(
      '/api/merchant-rules/duplicates/apply',
      { candidate_ids: candidateIds },
    )
    return response.data
  },

  // Phase 30 — AI Finance Assistant chat. Pairs with
  // ``POST /api/assistant/chat`` on the BE. The orchestrator loads
  // SOUL.md + STYLE.md into the system prompt, asks the local Ollama
  // LLM to pick a tool, dispatches, then generates a natural-
  // language reply. Blocking v1 (no SSE — streaming is 30e).
  //
  // If Ollama is unreachable, the BE returns ``status='offline'``
  // with a graceful fallback reply (no 500) so the FE can render an
  // offline banner instead of an error toast.
  //
  // Phase 30c — ``conversationId`` is optional. When omitted, the BE
  // creates a new conversation and returns its id. When provided, the
  // message is appended to the existing conversation for multi-turn
  // context. The FE stores the id and sends it back on each turn.
  assistantChat: async (
    message: string,
    conversationId?: number | null,
  ): Promise<{
    reply: string
    tool_used: string | null
    tool_result: Record<string, unknown> | null
    follow_ups: string[]
    status: 'ok' | 'offline' | 'error'
    conversation_id: number | null
    conversation_title: string | null
  }> => {
    const response = await api.post('/api/assistant/chat', {
      message,
      conversation_id: conversationId ?? null,
    })
    return response.data
  },

  // Phase 30c — List the user's conversations (newest first).
  // Returns conversations WITHOUT messages; the sidebar only needs
  // the title + timestamps. Messages are loaded via getConversation.
  listAssistantConversations: async (): Promise<
    Array<{
      id: number
      title: string
      created_at: string
      updated_at: string
      messages: AssistantMessage[]
    }>
  > => {
    const response = await api.get('/api/assistant/conversations')
    return response.data
  },

  // Phase 30e — SSE streaming chat. Uses fetch + ReadableStream
  // (not EventSource, which doesn't support POST bodies). The
  // caller receives an async generator of SSE events:
  //   { event: 'conversation', data: {...} }
  //   { event: 'thinking', data: {} }
  //   { event: 'tool_call', data: { tool, params } }
  //   { event: 'tool_result', data: { tool, result } }
  //   { event: 'reply_chunk', data: { chunk } }
  //   { event: 'done', data: { reply, tool_used, ... } }
  //
  // The caller is responsible for parsing the SSE stream. This
  // method handles auth (Bearer token) + the POST body.
  assistantChatStream: async function* (
    message: string,
    conversationId?: number | null,
  ): AsyncGenerator<{ event: string; data: Record<string, unknown> }> {
    const token = getStoredToken()
    const baseURL =
      typeof window === 'undefined'
        ? apiBaseUrl.replace('localhost', '127.0.0.1')
        : apiBaseUrl
    const response = await fetch(`${baseURL}/api/assistant/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      credentials: 'include',
      body: JSON.stringify({
        message,
        conversation_id: conversationId ?? null,
      }),
    })
    if (!response.ok) {
      throw new Error(`Stream request failed: ${response.status}`)
    }
    const reader = response.body?.getReader()
    if (!reader) throw new Error('No response body')
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // SSE events are separated by \n\n
      const events = buffer.split('\n\n')
      buffer = events.pop() || ''
      for (const evt of events) {
        const lines = evt.split('\n')
        let eventType = 'message'
        let dataStr = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) eventType = line.slice(7)
          else if (line.startsWith('data: ')) dataStr = line.slice(6)
        }
        if (dataStr) {
          try {
            const data = JSON.parse(dataStr)
            yield { event: eventType, data }
          } catch {
            // Skip malformed events
          }
        }
      }
    }
  },

  // Phase 30c — Fetch a single conversation with all its messages.
  // Used when the user clicks a past conversation in the sidebar.
  // Phase 39 — Portfolio Holdings.
  /** Import a Fidelity Portfolio Positions CSV. Pairs with
   *  ``POST /api/holdings/import``. Auto-creates accounts and
   *  upserts holdings. */
  importPortfolio: async (file: File): Promise<PortfolioImportResult> => {
    const form = new FormData()
    form.append('file', file)
    const response = await api.post('/api/holdings/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  },

  /** List all holdings for the current user. */
  listHoldings: async (): Promise<Holding[]> => {
    const response = await api.get('/api/holdings/')
    return response.data
  },

  /** Fetch live prices from Finnhub and return updated holdings. */
  refreshPrices: async (): Promise<HoldingsRefreshResult> => {
    const response = await api.post('/api/holdings/refresh-prices')
    return response.data
  },

  /** Phase 41 — manually add a single holding. Pairs with
   *  `POST /api/holdings/`. Auto-creates a new portfolio account when
   *  `account_name` is provided (one-click portfolio bootstrapping);
   *  resolves an existing account by id when `account_id` is set.
   *  On the 400 / 404 / 201 contract the FE surfaces errors via the
   *  AxiosError's `response.data.detail` message. */
  createHolding: async (payload: HoldingManualCreate): Promise<Holding> => {
    const response = await api.post('/api/holdings/', payload)
    return response.data
  },

  /** Phase 47 — partial-update one position. Pairs with
   *  ``PUT /api/holdings/{id}``. Multi-field patch in one round-trip;
   *  the BE's ``model_dump(exclude_unset=True)`` leaves any field
   *  omitted from ``patch`` alone on the underlying row. The user's
   *  primary use case is "I just bought 15 more shares" — the FE's
   *  Edit modal just sends ``{quantity: <new>}`` and the BE
   *  auto-derives ``current_value = last_price * quantity`` server-
   *  side (Q5 hotfix: only when quantity is in the patch; a single-
   *  field price edit does NOT auto-derive). */
  updateHolding: async (id: number, patch: Partial<HoldingUpdate>): Promise<Holding> => {
    const response = await api.put(`/api/holdings/${id}`, patch)
    return response.data
  },

  /** Phase 47 — hard-delete one position. Pairs with
   *  ``DELETE /api/holdings/{id}``. Returns void; the BE responds
   *  with 204 No Content (RFC 9110 §15.3.5: empty body). The FE's
   *  Edit / Delete modal flow calls this followed by ``loadData()``
   *  so the /portfolio aggregate refetches and the user sees the
   *  row gone. Cross-user isolation: 404 from the BE if the holding
   *  belongs to another user — but the FE never sees another
   *  user's id (it only renders ids from its own ``listHoldings()``)
   *  so the only 404 branch the FE can hit is the typo branch. */
  deleteHolding: async (id: number): Promise<void> => {
    await api.delete(`/api/holdings/${id}`)
  },

  getAssistantConversation: async (
    conversationId: number,
  ): Promise<{
    id: number
    title: string
    created_at: string
    updated_at: string
    messages: AssistantMessage[]
  }> => {
    const response = await api.get(
      `/api/assistant/conversations/${conversationId}`,
    )
    return response.data
  },
}

export default api
