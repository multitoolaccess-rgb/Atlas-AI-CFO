'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Wallet,
  RefreshCw,
  Upload,
  Loader2,
  Landmark,
  FileSpreadsheet,
  Plus,
  X,
  AlertCircle,
  Sparkles,
  ArrowUpRight,
  ArrowDownRight,
  TrendingUp,
  ExternalLink,
  // Phase 47 — per-row Edit + Delete affordances on /portfolio's
  // holdings table. Pencil mirrors the existing chip aesthetic;
  // Trash2 reads as "destructive" without the surrounding red box
  // the old X icon implied.
  Pencil,
  Trash2,
} from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'
import { AtlasFilterProvider } from '@/components/ui/AtlasFilterContext'
import FloatingTimeRangeBar from '@/components/ui/FloatingTimeRangeBar'
import HeroSummary from '@/components/dashboard/HeroSummary'
import ChartDonut, { type DonutSliceConfig } from '@/components/charts/ChartDonut'
import AnimatedRadialProgress from '@/components/charts/AnimatedRadialProgress'
import TiltCard from '@/components/ui/TiltCard'
import Button from '@/components/ui/Button'
import ErrorBanner from '@/components/ui/ErrorBanner'
import EmptyState from '@/components/ui/EmptyState'
import PageHeader from '@/components/ui/PageHeader'
import { CountUp, Input, Select, Modal } from '@/components/ui'
import {
  rulesService,
  type Account,
  type DashboardSummary,
  type Holding,
  type HoldingManualCreate,
  type HoldingUpdate,
  type Profile,
} from '@/lib/api'
import { classifyErrorMessage } from '@/lib/errors'
import { useThemeColors } from '@/lib/themeColors'
import { onDataRefresh } from '@/lib/dataRefresh'
import {
  DEFAULT_REFRESH_MINUTES,
  getAutoRefreshMinutes,
  MAX_REFRESH_MINUTES,
  MIN_REFRESH_MINUTES,
  setAutoRefreshMinutes,
} from '@/lib/holdingsPrefs'

/** Phase 41 — asset-class options for the manual holding form.
 *  Mirrors the strings the Fidelity / Robinhood parsers stamp on
 *  a row so the new row visually matches next to an import sibling. */
const HOLDING_TYPE_OPTIONS = [
  { value: 'Stock', label: 'Stock' },
  { value: 'ETF', label: 'ETF' },
  { value: 'Mutual Fund', label: 'Mutual Fund' },
  { value: 'Crypto', label: 'Crypto' },
  { value: 'Cash', label: 'Cash' },
  { value: 'Bond', label: 'Bond' },
  { value: 'Other', label: 'Other' },
] as const



/** Phase 41 — concentration risk thresholds (per single holding).
 *  >10% in a single ticker = yellow "review your allocation" tint;
 *  >20% = red "you are concentrated" tint. The %s are deliberately
 *  hand-picked (not derived from the user's profile) so the warning
 *  tone is uniform across users. */
const CONCENTRATION_WARN_PCT = 10
const CONCENTRATION_DANGER_PCT = 20

/** Account palette keys — indexes into DASHBOARD_COLORS via tc[account_N].
 *  Theme-aware: deep shades in light mode, vivid brights in dark mode. */
const ACCOUNT_KEYS = ['account_0', 'account_1', 'account_2', 'account_3', 'account_4', 'account_5'] as const

export default function PortfolioPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)
  const [importing, setImporting] = useState(false)
  const [importStatus, setImportStatus] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [priceWarning, setPriceWarning] = useState<string | null>(null)
  const [pricesAvailable, setPricesAvailable] = useState(false)
  // ---- Phase 48 — auto-refresh state ----
  // ``autoRefreshMinutes``: COMMITTED minutes between automatic
  // refreshes (0 = off, default DEFAULT_REFRESH_MINUTES, clamped to
  // [0, MAX_REFRESH_MINUTES] on commit). Persisted to localStorage so
  // the user doesn't re-pick on every page load. Drives the auto-
  // refresh setInterval + the countdown display.
  // ``autoRefreshMinutesDraft``: LOCAL string state for the timer
  // input. Decouples the input's "what the user is typing" from the
  // committed number so a transient ``1`` or ``0`` doesn't snap to
  // ``5`` (clamp floor) or ``off`` (0 sentinel) mid-keystroke. The
  // input's onChange writes here; onBlur commits via
  // setAutoRefreshMinutes which clamps + persists + returns the
  // clamped value back to the React state mirror.
  // ``lastRefreshedAt``: Date.now() ms of the most recent successful
  // refresh (manual OR auto). Drives the countdown display + the
  // "Last refreshed 14m ago" badge. ``null`` until the first
  // successful refresh lands.
  // ``now``: 1-second ticker that re-renders the component so the
  // countdown + "last refreshed" label stay live. Skipped when the
  // loop is off so an "off" user pays zero re-render cost.
  const [autoRefreshMinutes, setAutoRefreshMinutesState] = useState<number>(
    DEFAULT_REFRESH_MINUTES
  )
  const [autoRefreshMinutesDraft, setAutoRefreshMinutesDraft] =
    useState<string>(String(DEFAULT_REFRESH_MINUTES))
  const [lastRefreshedAt, setLastRefreshedAt] = useState<number | null>(null)
  const [now, setNow] = useState<number>(() => Date.now())
  // Ref-mirror of ``refreshing`` state so the auto-refresh tick
  // closure can read the latest in-flight flag without re-creating
  // the setInterval on every manual refresh (which would happen if
  // ``refreshing`` were a dep of the auto-refresh useEffect, turning
  // a single setInterval into a clear+create cycle per click).
  const refreshingRef = useRef(false)

  // Phase 41 — manual Add Holding form state.
  const [showAddForm, setShowAddForm] = useState(false)
  const [addAccountMode, setAddAccountMode] = useState<'existing' | 'new'>('existing')
  const [addAccountId, setAddAccountId] = useState<number | ''>('')
  const [addAccountName, setAddAccountName] = useState('')
  const [addSymbol, setAddSymbol] = useState('')
  const [addDescription, setAddDescription] = useState('')
  const [addQuantity, setAddQuantity] = useState('')
  const [addLastPrice, setAddLastPrice] = useState('')
  const [addCostBasis, setAddCostBasis] = useState('')
  const [addType, setAddType] = useState<string>('Stock')
  const [addSubmitting, setAddSubmitting] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)

  // Phase 47 — Edit modal state (separate from Add so the Cancel
  // dance doesn't clobber the Add form mid-flight). Mirrors the Add
  // form's field set (minus the Account picker — Edit doesn't move a
  // holding across accounts, that's a future "Transfer" affordance).
  const [editHolding, setEditHolding] = useState<Holding | null>(null)
  const [editSymbol, setEditSymbol] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editQuantity, setEditQuantity] = useState('')
  const [editLastPrice, setEditLastPrice] = useState('')
  const [editCostBasis, setEditCostBasis] = useState('')
  const [editType, setEditType] = useState<string>('Stock')
  const [editSubmitting, setEditSubmitting] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)

  // Phase 47 — Delete confirm modal state. Holds the row whose
  // Delete button was clicked so the confirm step can echo the
  // position summary ("Delete AAPL, 10 shares @ $200?") rather
  // than a generic "Are you sure?".
  const [deleteHoldingRow, setDeleteHoldingRow] = useState<Holding | null>(null)
  const [deleteSubmitting, setDeleteSubmitting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  // Phase 41 — Analyze drawer state (one drawer at a time + in-memory
  // per-ticker cache so flipping between rows doesn't re-hit Finnhub).
  const [analyzingHolding, setAnalyzingHolding] = useState<Holding | null>(null)
  const [ratingsByTicker, setRatingsByTicker] = useState<
    Record<
      string,
      | { state: 'loading' }
      | { state: 'ok'; data: Awaited<ReturnType<typeof rulesService.getAnalystRatings>> }
      | { state: 'error'; message: string }
    >
  >({})

  // Phase 42 — whole-batch analyst coverage error. Distinct from
  // per-ticker `ratingsByTicker[symbol].state='error'`: this surfaces
  // a banner when the BE 500s or the request 422s (whole-batch failure
  // modes), while per-ticker errors render as "Uncovered" chips. The
  // distinction matters for triage — a banner says "service is down",
  // a chip says "this ticker is uncovered".
  const [analystCoverageError, setAnalystCoverageError] = useState<string | null>(null)

  // Phase 49 (analyst-coverage loading-state fix) — flips true
  // AFTER the batch fetch resolves (either .then() OR .catch()).
  // Without this flag the "Loading coverage for N holdings…" footer
  // stayed visible forever whenever every ticker returned a
  // per-row error (e.g. all 502s from Finnhub, all invalid tickers):
  // ``analystCoverageAggregate.covered === 0`` and
  // ``analystCoverageError === null`` were both permanently true,
  // so the loading branch of the render kept firing even though
  // the call had long since resolved. With this flag the "Loading…"
  // copy is scoped to the genuine in-flight window; after the call
  // settles we render an honest "No coverage available for your
  // N tickers" footer instead so the user knows the system tried
  // and the row's chips already carry the per-ticker error detail.
  const [analystCoverageLoaded, setAnalystCoverageLoaded] = useState(false)

  useEffect(() => onDataRefresh(() => setRetryCount((c) => c + 1)), [])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [s, a, h, p] = await Promise.all([
        rulesService.getDashboardSummary(),
        rulesService.listAccounts(),
        rulesService.listHoldings(),
        rulesService.getProfile().catch(() => null),
      ])
      setSummary(s)
      setAccounts(a)
      setHoldings(h)
      setProfile(p)
      // Detect whether any row carries live-price data from a
      // previous refresh — drives the Top Movers visibility toggle.
      setPricesAvailable(h.some((row) => row.live_price != null))
    } catch (err: unknown) {
      setError(classifyErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData, retryCount])

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    setImportStatus(null)
    setError(null)
    try {
      const result = await rulesService.importPortfolio(file)
      setImportStatus(
        `Imported ${result.holdings_count} positions across ${result.account_ids.length} accounts (total: ${result.total_value.toLocaleString('en-US', { minimumFractionDigits: 2 })})${result.accounts_created > 0 ? ` — ${result.accounts_created} new account(s) created` : ''}`
      )
      await loadData()
    } catch (err: unknown) {
      setError(classifyErrorMessage(err))
    } finally {
      setImporting(false)
      e.target.value = ''
    }
  }

  // Phase 48 — extracted refresh core so manual + auto-refresh share
  // the same try/catch/finally + the same lastRefreshedAt stamp.
  // ``kind`` toggles (a) the success-banner copy so the user can
  // tell at a glance which path fired, and (b) the error-handling
  // policy (manual errors surface via ErrorBanner; auto errors
  // stay quiet in the console so a flaky upstream doesn't spam an
  // ErrorBanner every hour).
  //
  // The useCallback has empty deps so the function identity is
  // stable — a non-stable performRefresh would cause the auto-
  // refresh useEffect to re-run on every render, which would
  // clear + re-create the setInterval on every parent re-render.
  const performRefresh = useCallback(async (kind: 'manual' | 'auto') => {
    if (refreshingRef.current) return  // already in flight; don't double-fire
    refreshingRef.current = true
    setRefreshing(true)
    setPriceWarning(null)
    try {
      const result = await rulesService.refreshPrices()
      if (result.warning) setPriceWarning(result.warning)
      if (result.holdings?.length > 0) {
        setHoldings(result.holdings)
        setPricesAvailable(true)
      }
      setImportStatus(
        kind === 'auto'
          ? `Auto-refresh: prices updated for ${result.prices_updated} symbol(s).`
          : `Prices updated for ${result.prices_updated} symbol(s).`
      )
      setLastRefreshedAt(Date.now())
    } catch (err: unknown) {
      if (kind === 'manual') {
        setError(classifyErrorMessage(err))
      } else {
        // Auto-refresh errors stay in the console only — a flaky
        // upstream would otherwise spam an ErrorBanner every hour
        // and bury real load errors. The user can still see the
        // "Last refreshed" badge stays stale (no update).
        // eslint-disable-next-line no-console
        console.warn('[portfolio] auto-refresh failed:', err)
      }
    } finally {
      refreshingRef.current = false
      setRefreshing(false)
    }
  }, [])

  const handleRefresh = useCallback(() => performRefresh('manual'), [performRefresh])

  // ---- Phase 48 — auto-refresh lifecycle effects ----

  // Read the persisted auto-refresh preference on mount so the
  // timer input reflects the user's last value (not always the
  // default). One-shot effect; subsequent changes are handled by
  // the input's onBlur which calls setAutoRefreshMinutes (clamps +
  // writes localStorage) and then syncs BOTH the committed number
  // state and the draft string so the input + the auto-refresh
  // loop agree on the same value.
  useEffect(() => {
    const m = getAutoRefreshMinutes()
    setAutoRefreshMinutesState(m)
    setAutoRefreshMinutesDraft(String(m))
  }, [])

  // 1s ticker for the "Next refresh in MM:SS" countdown. Skipped
  // when the loop is off (no countdown needed) so an off-user pays
  // zero re-render cost — important because the countdown would
  // otherwise force the entire page to re-render every second.
  useEffect(() => {
    if (autoRefreshMinutes === 0) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [autoRefreshMinutes])

  // Auto-refresh loop. setInterval re-fires every
  // ``autoRefreshMinutes`` minutes. The tick skips when:
  //   - the tab is hidden (saves upstream quota — no use
  //     refreshing prices the user can't see),
  //   - a manual refresh is already in flight (avoid double-fire;
  //     the ref mirrors refreshing state without making it a dep),
  //   - the last refresh was < 60s ago (rate-limit protection:
  //     user toggles timer 60→5 while a manual refresh just
  //     landed, the next auto tick would fire almost immediately
  //     without this gate).
  //
  // ``lastRefreshedAt`` IS in the deps so a successful refresh
  // resets the interval from "now" (otherwise the next tick
  // could fire arbitrarily soon after the just-completed one).
  // ``holdings.length`` is in the deps so the interval tears
  // down when the user has no portfolio to refresh.
  useEffect(() => {
    if (autoRefreshMinutes === 0) return
    if (typeof window === 'undefined') return
    if (holdings.length === 0) return

    const tick = async () => {
      if (document.hidden) return
      if (refreshingRef.current) return
      if (lastRefreshedAt && Date.now() - lastRefreshedAt < 60_000) return
      await performRefresh('auto')
    }

    const intervalMs = autoRefreshMinutes * 60 * 1000
    const handle = setInterval(tick, intervalMs)
    return () => clearInterval(handle)
  }, [autoRefreshMinutes, holdings.length, performRefresh, lastRefreshedAt])

  // "Next refresh in MM:SS" countdown. Reads the 1-second ticker
  // (``now``) so the display stays live without any setInterval
  // re-render of its own. ``null`` when the loop is off OR no
  // auto-refresh has fired yet (the "off" case needs no countdown;
  // the "not fired yet" case would display a meaningless
  // "60:00 from page load" countdown).
  const nextRefreshInSec = useMemo(() => {
    if (autoRefreshMinutes === 0) return null
    if (!lastRefreshedAt) return null
    const elapsedMs = now - lastRefreshedAt
    const remainingMs = autoRefreshMinutes * 60 * 1000 - elapsedMs
    return Math.max(0, Math.ceil(remainingMs / 1000))
  }, [now, autoRefreshMinutes, lastRefreshedAt])

  // "Last refreshed 14m ago" badge next to the countdown. Same
  // null-when-no-data policy; the existing useMemo chain means
  // it recomputes once per second alongside the countdown.
  const lastRefreshedLabel = useMemo(() => {
    if (!lastRefreshedAt) return null
    const elapsedSec = Math.floor((now - lastRefreshedAt) / 1000)
    if (elapsedSec < 60) return 'just now'
    if (elapsedSec < 3600) {
      const m = Math.floor(elapsedSec / 60)
      return `${m}m ago`
    }
    const h = Math.floor(elapsedSec / 3600)
    return `${h}h ago`
  }, [now, lastRefreshedAt])

  const resetAddForm = () => {
    setAddAccountMode('existing')
    setAddAccountId('')
    setAddAccountName('')
    setAddSymbol('')
    setAddDescription('')
    setAddQuantity('')
    setAddLastPrice('')
    setAddCostBasis('')
    setAddType('Stock')
    setAddError(null)
  }

  const submitAddHolding = async (e: React.FormEvent) => {
    e.preventDefault()
    setAddSubmitting(true)
    setAddError(null)
    try {
      const qty = Number(addQuantity)
      const lastPrice = addLastPrice === '' ? null : Number(addLastPrice)
      const costBasis = addCostBasis === '' ? null : Number(addCostBasis)
      if (!Number.isFinite(qty) || qty <= 0) {
        setAddError('Quantity must be a positive number.')
        setAddSubmitting(false)
        return
      }
      const trimmedSymbol = addSymbol.trim().toUpperCase()
      if (!trimmedSymbol) {
        setAddError('Symbol is required.')
        setAddSubmitting(false)
      return
      }
      const payload: HoldingManualCreate = {
        symbol: trimmedSymbol,
        description: addDescription.trim() || undefined,
        quantity: qty,
        type: addType || undefined,
      }
      if (addAccountMode === 'existing' && addAccountId !== '') {
        payload.account_id = Number(addAccountId)
      } else if (addAccountMode === 'new' && addAccountName.trim()) {
        payload.account_name = addAccountName.trim()
      }
      if (lastPrice != null && Number.isFinite(lastPrice)) payload.last_price = lastPrice
      if (costBasis != null && Number.isFinite(costBasis)) payload.cost_basis_total = costBasis

      await rulesService.createHolding(payload)
      await loadData()
      setShowAddForm(false)
      resetAddForm()
      setImportStatus(`Added ${trimmedSymbol} to portfolio.`)
    } catch (err: any) {
      setAddError(
        err?.response?.data?.detail ?? err?.message ?? 'Failed to add holding.'
      )
    } finally {
      setAddSubmitting(false)
    }
  }

  const openAnalyze = async (h: Holding) => {
    if (!h.symbol) return
    const symbol = h.symbol.toUpperCase()
    setAnalyzingHolding(h)
    if (ratingsByTicker[symbol]) return
    setRatingsByTicker((prev) => ({ ...prev, [symbol]: { state: 'loading' } }))
    try {
      const data = await rulesService.getAnalystRatings(symbol)
      setRatingsByTicker((prev) => ({ ...prev, [symbol]: { state: 'ok', data } }))
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ?? err?.message ?? 'Failed to fetch analyst ratings.'
      setRatingsByTicker((prev) => ({ ...prev, [symbol]: { state: 'error', message: msg } }))
    }
  }

  const closeAnalyze = () => setAnalyzingHolding(null)

  // ============================================================
  // Phase 47 — Edit + Delete handlers (per-row Action column)
  // ============================================================
  // Edit mirrors the Add holding form's field set (minus the
  // Account picker — a cross-account move needs TWO account-balance
  // recomputes atomically; that's a future "Transfer" affordance,
  // not "Edit"). The BE route auto-derives ``current_value`` from
  // ``last_price * quantity`` on partial-update when BOTH fields
  // are in the patch, so the FE doesn't need to do manual arithmetic.
  // The buttons render Edit always (even on cash rows with no
  // symbol) and Analyze only when there's a tradable ticker.
  const openEdit = (h: Holding) => {
    // Clear stale submit error FIRST so a flicker of the prior row's
    // error message doesn't show against the new row's freshly-
    // populated form fields during the same render pass.
    setEditError(null)
    setEditHolding(h)
    setEditSymbol(h.symbol ?? '')
    setEditDescription(h.description ?? '')
    setEditQuantity(h.quantity != null ? String(h.quantity) : '')
    setEditLastPrice(h.last_price != null ? String(h.last_price) : '')
    setEditCostBasis(h.cost_basis_total != null ? String(h.cost_basis_total) : '')
    setEditType(h.type ?? 'Stock')
  }

  const resetEditForm = () => {
    setEditHolding(null)
    setEditSymbol('')
    setEditDescription('')
    setEditQuantity('')
    setEditLastPrice('')
    setEditCostBasis('')
    setEditType('Stock')
    setEditError(null)
  }

  const submitEditHolding = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editHolding) return
    setEditSubmitting(true)
    setEditError(null)
    try {
      const qty = Number(editQuantity)
      if (!Number.isFinite(qty) || qty <= 0) {
        setEditError('Quantity must be a positive number.')
        setEditSubmitting(false)
        return
      }
      const trimmedSymbol = editSymbol.trim().toUpperCase()
      if (!trimmedSymbol) {
        setEditError('Symbol is required.')
        setEditSubmitting(false)
        return
      }
      // Send only what the FE knows how to edit. ``current_value``
      // is omitted intentionally — the BE route sees BOTH quantity
      // AND last_price in the patch and derives current_value
      // server-side (see ``app/routes/holdings.py::update_holding``).
      // Sending an explicit current_value would short-circuit
      // geometric tangent cases (e.g. user knows the exact cost basis
      // and wants current_value = cost_basis regardless of price*qty).
      const payload: HoldingUpdate = {
        symbol: trimmedSymbol,
        description: editDescription.trim() === '' ? null : editDescription.trim(),
        quantity: qty,
        last_price: editLastPrice === '' ? null : Number(editLastPrice),
        cost_basis_total: editCostBasis === '' ? null : Number(editCostBasis),
        type: editType || null,
      }
      await rulesService.updateHolding(editHolding.id, payload)
      await loadData()
      resetEditForm()
      setImportStatus(`Updated ${trimmedSymbol}.`)
    } catch (err: any) {
      setEditError(
        err?.response?.data?.detail ?? err?.message ?? 'Failed to update holding.'
      )
    } finally {
      setEditSubmitting(false)
    }
  }

  // ---- Phase 47 — Delete confirm ----
  // Holds the row whose Delete button was clicked so the confirm
  // step echoes the SPECIFIC position summary ("Delete AAPL, 10
  // shares @ $200?") rather than a generic "Are you sure?". Hard-
  // delete on the BE mirrors the import flow's existing contract
  // (overwrites-or-replaces rows on re-import), so soft-delete
  // would be a new persistent concept that buys us nothing in a
  // single-user portfolio app.
  const openDelete = (h: Holding) => {
    setDeleteHoldingRow(h)
    setDeleteError(null)
  }

  const submitDeleteHolding = async () => {
    if (!deleteHoldingRow) return
    setDeleteSubmitting(true)
    setDeleteError(null)
    try {
      const symbolForMsg = deleteHoldingRow.symbol ?? '(unknown)'
      const deletedId = deleteHoldingRow.id
      await rulesService.deleteHolding(deletedId)
      await loadData()
      setDeleteHoldingRow(null)
      setImportStatus(`Deleted ${symbolForMsg} from portfolio.`)
    } catch (err: any) {
      setDeleteError(
        err?.response?.data?.detail ?? err?.message ?? 'Failed to delete holding.'
      )
    } finally {
      setDeleteSubmitting(false)
    }
  }

  // ---- Derived aggregates ----
  const holdingsByAccount: Record<
    number,
    { account: Account; holdings: Holding[]; total: number }
  > = {}
  for (const h of holdings) {
    if (!holdingsByAccount[h.account_id]) {
      const acct = accounts.find((a) => a.id === h.account_id)
      if (!acct) continue
      holdingsByAccount[h.account_id] = { account: acct, holdings: [], total: 0 }
    }
    holdingsByAccount[h.account_id].holdings.push(h)
  }
  for (const group of Object.values(holdingsByAccount)) {
    group.total = group.holdings.reduce(
      (sum, h) => sum + (h.live_value ?? h.current_value),
      0
    )
    group.holdings.sort(
      (a, b) => (b.live_value ?? b.current_value) - (a.live_value ?? a.current_value)
    )
  }
  const grandTotal = Object.values(holdingsByAccount).reduce((s, g) => s + g.total, 0)

  // ---- Phase 41 derived: Top Movers (only after live prices) ----
  const topMovers = useMemo(() => {
    const priced = holdings.filter((h) => h.day_change_pct != null) as Array<
      Holding & { day_change_pct: number }
    >
    if (priced.length === 0) return null
    const winners = [...priced]
      .sort((a, b) => b.day_change_pct - a.day_change_pct)
      .slice(0, 5)
    const losers = [...priced]
      .sort((a, b) => a.day_change_pct - b.day_change_pct)
      .slice(0, 3)
    return { winners, losers }
  }, [holdings])

  // ---- Phase 41 derived: Top Holdings by % portfolio (concentration) ----
  const topHoldingsConcentration = useMemo(() => {
    if (grandTotal <= 0) return []
    return [...holdings]
      .map((h) => ({
        h,
        pct: ((h.live_value ?? h.current_value) / grandTotal) * 100,
        value: h.live_value ?? h.current_value,
      }))
      .sort((a, b) => b.pct - a.pct)
      .slice(0, 10)
  }, [holdings, grandTotal])

  // ---- Phase 42 derived: every tradable holding (analyst-coverage batch) ----
  // User asked for analyst coverage to be visible on /portfolio's
  // HOLDINGS -- not just a top-N slice. Fetch every distinct ticker
  // that has a real symbol and isn't a Cash row. Excludes only Cash
  // (no trading symbol) and rows without a symbol. ``Bond`` /
  // bond ETFs like AGG/BND ARE included: they have real Finnhub
  // tickers and the user explicitly wants coverage on their
  // holdings, not for us to second-guess asset-class semantics.
  //
  // Dedup by symbol: two accounts can hold the same ticker (AAPL in
  // both a brokerage + an IRA) and the chip on every row reads from
  // the same cache entry, so we only need one upstream call
  // regardless of how many rows share a symbol.
  //
  // Rate-limit math: ``N ≤ 50`` symbols × 2 endpoints = ``2N``
  // upstream calls per cold fetch, gated by ``asyncio.Semaphore(5)``
  // on the BE. For a 30-stock portfolio that's 60 upstream calls,
  // a SINGLE cold-start burst against the 60/min Finnhub free tier.
  // A subsequent visit within 24h hits the BE ``_cache`` = 0
  // upstream calls. A real >50-symbol portfolio chunks via the
  // 50-item cap in ``api.ts`` so the worst case is still ≤ 100
  // upstream calls / 24h.
  const tradableHoldingsForCoverage = useMemo(() => {
    const seen = new Set<string>()
    return holdings.filter((h) => {
      if (!h.symbol) return false
      if ((h.type ?? '').toLowerCase() === 'cash') return false
      const sym = h.symbol.toUpperCase()
      if (seen.has(sym)) return false
      seen.add(sym)
      return true
    })
  }, [holdings])

  // ---- Phase 42 derived: aggregate analyst signal across covered tickers ----
  // Sums each bucket across the most-recent 4 reported months for every
  // covered ticker; mirrors the math the per-row AnalyzeContent drawer +
  // the RatingsChip component use so the card matches the chips pixel-
  // for-pixel.
  //
  // ``covered`` counts distinct tradable symbols with NON-EMPTY monthly
  // data: a ticker that returned ``status='ok'`` but with an empty
  // ``recommendation_trends`` array is NOT counted (its row would
  // render as "Uncovered" so including it in the badge would
  // overwrite the chip's honest empty-state with a misleading
  // "covered" label).
  const analystCoverageAggregate = useMemo(() => {
    const aggregate = {
      covered: 0,
      excluded: 0,
      strongBuy: 0,
      buy: 0,
      hold: 0,
      sell: 0,
      strongSell: 0,
    }
    for (const h of tradableHoldingsForCoverage) {
      // Asset types that Finnhub never covers (ETFs, mutual funds,
      // bonds, crypto) are counted as "excluded" rather than
      // "uncovered" so the coverage ratio denominator reflects only
      // stock-like holdings that SHOULD have consensus data.
      const assetLabel = noCoverageLabel(h.type)
      if (assetLabel) {
        aggregate.excluded += 1
        continue
      }
      const sym = h.symbol!.toUpperCase()
      const entry = ratingsByTicker[sym]
      if (!entry || entry.state !== 'ok') continue
      const trends = entry.data.recommendation_trends ?? []
      const months4 = trends.slice(0, 4).reverse()
      // Only count as "covered" when we have at least one monthly row
      // to sum -- prevents a 0-row ticker from inflating the badge
      // while still rendering honestly on the chip.
      if (months4.length === 0) continue
      aggregate.covered += 1
      for (const t of months4) {
        aggregate.strongBuy += t.strongBuy ?? 0
        aggregate.buy += t.buy ?? 0
        aggregate.hold += t.hold ?? 0
        aggregate.sell += t.sell ?? 0
        aggregate.strongSell += t.strongSell ?? 0
      }
    }
    return aggregate
  }, [tradableHoldingsForCoverage, ratingsByTicker])

  // Phase 42 — batch fetch on portfolio mount + whenever holdings
  // change (post-import, post-refresh). Lifted to a useEffect on the
  // ``tradableHoldingsForCoverage`` memo rather than folded into
  // ``loadData()`` so an import that arrives AFTER the initial loadData
  // resolves (the in-flight /portfolio file upload flow) still
  // re-fires the batch without a full page reload. Marks every
  // distinct tradable ticker as ``state: 'loading'`` BEFORE the await
  // so the existing Analyze drawer's short-circuit
  // (`if (ratingsByTicker[symbol]) return;`) correctly returns
  // instead of re-firing the same upstream call.
  useEffect(() => {
    const symbols = tradableHoldingsForCoverage.map((h) => h.symbol!.toUpperCase())
    if (symbols.length === 0) return
    setRatingsByTicker((prev) => {
      const next = { ...prev }
      let mutated = false
      for (const sym of symbols) {
        if (!next[sym]) {
          next[sym] = { state: 'loading' }
          mutated = true
        }
      }
      return mutated ? next : prev
    })
    setAnalystCoverageError(null)
    // Reset the loaded flag on every fetch attempt so a holdings
    // change that RE-TRIGGERS this effect (e.g. post-import or
    // post-refresh) flips the card back to "Loading…" until the
    // new batch resolves. Without the reset, the first loaded
    // state would lock in even if subsequent fetches error.
    setAnalystCoverageLoaded(false)
    let cancelled = false
    rulesService
      .getBatchAnalystRatings(symbols)
      .then((resp) => {
        if (cancelled) return
        // Build a lookup map of returned results so we can sweep ALL
        // requested symbols — not just the ones in resp.results.
        // If Finnhub silently drops a ticker (invalid CUSIP, partial
        // response, upstream timeout), that symbol would stay
        // permanently in 'loading' state (showing "—" in the chip)
        // because the old loop only iterated resp.results. Sweeping
        // the requested symbols list guarantees every ticker exits
        // loading state regardless of what the API returned.
        const resultMap = new Map(resp.results.map(r => [r.symbol, r]))
        setRatingsByTicker((prev) => {
          const next = { ...prev }
          for (const sym of symbols) {
            const item = resultMap.get(sym)
            if (item && item.status === 'ok' && item.data) {
              next[sym] = { state: 'ok', data: item.data }
            } else {
              // Covers explicit errors AND missing/omitted symbols
              next[sym] = {
                state: 'error',
                message: item?.error ?? 'No coverage available',
              }
            }
          }
          return next
        })
        // Mark loaded even when EVERY item returned ``status='error'``
        // — without this the "Loading coverage…" footer stayed glued
        // to the card forever because per-ticker errors never produce
        // a whole-batch ``analystCoverageError``.
        setAnalystCoverageLoaded(true)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setAnalystCoverageError(
          (err as { response?: { data?: { detail?: string } } })?.response
            ?.data?.detail ?? classifyErrorMessage(err),
        )
        // Mark all tickers still in 'loading' as 'error' so chips
        // show 'Uncovered' instead of an infinite spinner. Without
        // this, a whole-batch failure (500/502) leaves every ticker
        // permanently in the loading state.
        setRatingsByTicker((prev) => {
          const next = { ...prev }
          let mutated = false
          for (const sym of symbols) {
            if (next[sym]?.state === 'loading') {
              next[sym] = {
                state: 'error',
                message: 'Analyst ratings service unavailable',
              }
              mutated = true
            }
          }
          return mutated ? next : prev
        })
        setAnalystCoverageLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [tradableHoldingsForCoverage])

  const tc = useThemeColors()
  const accountPalette = ACCOUNT_KEYS.map(k => tc[k] ?? '#6B7280')
  const consensusColors = useMemo(() => ({
    strongBuy: tc.consensus_strong_buy,
    buy: tc.consensus_buy,
    hold: tc.consensus_hold,
    sell: tc.consensus_sell,
    strongSell: tc.consensus_strong_sell,
  }), [tc])

  const ready = !loading && !!summary

  return (
    <PageLayout>
      <AtlasFilterProvider>
      <PageHeader
        title="Portfolio"
        description="Your holdings, allocation, and real-time values."
        className="mb-6"
      />

      {/* Floating bar — URL-synced via ?range=… (page-default YTD).
          Visual-only today: portfolio monthly-trend logic is not
          range-aware yet. Future work will wire ranged trends. */}
      <FloatingTimeRangeBar />

      {error && (
        <ErrorBanner
          title="Couldn't load portfolio:"
          message={error}
          variant="warning"
          onRetry={() => setRetryCount((c) => c + 1)}
        />
      )}

      <HeroSummary
        loading={!ready}
        summary={ready ? summary : null}
        greeting={profile?.full_name ?? 'Alex'}
      />

      {/* Import + Refresh + Add Holding row (Phase 41 adds Add) */}
      <div className="flex flex-wrap items-center gap-3 mt-6 mb-4">
        <label className="relative">
          <input
            type="file"
            accept=".csv,.pdf,application/pdf,text/csv"
            onChange={handleImport}
            disabled={importing}
            className="absolute inset-0 opacity-0 cursor-pointer"
          />
          <Button
            variant="primary"
            size="sm"
            disabled={importing}
            icon={
              importing ? (
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
              ) : (
                <Upload className="w-4 h-4" aria-hidden="true" />
              )
            }
          >
            {importing ? 'Importing…' : 'Import Portfolio (CSV / PDF)'}
          </Button>
        </label>
        <Button
          variant="secondary"
          size="sm"
          onClick={handleRefresh}
          disabled={refreshing || holdings.length === 0}
          icon={
            refreshing ? (
              <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw className="w-4 h-4" aria-hidden="true" />
            )
          }
        >
          {refreshing ? 'Refreshing…' : 'Refresh Prices'}
        </Button>
        <Button
          variant="tertiary"
          size="sm"
          onClick={() => setShowAddForm(true)}
          icon={<Plus className="w-4 h-4" aria-hidden="true" />}
        >
          Add Holding
        </Button>
      </div>

      {/* ============================================================
          Phase 48 — auto-refresh config row
          ============================================================
          Sits BELOW the action buttons so the timer input reads as
          a "preference" rather than a sibling action. The number
          input is a plain styled <input type="number"> (NOT the
          wrapped Input component) because the wrapped component
          forces a label slot that doesn't match the trailing
          "min (0 = off)" suffix. value/onChange round-trip through
          setAutoRefreshMinutes which writes localStorage AND
          returns the clamped value — the React state mirrors
          storage so the input never displays an out-of-bounds
          value the user just typed.

          Two readouts flank the input:
          - "Next in MM:SS" countdown when the loop is on and at
            least one refresh has fired (so the countdown has a
            real anchor).
          - "Last refreshed 14m ago" badge pushed to the right via
            ml-auto, so the user has a single-glance freshness
            signal without parsing the countdown.
          - "Auto-refresh is off" when the user set 0, so the row
            never reads as broken (input shows 0, no countdown). */}
      <div className="flex flex-wrap items-center gap-3 -mt-2 mb-4 text-sm">
        <label
          htmlFor="auto-refresh-minutes"
          className="label-sm uppercase tracking-wider text-tertiary"
        >
          Auto-refresh every
        </label>
        <input
          id="auto-refresh-minutes"
          type="number"
          min={0}
          max={MAX_REFRESH_MINUTES}
          step={5}
          // value is the LOCAL draft (what the user typed), NOT the
          // committed number — so a transient ``1`` doesn't snap to
          // ``5`` mid-keystroke. onBlur commits via
          // setAutoRefreshMinutes which clamps + persists, then we
          // mirror the clamped value back into both states so the
          // input + the auto-refresh loop agree.
          value={autoRefreshMinutesDraft}
          onChange={(e) => setAutoRefreshMinutesDraft(e.target.value)}
          onBlur={() => {
            const parsed = Number(autoRefreshMinutesDraft)
            const clamped = setAutoRefreshMinutes(parsed)
            setAutoRefreshMinutesState(clamped)
            setAutoRefreshMinutesDraft(String(clamped))
          }}
          className="w-20 px-2 py-1 rounded text-sm bg-[var(--bg-tertiary)] border border-[var(--border-subtle)] text-primary focus:outline-none focus:ring-2 focus:ring-[var(--primary-500)] focus:border-transparent"
          title={`Minutes between automatic price refreshes (0 to disable, ${MIN_REFRESH_MINUTES}-${MAX_REFRESH_MINUTES})`}
          data-testid="auto-refresh-minutes-input"
        />
        <span className="text-xs text-tertiary">min (0 = off)</span>
        {autoRefreshMinutes > 0 && nextRefreshInSec !== null && (
          <span
            className="text-xs text-tertiary font-mono"
            data-testid="auto-refresh-countdown"
          >
            · Next in {Math.floor(nextRefreshInSec / 60)}:
            {(nextRefreshInSec % 60).toString().padStart(2, '0')}
          </span>
        )}
        {autoRefreshMinutes === 0 && (
          <span
            className="text-xs text-tertiary"
            data-testid="auto-refresh-off-indicator"
          >
            · Auto-refresh is off
          </span>
        )}
        {lastRefreshedLabel && (
          <span
            className="ml-auto text-xs text-tertiary"
            data-testid="last-refreshed-label"
          >
            Last refreshed {lastRefreshedLabel}
          </span>
        )}
      </div>

      {importStatus && (
        <div
          className="flex items-start gap-3 p-3 rounded-[var(--radius-md)] bg-[var(--success-50)] text-[var(--success-700)] border border-[var(--success-200)] mb-4"
          role="status"
        >
          <FileSpreadsheet className="w-5 h-5 mt-0.5 flex-shrink-0" aria-hidden="true" />
          <p className="text-sm flex-1">{importStatus}</p>
        </div>
      )}

      {priceWarning && (
        <div className="p-3 rounded-[var(--radius-md)] bg-[var(--warning-50)] text-[var(--warning-700)] border border-[var(--warning-200)] mb-4 text-sm">
          ⚠️ {priceWarning}
        </div>
      )}

      {loading ? (
        <div className="space-y-6">
          {[0, 1].map((i) => (
            <div key={i} className="card p-6 border-l-4 border-l-[var(--primary-200)]">
              <div className="flex items-center gap-3 mb-4">
                <div className="skeleton h-4 w-4 rounded" />
                <div className="skeleton h-5 w-40" />
              </div>
              <div className="space-y-2">
                {[0, 1, 2].map((j) => (
                  <div key={j} className="skeleton h-10 w-full rounded-lg" />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : Object.keys(holdingsByAccount).length === 0 ? (<EmptyState
            icon={<Landmark className="h-6 w-6" />}
            title="Build your portfolio view"
            description="Add a holding or import a position file so Atlas can organize the investments you choose to review."
            guidance={<p className="text-sm">Use Import Portfolio CSV or Add Holding above. This empty state does not assume positions or performance.</p>}
          />
      ) : (
        <motion.div
          className="space-y-8"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        >
          {/* ============================================================
              Phase 42 -- Analyst Coverage card (prominent top-of-portfolio)
              ============================================================
              Sits ABOVE the account-grouped tables so the user lands on
              /portfolio and immediately sees the consensus aggregate.
              Renders only when the user has at least one tradeable
              holding (Cash / Bond rows are filtered out of the batch
              see ``tradableHoldingsForCoverage`` memo). The card's numbers match the
              per-row chips pixel-for-pixel (same 4-month aggregate math)
              so the two views never disagree. */}
          {(tradableHoldingsForCoverage.length - analystCoverageAggregate.excluded) > 0 && (
            <TiltCard className="h-full">
            <section
              className="surface-focal card p-6 border-l-4 border-l-[var(--primary-400)] h-full"
              data-testid="analyst-coverage-card"
            >
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 rounded-lg bg-[var(--primary-50)] flex items-center justify-center border border-[var(--primary-200)]">
                  <Sparkles className="w-4 h-4 text-[var(--primary-600)]" aria-hidden="true" />
                </div>
                <div>
                  <h2 className="headline-md text-primary">Analyst Coverage</h2>
                  <span className="text-xs text-tertiary">
                    sell-side consensus across your{' '}
                    <span className="font-semibold text-[var(--primary-600)]">
                      {tradableHoldingsForCoverage.length} unique{' '}
                      {tradableHoldingsForCoverage.length === 1 ? 'ticker' : 'tickers'}
                    </span>
                  </span>
                </div>
                {(() => {
                  const stockCount = tradableHoldingsForCoverage.length - analystCoverageAggregate.excluded
                  if (analystCoverageError) {
                    return (
                      <span className="ml-auto text-xs text-[var(--danger-700)]" role="alert">
                        ⚠️ {analystCoverageError}
                      </span>
                    )
                  }
                  if (analystCoverageAggregate.covered < stockCount) {
                    return (
                      <span className="ml-auto text-xs text-tertiary">
                        {analystCoverageAggregate.covered}/{stockCount} stocks covered
                        {analystCoverageAggregate.excluded > 0 && (
                          <span className="opacity-60"> · {analystCoverageAggregate.excluded} excluded</span>
                        )}
                      </span>
                    )
                  }
                  return (
                    <span className="ml-auto text-xs text-[var(--success-700)]">
                      ✓ all {stockCount} stocks covered
                      {analystCoverageAggregate.excluded > 0 && (
                        <span className="text-tertiary opacity-60"> · {analystCoverageAggregate.excluded} excluded</span>
                      )}
                    </span>
                  )
                })()}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                {[
                  {
                    key: 'strongBuy',
                    label: 'Strong Buy',
                    n: analystCoverageAggregate.strongBuy,
                    bg: 'bg-gradient-to-br from-[var(--success-50)] to-[var(--success-100)]',
                    border: 'border-[var(--success-200)]',
                    text: 'text-[var(--success-700)]',
                  },
                  {
                    key: 'buy',
                    label: 'Buy',
                    n: analystCoverageAggregate.buy,
                    bg: 'bg-gradient-to-br from-[var(--success-50)] to-[var(--success-100)]',
                    border: 'border-[var(--success-200)]',
                    text: 'text-[var(--success-600)]',
                  },
                  {
                    key: 'hold',
                    label: 'Hold',
                    n: analystCoverageAggregate.hold,
                    bg: 'bg-[var(--bg-tertiary)]',
                    border: 'border-[var(--border-subtle)]',
                    text: 'text-tertiary',
                  },
                  {
                    key: 'sell',
                    label: 'Sell',
                    n: analystCoverageAggregate.sell,
                    bg: 'bg-gradient-to-br from-[var(--warning-50)] to-[var(--warning-100)]',
                    border: 'border-[var(--warning-200)]',
                    text: 'text-[var(--warning-700)]',
                  },
                  {
                    key: 'strongSell',
                    label: 'Strong Sell',
                    n: analystCoverageAggregate.strongSell,
                    bg: 'bg-gradient-to-br from-[var(--danger-50)] to-[var(--danger-100)]',
                    border: 'border-[var(--danger-200)]',
                    text: 'text-[var(--danger-700)]',
                  },
                ].map((bucket) => (
                  <div
                    key={bucket.key}
                    className={`p-3.5 rounded-lg border ${bucket.bg} ${bucket.border} ${bucket.text} transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 cursor-default`}
                    data-testid={`coverage-bucket-${bucket.key}`}
                  >
                    <p className="text-[10px] uppercase tracking-wider font-semibold opacity-70 mb-1">
                      {bucket.label}
                    </p>
                    <p className="text-2xl font-bold tracking-tight tabular-nums"><CountUp end={bucket.n} duration={700} /></p>
                  </div>
                ))}
              </div>
              {analystCoverageAggregate.covered === 0 &&
                !analystCoverageError &&
                (tradableHoldingsForCoverage.length - analystCoverageAggregate.excluded) > 0 &&
                (analystCoverageLoaded ? (
                  // After the batch fetch resolves with zero coverage we
                  // RENDER an honest "no coverage" footer so the user
                  // can tell the call actually completed (vs. reading
                  // the old "Loading coverage…" copy that implied the
                  // call was still in flight). The per-row chips below
                  // already carry the per-ticker error detail in their
                  // title attribute for triage.
                  <p
                    className="text-xs text-tertiary mt-3"
                    data-testid="analyst-coverage-empty"
                  >
                    No analyst coverage available — Finnhub may be unreachable
                    or missing an API key.
                    {analystCoverageAggregate.excluded > 0 && ` ${analystCoverageAggregate.excluded} excluded (no consensus).`}
                  </p>
                ) : (
                  // Genuine in-flight window: the batch fetch is still
                  // resolving, so "Loading…" is the correct copy. Once
                  // ``analystCoverageLoaded`` flips (next tick) this
                  // branch unmounts and the empty-state above takes
                  // over if the result set is still empty.
                  <p
                    className="text-xs text-tertiary mt-3"
                    data-testid="analyst-coverage-loading"
                  >
                    Loading coverage for {tradableHoldingsForCoverage.length - analystCoverageAggregate.excluded}{' '}
                    {tradableHoldingsForCoverage.length - analystCoverageAggregate.excluded === 1 ? 'stock' : 'stocks'}…
                  </p>
                ))}
            </section>
            </TiltCard>
          )}

          {Object.entries(holdingsByAccount).map(([acctId, group]) => (
            <section key={acctId} className="card overflow-hidden border-l-4 border-l-[var(--primary-400)] shadow-[var(--shadow-3)]">
              <div className="px-5 py-4 bg-gradient-to-r from-[var(--bg-tertiary)] via-[var(--bg-tertiary)] to-transparent border-b border-[var(--border-subtle)]">
                <div className="flex items-center justify-between flex-wrap gap-3">
                  <div className="flex items-center gap-3">
                    <div
                      className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ring-1 ring-inset ring-white/10"
                      style={{
                        backgroundColor: `${accountPalette[parseInt(acctId) % accountPalette.length]}18`,
                      }}
                    >
                      <Wallet
                        className="w-4 h-4"
                        style={{ color: accountPalette[parseInt(acctId) % accountPalette.length] }}
                        aria-hidden="true"
                      />
                    </div>
                    <div>
                      <h2 className="headline-md text-primary leading-tight">{group.account.account_name}</h2>
                      <p className="text-xs text-tertiary mt-0.5">
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-[var(--bg-secondary)] border border-[var(--border-subtle)]">
                          {group.account.account_type}
                        </span>
                        <span className="mx-1.5">·</span>
                        {group.holdings.length} position{group.holdings.length === 1 ? '' : 's'}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="numeric-lg text-primary">
                      {group.total.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </p>
                    <p className="text-[10px] text-tertiary">
                      {grandTotal > 0 ? `${((group.total / grandTotal) * 100).toFixed(1)}% of portfolio` : ''}
                    </p>
                  </div>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="holdings-table">
                  <thead>
                    <tr className="border-b-2 border-[var(--border-color)] bg-gradient-to-r from-[var(--bg-secondary)] to-transparent">
                      <th className="text-left py-3 px-4 label-sm uppercase tracking-wider text-[var(--text-tertiary)] text-[10px]">Symbol</th>
                      <th className="text-left py-3 px-4 label-sm uppercase tracking-wider text-[var(--text-tertiary)] text-[10px]">Description</th>
                      <th className="text-right py-3 px-4 label-sm uppercase tracking-wider text-[var(--text-tertiary)] text-[10px]">Shares</th>
                      <th className="text-right py-3 px-4 label-sm uppercase tracking-wider text-[var(--text-tertiary)] text-[10px]">Price</th>
                      <th className="text-right py-3 px-4 label-sm uppercase tracking-wider text-[var(--text-tertiary)] text-[10px]">Value</th>
                      <th className="text-right py-3 px-4 label-sm uppercase tracking-wider text-[var(--text-tertiary)] text-[10px]">Gain/Loss</th>
                      <th className="text-right py-3 px-4 label-sm uppercase tracking-wider text-[var(--text-tertiary)] text-[10px]">%</th>
                      <th className="text-right py-3 px-4 label-sm uppercase tracking-wider text-[var(--text-tertiary)] text-[10px]">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.holdings.map((h, rowIdx) => {
                      const value = h.live_value ?? h.current_value
                      const pct = group.total > 0 ? (value / group.total) * 100 : 0
                      const gain =
                        h.cost_basis_total != null && h.cost_basis_total !== 0
                          ? ((value - h.cost_basis_total) / Math.abs(h.cost_basis_total)) * 100
                          : null
                      const gainColor =
                        gain != null
                          ? gain >= 0
                            ? 'text-[var(--success-700)]'
                            : 'text-[var(--danger-700)]'
                          : 'text-tertiary'
                      // Zebra striping — alternating subtle background
                      const rowBg = rowIdx % 2 === 0 ? '' : 'bg-[var(--bg-tertiary)]/30'
                      return (
                        <tr
                          key={h.id}
                          className={`border-b border-[var(--border-subtle)] hover:bg-[var(--primary-50)]/60 transition-colors duration-150 ${rowBg}`}
                        >
                          <td className="py-2.5 px-4">
                            {h.symbol ? (
                              <div className="flex flex-col gap-1">
                                <a
                                  href={`https://finance.yahoo.com/quote/${encodeURIComponent(h.symbol.toUpperCase())}`}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 font-mono font-semibold text-primary text-xs hover:text-[var(--primary-600)] hover:underline transition-colors group"
                                  title={`View ${h.symbol} on Yahoo Finance`}
                                >
                                  {h.symbol}
                                  <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity text-[var(--primary-500)]" aria-hidden="true" />
                                </a>
                                <RatingsChip
                                  symbol={h.symbol.toUpperCase()}
                                  ratingsByTicker={ratingsByTicker}
                                  holdingType={h.type}
                                />
                              </div>
                            ) : (
                              <span className="text-tertiary text-xs">—</span>
                            )}
                          </td>
                          <td className="py-2.5 px-4 text-primary max-w-[16rem] truncate" title={h.description || ''}>
                            {h.description || '—'}
                          </td>
                          <td className="py-2.5 px-4 text-right text-secondary font-mono text-xs">
                            {h.quantity != null ? h.quantity.toLocaleString('en-US', { maximumFractionDigits: 4 }) : '—'}
                          </td>
                          <td className="py-2.5 px-4 text-right">
                            {h.live_price != null ? (
                              <span className="text-primary font-mono text-xs">
                                {h.live_price.toFixed(2)}
                                {h.day_change_pct != null && (
                                  <span className={`ml-1 text-[10px] ${h.day_change_pct >= 0 ? 'text-[var(--success-600)]' : 'text-[var(--danger-600)]'}`}>
                                    {h.day_change_pct >= 0 ? '↑' : '↓'}{Math.abs(h.day_change_pct).toFixed(1)}%
                                  </span>
                                )}
                              </span>
                            ) : h.last_price != null ? (
                              <span className="text-secondary font-mono text-xs">
                                {h.last_price.toFixed(2)}
                              </span>
                            ) : (
                              <span className="text-tertiary text-xs">—</span>
                            )}
                          </td>
                          <td className="py-2.5 px-4 text-right font-semibold text-primary font-mono text-xs">
                            {value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </td>
                          <td className={`py-2.5 px-4 text-right font-mono text-xs ${gainColor}`}>
                            {gain != null ? `${gain >= 0 ? '+' : ''}${gain.toFixed(1)}%` : '—'}
                          </td>
                          <td className="py-2.5 px-4 text-right text-tertiary text-xs">
                            {pct.toFixed(1)}%
                          </td>
                          <td className="py-2.5 px-4 text-right">
                            {/* Phase 47 — three-button cluster.
                                Phase 47 bullet order: Edit → Analyze → Delete.
                                Destructive action LAST (vs. sandwiched in the
                                middle, which made cursor-tab users aiming for
                                Analyze accidentally land on Delete). Edit +
                                Delete render on EVERY row so the user can
                                correct or remove parser-led imports regardless
                                of whether they hold a tradable ticker. Analyze
                                is conditional on `h.symbol` because the Finnhub
                                endpoint 422s on empty symbols.
                                Phase 47 hover styles: Edit = primary-blue glow,
                                Analyze = subtle gray border-only (visually
                                distinct from Edit's bolder background tint),
                                Delete = danger-red glow. The three reads
                                differently on hover so a user scanning the row
                                can tell which cursor is over which action. */}
                            <div className="inline-flex items-center gap-1 justify-end whitespace-nowrap">
                              <button
                                type="button"
                                onClick={() => openEdit(h)}
                                className="inline-flex items-center gap-1 px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:bg-[var(--primary-50)] hover:text-[var(--primary-700)] border border-transparent hover:border-[var(--primary-200)] transition-colors"
                                title={`Edit ${h.symbol ?? 'holding'}`}
                                data-testid={`holding-edit-${h.id}`}
                              >
                                <Pencil className="w-3 h-3" aria-hidden="true" />
                                Edit
                              </button>
                              {h.symbol && (
                                <button
                                  type="button"
                                  onClick={() => openAnalyze(h)}
                                  className="inline-flex items-center gap-1 px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)] hover:border-[var(--primary-200)] hover:text-[var(--primary-700)] border border-transparent transition-colors"
                                  title={`Fetch analyst consensus for ${h.symbol}`}
                                  data-testid={`holding-analyze-${h.id}`}
                                >
                                  <Sparkles className="w-3 h-3" aria-hidden="true" />
                                  Analyze
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() => openDelete(h)}
                                className="inline-flex items-center gap-1 px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:bg-[var(--danger-50)] hover:text-[var(--danger-700)] border border-transparent hover:border-[var(--danger-200)] transition-colors"
                                title={`Delete ${h.symbol ?? 'holding'}`}
                                data-testid={`holding-delete-${h.id}`}
                              >
                                <Trash2 className="w-3 h-3" aria-hidden="true" />
                                Delete
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          ))}

          {/* ============================================================
              Phase 41 — Top Movers (only after refresh)
              ============================================================ */}
          {topMovers && (topMovers.winners.length > 0 || topMovers.losers.length > 0) && (
            <TiltCard className="h-full">
            <section className="card p-6 border-l-4 border-l-[var(--primary-400)] h-full" data-testid="top-movers-card">
              <div className="flex items-center gap-2 mb-5">
                <div className="w-8 h-8 rounded-lg bg-[var(--primary-50)] flex items-center justify-center border border-[var(--primary-200)]">
                  <TrendingUp className="w-4 h-4 text-[var(--primary-600)]" aria-hidden="true" />
                </div>
                <div>
                  <h2 className="headline-md text-primary">Top Movers</h2>
                  <span className="text-xs text-tertiary">from today’s live prices</span>
                </div>
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {topMovers.winners.length > 0 && (
                  <div>
                    <p className="label-sm uppercase tracking-wider mb-3 flex items-center gap-1 text-[var(--success-700)]">
                      <ArrowUpRight className="w-3.5 h-3.5" aria-hidden="true" />
                      Winners
                    </p>
                    <div className="space-y-2">
                      {topMovers.winners.map((h) => {
                        const pct = h.day_change_pct ?? 0
                        // Scale bar width: winners cap at +10% visually
                        const width = Math.min(100, (pct / 10) * 100)
                        return (
                          <div key={h.id} className="flex items-center gap-3 text-xs">
                            <a
                            href={`https://finance.yahoo.com/quote/${encodeURIComponent((h.symbol ?? '').toUpperCase())}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="w-12 font-mono font-bold text-primary hover:text-[var(--primary-600)] hover:underline transition-colors"
                            title={`View ${h.symbol} on Yahoo Finance`}
                          >
                            {h.symbol}
                          </a>
                            <AnimatedRadialProgress
                              percentage={Math.min(100, Math.max(4, width))}
                              size={36}
                              strokeWidth={4}
                              color="var(--success-500)"
                              trackColor="var(--bg-tertiary)"
                              label={
                                <span className="text-[10px] font-mono font-semibold text-[var(--success-700)]">
                                  +{pct.toFixed(2)}%
                                </span>
                              }
                            />
                            <span className="w-16 text-right font-mono font-semibold text-[var(--success-700)]">
                              +{pct.toFixed(2)}%
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
                {topMovers.losers.length > 0 && (
                  <div>
                    <p className="label-sm uppercase tracking-wider mb-3 flex items-center gap-1 text-[var(--danger-700)]">
                      <ArrowDownRight className="w-3.5 h-3.5" aria-hidden="true" />
                      Losers
                    </p>
                    <div className="space-y-2">
                      {topMovers.losers.map((h) => {
                        const pct = h.day_change_pct ?? 0
                        const width = Math.min(100, (Math.abs(pct) / 10) * 100)
                        return (
                          <div key={h.id} className="flex items-center gap-3 text-xs">
                            <a
                            href={`https://finance.yahoo.com/quote/${encodeURIComponent((h.symbol ?? '').toUpperCase())}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="w-12 font-mono font-bold text-primary hover:text-[var(--primary-600)] hover:underline transition-colors"
                            title={`View ${h.symbol} on Yahoo Finance`}
                          >
                            {h.symbol}
                          </a>
                            <AnimatedRadialProgress
                              percentage={Math.min(100, Math.max(4, width))}
                              size={36}
                              strokeWidth={4}
                              color="var(--danger-500)"
                              trackColor="var(--bg-tertiary)"
                              label={
                                <span className="text-[10px] font-mono font-semibold text-[var(--danger-700)]">
                                  {Math.abs(pct).toFixed(2)}%
                                </span>
                              }
                            />
                            <span className="w-16 text-right font-mono font-semibold text-[var(--danger-700)]">
                              {pct.toFixed(2)}%
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            </section>
            </TiltCard>
          )}

          {/* ============================================================
              Phase 41 — Asset Allocation (donut + bars)
              ============================================================ */}
          {grandTotal > 0 && (
            <TiltCard className="h-full">
            <section className="card p-6 border-l-4 border-l-[var(--primary-400)] h-full" data-testid="asset-allocation-card">
              <div className="flex items-center gap-2 mb-5">
                <div className="w-8 h-8 rounded-lg bg-[var(--primary-50)] flex items-center justify-center border border-[var(--primary-200)]">
                  <Wallet className="w-4 h-4 text-[var(--primary-600)]" aria-hidden="true" />
                </div>
                <h2 className="headline-md text-primary">Asset Allocation</h2>
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-center">
                {/* SVG donut */}
                <ChartDonut
                  slices={Object.entries(holdingsByAccount).map(([acctId, g], i) => ({
                    label: g.account.account_name,
                    value: g.total,
                    color: accountPalette[i % accountPalette.length],
                    pctLabel: `${((g.total / grandTotal) * 100).toFixed(1)}%`,
                    subLabel: g.account.account_type,
                  }))}
                  centerLabel="Total"
                  centerValue={grandTotal}
                />
                {/* Bars + legend */}
                <div className="space-y-3">
                  {Object.entries(holdingsByAccount).map(([acctId, group], i) => {
                    const pct = (group.total / grandTotal) * 100
                    const color = accountPalette[i % accountPalette.length]
                    return (
                      <div key={acctId} className="space-y-1.5">
                        <div className="flex items-center justify-between text-sm">
                          <div className="flex items-center gap-2">
                            <span
                              className="w-3 h-3 rounded-sm flex-shrink-0"
                              style={{ backgroundColor: color }}
                              aria-hidden="true"
                            />
                            <span className="text-primary font-medium">{group.account.account_name}</span>
                            <span className="text-tertiary text-xs">
                              {group.account.account_type}
                            </span>
                          </div>
                          <span className="text-secondary font-mono text-xs">                            {group.total.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                            {' · '}
                            {pct.toFixed(1)}%
                          </span>
                        </div>
                        <AnimatedRadialProgress
                          percentage={Math.min(100, Math.max(1.5, pct))}
                          size={48}
                          strokeWidth={5}
                          color={color}
                          trackColor="var(--bg-tertiary)"
                          label={
                            <span className="text-[10px] font-mono font-semibold text-primary">
                              {pct.toFixed(1)}%
                            </span>
                          }
                        />
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Type breakdown */}
              {(() => {
                const typeTotals: Record<string, number> = {}
                for (const h of holdings) {
                  const t = h.type || 'Other'
                  typeTotals[t] = (typeTotals[t] || 0) + (h.live_value ?? h.current_value)
                }
                const types = Object.entries(typeTotals).sort((a, b) => b[1] - a[1])
                if (types.length <= 1) return null
                return (
                  <div className="mt-6 pt-4 border-t border-[var(--border-subtle)]">
                    <p className="label-sm text-tertiary uppercase tracking-wider mb-3">By Asset Type</p>
                    <div className="flex flex-wrap gap-3">
                      {types.map(([type, value]) => {
                        const tpct = (value / grandTotal) * 100
                        return (
                          <div
                            key={type}
                            className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[var(--bg-tertiary)]"
                          >
                            <span className="text-sm text-primary font-medium">{type}</span>
                            <span className="text-xs text-tertiary">
                              {tpct.toFixed(1)}%
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })()}
            </section>
            </TiltCard>
          )}

          {/* ============================================================
              Phase 41 — Top Holdings Concentration
              ============================================================ */}
          {topHoldingsConcentration.length > 0 && grandTotal > 0 && (
            <TiltCard className="h-full">
            <section className="card p-6 border-l-4 border-l-[var(--warning-400)] h-full" data-testid="concentration-card">
              <div className="flex items-center gap-2 mb-5">
                <div className="w-8 h-8 rounded-lg bg-[var(--warning-50)] flex items-center justify-center border border-[var(--warning-200)]">
                  <AlertCircle className="w-4 h-4 text-[var(--warning-600)]" aria-hidden="true" />
                </div>
                <div>
                  <h2 className="headline-md text-primary">Top Holdings Concentration</h2>
                  <span className="text-xs text-tertiary">top 10 by weight</span>
                </div>
              </div>
              <div className="space-y-3">
                {topHoldingsConcentration.map(({ h, pct, value }) => {
                  const dangerLevel =
                    pct >= CONCENTRATION_DANGER_PCT ? 'danger'
                      : pct >= CONCENTRATION_WARN_PCT ? 'warn'
                      : 'ok'
                  const barColor =
                    dangerLevel === 'danger'
                      ? 'var(--danger-500)'
                      : dangerLevel === 'warn'
                      ? 'var(--warning-500)'
                      : 'var(--primary-500)'
                  return (
                    <div key={h.id} className="space-y-1" data-testid={`concentration-row-${h.id}`}>
                      <div className="flex items-center justify-between text-sm gap-3">
                        <div className="flex items-center gap-2 min-w-0">
                          {h.symbol ? (
                            <a
                              href={`https://finance.yahoo.com/quote/${encodeURIComponent(h.symbol.toUpperCase())}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 font-mono font-semibold text-primary text-xs hover:text-[var(--primary-600)] hover:underline transition-colors group"
                              title={`View ${h.symbol} on Yahoo Finance`}
                            >
                              {h.symbol}
                              <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity text-[var(--primary-500)]" aria-hidden="true" />
                            </a>
                          ) : (
                            <span className="font-mono font-semibold text-primary text-xs">—</span>
                          )}
                          {h.description && (
                            <span className="text-tertiary text-xs truncate max-w-[20rem]" title={h.description}>
                              {h.description}
                            </span>
                          )}
                          {dangerLevel !== 'ok' && (
                            <span
                              className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                                dangerLevel === 'danger'
                                  ? 'bg-[var(--danger-50)] text-[var(--danger-700)] border border-[var(--danger-200)]'
                                  : 'bg-[var(--warning-50)] text-[var(--warning-700)] border border-[var(--warning-200)]'
                              }`}
                              title={
                                dangerLevel === 'danger'
                                  ? `${pct.toFixed(1)}% in one ticker -- consider rebalancing`
                                  : `${pct.toFixed(1)}% in one ticker -- worth a review`
                              }
                            >
                              <AlertCircle className="w-3 h-3" aria-hidden="true" />
                              {dangerLevel === 'danger' ? 'Concentrated' : 'Review'}
                            </span>
                          )}
                        </div>
                        <div className="text-right flex-shrink-0">
                          <span className="text-primary font-mono text-xs">
                            ${value.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                          </span>
                          <span className="text-tertiary text-xs ml-2 font-mono">{pct.toFixed(1)}%</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <AnimatedRadialProgress
                          percentage={Math.min(100, Math.max(1.5, pct))}
                          size={48}
                          strokeWidth={5}
                          color={barColor}
                          trackColor="var(--bg-tertiary)"
                          label={
                            <span className="text-[10px] font-mono font-semibold text-primary">
                              {pct.toFixed(1)}%
                            </span>
                          }
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
            </TiltCard>
          )}

          {/* Grand total footer */}
          <div className="card p-5 flex items-center justify-between bg-gradient-to-r from-[var(--primary-200)]/15 to-transparent border-l-4 border-l-[var(--primary-500)]">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-[var(--primary-100)] flex items-center justify-center">
                <Wallet className="w-5 h-5 text-[var(--primary-600)]" aria-hidden="true" />
              </div>
              <span className="label-md text-primary">Total Portfolio Value</span>
              {pricesAvailable && (
                <span className="text-[10px] uppercase tracking-wider font-bold text-[var(--success-700)] px-2 py-0.5 rounded bg-[var(--success-50)] border border-[var(--success-200)]">
                  Live
                </span>
              )}
            </div>
            <span className="text-2xl font-bold tracking-tight text-primary tabular-nums">
              {grandTotal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
        </motion.div>
      )}

      {/* ============================================================
          Phase 41 — Add Holding modal
          ============================================================ */}
      <Modal
        open={showAddForm}
        onClose={() => {
          if (!addSubmitting) {
            setShowAddForm(false)
            resetAddForm()
          }
        }}
        title="Add a holding"
        size="md"
        footer={
          <>
            <Button
              variant="tertiary"
              onClick={() => {
                setShowAddForm(false)
                resetAddForm()
              }}
              disabled={addSubmitting}
            >
              Cancel
            </Button>
            <button
              type="submit"
              form="add-holding-form"
              disabled={addSubmitting}
              data-testid="add-holding-submit"
              className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg font-medium bg-[var(--primary-500)] text-[var(--text-on-brand)] hover:bg-[var(--primary-600)] active:bg-[var(--primary-700)] disabled:bg-[var(--slate-400)] transition-all duration-150 disabled:cursor-not-allowed"
            >
              {addSubmitting && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />}
              {addSubmitting ? 'Adding…' : 'Add holding'}
            </button>
          </>
        }
      >
        <form id="add-holding-form" onSubmit={submitAddHolding} className="space-y-4">
          <div>
            <p className="label-sm uppercase tracking-wider text-tertiary mb-2">Account</p>
            <div className="flex items-center gap-3 mb-2">
              {(['existing', 'new'] as const).map((mode) => (
                <label key={mode} className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="radio"
                    name="add-account-mode"
                    checked={addAccountMode === mode}
                    onChange={() => setAddAccountMode(mode)}
                    className="accent-[var(--primary-500)]"
                  />
                  <span>{mode === 'existing' ? 'Use existing account' : 'Create new account'}</span>
                </label>
              ))}
            </div>
            {addAccountMode === 'existing' ? (
              <Select
                value={addAccountId === '' ? '' : String(addAccountId)}
                onChange={(e) =>
                  setAddAccountId(e.target.value === '' ? '' : Number(e.target.value))
                }
                options={[
                  { value: '', label: '— select —' },
                  ...accounts.map((a) => ({ value: String(a.id), label: a.account_name })),
                ]}
              />
            ) : (
              <Input
                value={addAccountName}
                onChange={(e) => setAddAccountName(e.target.value)}
                placeholder="e.g. Crypto Wallet"
                required
              />
            )}
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Symbol"
              value={addSymbol}
              onChange={(e) => setAddSymbol(e.target.value)}
              placeholder="AAPL"
              required
            />
            <Select
              label="Type"
              value={addType}
              onChange={(e) => setAddType(e.target.value)}
              options={HOLDING_TYPE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
            />
          </div>
          <Input
            label="Description (optional)"
            value={addDescription}
            onChange={(e) => setAddDescription(e.target.value)}
            placeholder="Apple Inc."
          />
          <div className="grid grid-cols-3 gap-4">
            <Input
              label="Quantity"
              type="number"
              value={addQuantity}
              onChange={(e) => setAddQuantity(e.target.value)}
              placeholder="10"
              required
            />
            <Input
              label="Last price"
              type="number"
              value={addLastPrice}
              onChange={(e) => setAddLastPrice(e.target.value)}
              placeholder="175.00"
            />
            <Input
              label="Cost basis"
              type="number"
              value={addCostBasis}
              onChange={(e) => setAddCostBasis(e.target.value)}
              placeholder="optional"
            />
          </div>
          <p className="text-xs text-tertiary">
            Cost basis defaults to <code>last_price × quantity</code> if left blank.
            Account balance is recomputed automatically when this holding lands.
          </p>
          {addError && (
            <p className="text-sm text-danger" role="alert" data-testid="add-holding-error">
              {addError}
            </p>
          )}
        </form>
      </Modal>

      {/* ============================================================
          Phase 47 — Edit modal (mirrors Add modal layout, no Account)
          ============================================================
          Same Input/Select layout as the Add Holding modal minus the
          Account picker (a cross-account migration is a future
          "Transfer" affordance). ``current_value`` is omitted from the
          FE payload — the BE route auto-derives it when BOTH quantity
          AND last_price land in the patch, so sending it would invite
          the FE to do arithmetic the BE can do better. The footer
          button uses ``type="submit" form="edit-holding-form"`` so the
          form (which lives INSIDE the modal, not adjacent to its
          footer button) submits via the standard HTML form contract
          and the Modal layout stays clean. */}
      <Modal
        open={editHolding !== null}
        onClose={() => {
          if (!editSubmitting) resetEditForm()
        }}
        title={
          editHolding
            ? `Edit holding — ${editHolding.symbol ?? '(no symbol)'}`
            : 'Edit holding'
        }
        size="md"
        footer={
          <>
            <Button variant="tertiary" onClick={resetEditForm} disabled={editSubmitting}>
              Cancel
            </Button>
            <button
              type="submit"
              form="edit-holding-form"
              disabled={editSubmitting}
              data-testid="edit-holding-submit"
              className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg font-medium bg-[var(--primary-500)] text-[var(--text-on-brand)] hover:bg-[var(--primary-600)] active:bg-[var(--primary-700)] disabled:bg-[var(--slate-400)] transition-all duration-150 disabled:cursor-not-allowed"
            >
              {editSubmitting && (
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
              )}
              {editSubmitting ? 'Saving…' : 'Save changes'}
            </button>
          </>
        }
      >
        <form id="edit-holding-form" onSubmit={submitEditHolding} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Symbol"
              value={editSymbol}
              onChange={(e) => setEditSymbol(e.target.value)}
              placeholder="AAPL"
              required
            />
            <Select
              label="Type"
              value={editType}
              onChange={(e) => setEditType(e.target.value)}
              options={HOLDING_TYPE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
            />
          </div>
          <Input
            label="Description (optional)"
            value={editDescription}
            onChange={(e) => setEditDescription(e.target.value)}
            placeholder="Apple Inc."
          />
          <div className="grid grid-cols-3 gap-4">
            <Input
              label="Quantity"
              type="number"
              value={editQuantity}
              onChange={(e) => setEditQuantity(e.target.value)}
              placeholder="10"
              required
            />
            <Input
              label="Last price"
              type="number"
              value={editLastPrice}
              onChange={(e) => setEditLastPrice(e.target.value)}
              placeholder="175.00"
            />
            <Input
              label="Cost basis"
              type="number"
              value={editCostBasis}
              onChange={(e) => setEditCostBasis(e.target.value)}
              placeholder="optional"
            />
          </div>
          <p className="text-xs text-tertiary">
            Server auto-derives position value as <code>last price × quantity</code>{' '}
            when both are updated. The parent account&apos;s balance is recomputed
            when the patch lands.
          </p>
          {editError && (
            <p
              className="text-sm text-danger"
              role="alert"
              data-testid="edit-holding-error"
            >
              {editError}
            </p>
          )}
        </form>
      </Modal>

      {/* ============================================================
          Phase 47 — Delete confirm modal
          ============================================================
          Mirrors the destructive-action pattern used on the Settings
          page — soft copy, no-recovery warning. The row summary
          echoes the SPECIFIC position so the user can verify they're
          deleting the right thing (vs. a generic "Are you sure?"
          which leads to the classic clicked-the-wrong-row support
          ticket). Cancel closes without firing the API; the footer
          Delete button is the ONLY path that commits the destroy. */}
      <Modal
        open={deleteHoldingRow !== null}
        onClose={() => {
          if (!deleteSubmitting) setDeleteHoldingRow(null)
        }}
        title="Delete holding?"
        size="md"
        footer={
          <>
            <Button
              variant="tertiary"
              onClick={() => setDeleteHoldingRow(null)}
              disabled={deleteSubmitting}
            >
              Cancel
            </Button>
            <button
              type="button"
              onClick={submitDeleteHolding}
              disabled={deleteSubmitting}
              data-testid="delete-holding-confirm"
              className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg font-medium bg-[var(--danger-600)] text-[var(--text-on-brand)] hover:bg-[var(--danger-700)] active:bg-[var(--danger-800)] disabled:bg-[var(--slate-400)] transition-all duration-150 disabled:cursor-not-allowed"
            >
              {deleteSubmitting && (
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
              )}
              {deleteSubmitting ? 'Deleting…' : 'Delete holding'}
            </button>
          </>
        }
      >
        <div className="space-y-4" data-testid="delete-holding-modal">
          <p className="text-sm">
            This permanently removes the position from your portfolio. The
            parent account&apos;s balance is recomputed after the row is gone —
            there is no undo.
          </p>
          {deleteHoldingRow && (
            <div className="card p-4 bg-[var(--bg-secondary)] space-y-2 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="text-tertiary uppercase label-xs tracking-wider">
                  Symbol
                </span>
                <span className="font-mono font-semibold text-primary">
                  {deleteHoldingRow.symbol ?? '—'}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-tertiary uppercase label-xs tracking-wider">
                  Description
                </span>
                <span
                  className="text-secondary truncate max-w-[16rem]"
                  title={deleteHoldingRow.description || ''}
                >
                  {deleteHoldingRow.description || '—'}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-tertiary uppercase label-xs tracking-wider">
                  Shares
                </span>
                <span className="font-mono text-secondary">
                  {deleteHoldingRow.quantity != null
                    ? deleteHoldingRow.quantity.toLocaleString('en-US', {
                        maximumFractionDigits: 4,
                      })
                    : '—'}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-tertiary uppercase label-xs tracking-wider">
                  Value
                </span>
                <span className="font-mono font-semibold text-primary">
                  {(deleteHoldingRow.live_value ?? deleteHoldingRow.current_value ?? 0)
                    .toLocaleString('en-US', {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                </span>
              </div>
            </div>
          )}
          {deleteError && (
            <p
              className="text-sm text-danger"
              role="alert"
              data-testid="delete-holding-error"
            >
              {deleteError}
            </p>
          )}
        </div>
      </Modal>

      {/* ============================================================
          Phase 41 — Analyze drawer (right-side modal)
          ============================================================ */}
      <Modal
        open={analyzingHolding !== null}
        onClose={closeAnalyze}
        title={
          analyzingHolding?.symbol
            ? `Analyst Consensus — ${analyzingHolding.symbol}`
            : 'Analyst Consensus'
        }
        size="md"
        footer={
          <Button variant="tertiary" onClick={closeAnalyze}>
            Close
          </Button>
        }
      >
        <AnalyzeContent
          symbol={analyzingHolding?.symbol ?? ''}
          ratings={analyzingHolding?.symbol ? ratingsByTicker[analyzingHolding.symbol.toUpperCase()] : undefined}
          consensusColors={consensusColors}
        />
      </Modal>
      </AtlasFilterProvider>
    </PageLayout>
  )
}

/**
 * Phase 42 — per-row analyst consensus chip.
 *
 * Renders ONE pill next to the symbol on every holdings row, color-
 * coded by the dominant sentiment across the last 4 reported months.
 * Mirrors the math the AnalystCoverage card uses so the two views
 * never disagree.
 *
 * Three rendering states:
 *   - **``undefined`` cache entry** (symbol not in top-10 fetched
 *     cohort): render nothing — the user can still click the row's
 *     Analyze button to lazy-load the missing ticker. Firing a chip
 *     here would say "0 ratings" for every non-top-10 row which is
 *     either misleading (\"this ticker truly has no coverage\") or
 *     premature (\"we just haven't asked yet\").
 *   - **state='loading'**: tiny spinner pill so the user sees a
 *     visible sub-second ETA cue.
 *   - **state='ok'**: dominant-bucket summary, factor-weighted
 *     (``strongBuy`` and ``strongSell`` count double so an outlier
 *     opinion doesn't get washed out by a neutral consensus, SELL
 *     counts 1.5× so a tracking-downgrade gets visible weight).
 *   - **state='error'**: gray \"Uncovered\" pill — Finnhub returned
 *     a per-ticker error (400 invalid, 403 forbidden, 502 upstream).
 *     The user-facing detail string is in the title attribute so
 *     hover-tap reveals the real cause (e.g. \"Forbidden -- free
 *     tier restriction\").
 *
 * ``ratingsByTicker`` is passed as a prop so the component stays
 * pure (testable on its own) and shares React's `Record`-keyed
 * cache with the parent page's batch + lazy-fetch paths.
 */
/** Asset classes that Finnhub does NOT cover with sell-side analyst
 *  consensus. Showing "Uncovered" for these is misleading — the user
 *  might think the system failed. Instead we show the asset class with
 *  "no analyst consensus" so they understand it's expected. */
function noCoverageLabel(type: string | null | undefined): string | null {
  if (!type) return null
  const t = type.toLowerCase()
  if (t === 'etf') return 'ETF (no consensus)'
  if (t === 'mutual fund') return 'Fund (no consensus)'
  if (t === 'bond') return 'Bond (no consensus)'
  if (t === 'crypto') return 'Crypto (no consensus)'
  if (t === 'cash') return null  // Cash rows are excluded from batch entirely
  return null
}

function RatingsChip({
  symbol,
  ratingsByTicker,
  holdingType,
}: {
  symbol: string
  ratingsByTicker: Record<
    string,
    | { state: 'loading' }
    | { state: 'ok'; data: Awaited<ReturnType<typeof rulesService.getAnalystRatings>> }
    | { state: 'error'; message: string }
  >
  holdingType?: string | null
}) {
  const entry = ratingsByTicker[symbol]
  if (!entry) return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider text-tertiary"
      title={`${symbol}: ratings not yet fetched`}
      data-testid={`ratings-chip-pending-${symbol}`}
    >
      —
    </span>
  )
  if (entry.state === 'loading') {
    return (
      <span
        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider bg-[var(--bg-tertiary)] text-tertiary"
        title={`Loading analyst consensus for ${symbol}…`}
        data-testid={`ratings-chip-loading-${symbol}`}
      >
        <Loader2 className="w-2.5 h-2.5 animate-spin" aria-hidden="true" />
        Loading
      </span>
    )
  }
  if (entry.state === 'error') {
    const assetLabel = noCoverageLabel(holdingType)
    return (
      <span
        className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider bg-[var(--bg-tertiary)] text-tertiary border border-[var(--border-subtle)]"
        title={assetLabel ? `${symbol}: ${holdingType} — Finnhub does not provide analyst consensus for this asset class` : `${symbol}: ${entry.message}`}
        data-testid={`ratings-chip-error-${symbol}`}
      >
        {assetLabel ?? 'Uncovered'}
      </span>
    )
  }
  // state === 'ok': compute the dominant bucket across the most-recent
  // 4 months. Same slice+reverse order as the drawer so the chip and
  // the drawer visually agree on what \"Strong Buy\" means.
  const trends = entry.data.recommendation_trends ?? []
  const months4 = trends.slice(0, 4).reverse()
  if (months4.length === 0) {
    const assetLabel = noCoverageLabel(holdingType)
    return (
      <span
        className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider bg-[var(--bg-tertiary)] text-tertiary border border-[var(--border-subtle)]"
        title={assetLabel ? `${symbol}: ${holdingType} — no analyst consensus available` : `${symbol}: no consensus yet`}
        data-testid={`ratings-chip-empty-${symbol}`}
      >
        {assetLabel ?? 'Uncovered'}
      </span>
    )
  }
  const aggregate = months4.reduce(
    (acc, t) => ({
      strongBuy: acc.strongBuy + (t.strongBuy ?? 0),
      buy: acc.buy + (t.buy ?? 0),
      hold: acc.hold + (t.hold ?? 0),
      sell: acc.sell + (t.sell ?? 0),
      strongSell: acc.strongSell + (t.strongSell ?? 0),
    }),
    { strongBuy: 0, buy: 0, hold: 0, sell: 0, strongSell: 0 },
  )
  const total =
    aggregate.strongBuy +
    aggregate.buy +
    aggregate.hold +
    aggregate.sell +
    aggregate.strongSell
  // Weighted-vote dominant — mirrors the drawer logic exactly so the
  // two views are pixel-identical on the dominant bucket choice.
  const weighted = {
    strongBuy: aggregate.strongBuy * 2,
    buy: aggregate.buy,
    hold: aggregate.hold,
    sell: aggregate.sell * 1.5,
    strongSell: aggregate.strongSell * 2,
  }
  const dominant = (
    Object.entries(weighted) as Array<[keyof typeof weighted, number]>
  ).reduce((a, b) => (a[1] > b[1] ? a : b))[0]
  const count = aggregate[dominant]
  const labelMap: Record<keyof typeof weighted, string> = {
    strongBuy: 'Strong Buy',
    buy: 'Buy',
    hold: 'Hold',
    sell: 'Sell',
    strongSell: 'Strong Sell',
  }
  const colorMap: Record<keyof typeof weighted, string> = {
    strongBuy: 'bg-[var(--success-50)] text-[var(--success-700)] border-[var(--success-200)]',
    buy: 'bg-[var(--success-50)] text-[var(--success-600)] border-[var(--success-200)]',
    hold: 'bg-[var(--bg-tertiary)] text-tertiary border-[var(--border-subtle)]',
    sell: 'bg-[var(--warning-50)] text-[var(--warning-700)] border-[var(--warning-200)]',
    strongSell: 'bg-[var(--danger-50)] text-[var(--danger-700)] border-[var(--danger-200)]',
  }
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider border ${colorMap[dominant]}`}
      title={`${count} ${labelMap[dominant]} (weighted) across ${total} reports in last ${months4.length} months. Click Analyze for the full monthly breakdown.`}
      data-testid={`ratings-chip-${symbol}`}
    >
      {count} {labelMap[dominant]}
    </span>
  )
}

/**
 * Phase 41 — content of the Analyze drawer. Renders either a
 * loading skeleton, an error banner, or the analyst_trends +
 * price_target block from the existing `getAnalystRatings` endpoint.
 */
function AnalyzeContent({
  symbol,
  ratings,
  consensusColors,
}: {
  symbol: string
  ratings:
    | { state: 'loading' }
    | { state: 'ok'; data: Awaited<ReturnType<typeof rulesService.getAnalystRatings>> }
    | { state: 'error'; message: string }
    | undefined
  consensusColors: {
    strongBuy: string
    buy: string
    hold: string
    sell: string
    strongSell: string
  }
}) {
  if (!symbol) return null
  if (!ratings || ratings.state === 'loading') {
    return (
      <div className="space-y-3" data-testid="ratings-loading">
        <div className="flex items-center gap-2 text-tertiary text-sm">
          <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
          Fetching consensus for {symbol}…
        </div>
        <div className="skeleton h-24 w-full" />
        <div className="skeleton h-24 w-full" />
      </div>
    )
  }
  if (ratings.state === 'error') {
    return (
      <div
        className="p-4 rounded-md border bg-[var(--danger-50)] border-[var(--danger-200)] text-[var(--danger-700)] text-sm"
        data-testid="ratings-error"
      >
        ⚠️ {ratings.message}
      </div>
    )
  }
  const data = ratings.data
  const trends = data.recommendation_trends ?? []
  const pt = data.price_target
  const consensusMonths = trends.slice(0, 4).reverse()
  const trendMax = consensusMonths.reduce(
    (m, t) =>
      Math.max(
        m,
        (t.strongBuy ?? 0) + (t.buy ?? 0) + (t.hold ?? 0) + (t.sell ?? 0) + (t.strongSell ?? 0)
      ),
    1
  )
  // Compute aggregate consensus across the 4 most recent months.
  const aggregate = consensusMonths.reduce(
    (acc, t) => ({
      strongBuy: acc.strongBuy + (t.strongBuy ?? 0),
      buy: acc.buy + (t.buy ?? 0),
      hold: acc.hold + (t.hold ?? 0),
      sell: acc.sell + (t.sell ?? 0),
      strongSell: acc.strongSell + (t.strongSell ?? 0),
    }),
    { strongBuy: 0, buy: 0, hold: 0, sell: 0, strongSell: 0 }
  )
  const aggregateTotal =
    aggregate.strongBuy + aggregate.buy + aggregate.hold + aggregate.sell + aggregate.strongSell
  // Empty-state guard: when Finnhub returns 0 recommendations for
  // a symbol (un-covered ticker, OTC, brand-new listing), the bar
  // legend would still render five "0 count" rows which is
  // misleading. Show an honest empty card instead.
  if (aggregateTotal === 0 && consensusMonths.length === 0) {
    return (
      <div className="p-6 text-center text-sm text-tertiary" data-testid="ratings-empty">
        No analyst coverage found for <strong>{symbol}</strong> yet.
        <br />
        The consensus will appear here once sell-side analysts publish a rating.
      </div>
    )
  }
  const aggregateTotalSafe = aggregateTotal || 1
  const dominant =
    aggregate.strongBuy >= aggregate.buy ? 'strongBuy' : 'buy'
  return (
    <div className="space-y-5" data-testid={`ratings-${symbol}`}>
      <div className="grid grid-cols-5 gap-2">
        <AnimatedRadialProgress
          percentage={(aggregate.strongBuy / aggregateTotalSafe) * 100}
          size={48}
          strokeWidth={5}
          color={consensusColors.strongBuy}
          trackColor="var(--bg-tertiary)"
          label={<span className="text-[10px] font-mono font-semibold text-[var(--success-700)]">{aggregate.strongBuy}</span>}
        />
        <AnimatedRadialProgress
          percentage={(aggregate.buy / aggregateTotalSafe) * 100}
          size={48}
          strokeWidth={5}
          color={consensusColors.buy}
          trackColor="var(--bg-tertiary)"
          label={<span className="text-[10px] font-mono font-semibold text-[var(--success-600)]">{aggregate.buy}</span>}
        />
        <AnimatedRadialProgress
          percentage={(aggregate.hold / aggregateTotalSafe) * 100}
          size={48}
          strokeWidth={5}
          color={consensusColors.hold}
          trackColor="var(--bg-tertiary)"
          label={<span className="text-[10px] font-mono font-semibold text-tertiary">{aggregate.hold}</span>}
        />
        <AnimatedRadialProgress
          percentage={(aggregate.sell / aggregateTotalSafe) * 100}
          size={48}
          strokeWidth={5}
          color={consensusColors.sell}
          trackColor="var(--bg-tertiary)"
          label={<span className="text-[10px] font-mono font-semibold text-[var(--warning-700)]">{aggregate.sell}</span>}
        />
        <AnimatedRadialProgress
          percentage={(aggregate.strongSell / aggregateTotalSafe) * 100}
          size={48}
          strokeWidth={5}
          color={consensusColors.strongSell}
          trackColor="var(--bg-tertiary)"
          label={<span className="text-[10px] font-mono font-semibold text-[var(--danger-700)]">{aggregate.strongSell}</span>}
        />
      </div>
      <p className="text-xs text-tertiary">
        Aggregate of last {consensusMonths.length} reported months:{' '}
        <span className="font-mono text-[var(--success-700)]">{aggregate.strongBuy} Strong Buy</span> ·{' '}
        <span className="font-mono text-[var(--success-600)]">{aggregate.buy} Buy</span> ·{' '}
        <span className="font-mono">{aggregate.hold} Hold</span> ·{' '}
        <span className="font-mono text-[var(--warning-700)]">{aggregate.sell} Sell</span> ·{' '}
        <span className="font-mono text-[var(--danger-700)]">{aggregate.strongSell} Strong Sell</span>
      </p>

      {consensusMonths.length > 0 && (
        <div>
          <p className="label-sm uppercase tracking-wider text-tertiary mb-2">Trend (last {consensusMonths.length} months)</p>
          <div className="space-y-2">
            {consensusMonths.map((t, idx) => {
              const total =
                (t.strongBuy ?? 0) + (t.buy ?? 0) + (t.hold ?? 0) + (t.sell ?? 0) + (t.strongSell ?? 0) || 1
              return (
                <div key={idx} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-mono text-tertiary">{t.period}</span>
                    <span className="text-tertiary">{total} reports</span>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <AnimatedRadialProgress
                      percentage={Math.min(100, ((t.strongBuy ?? 0) / trendMax) * 100)}
                      size={32}
                      strokeWidth={4}
                      color={consensusColors.strongBuy}
                      trackColor="var(--bg-tertiary)"
                      label={<span className="text-[8px] font-mono font-semibold text-[var(--success-700)]">{t.strongBuy ?? 0}</span>}
                    />
                    <AnimatedRadialProgress
                      percentage={Math.min(100, ((t.buy ?? 0) / trendMax) * 100)}
                      size={32}
                      strokeWidth={4}
                      color={consensusColors.buy}
                      trackColor="var(--bg-tertiary)"
                      label={<span className="text-[8px] font-mono font-semibold text-[var(--success-600)]">{t.buy ?? 0}</span>}
                    />
                    <AnimatedRadialProgress
                      percentage={Math.min(100, ((t.hold ?? 0) / trendMax) * 100)}
                      size={32}
                      strokeWidth={4}
                      color={consensusColors.hold}
                      trackColor="var(--bg-tertiary)"
                      label={<span className="text-[8px] font-mono font-semibold text-tertiary">{t.hold ?? 0}</span>}
                    />
                    <AnimatedRadialProgress
                      percentage={Math.min(100, ((t.sell ?? 0) / trendMax) * 100)}
                      size={32}
                      strokeWidth={4}
                      color={consensusColors.sell}
                      trackColor="var(--bg-tertiary)"
                      label={<span className="text-[8px] font-mono font-semibold text-[var(--warning-700)]">{t.sell ?? 0}</span>}
                    />
                    <AnimatedRadialProgress
                      percentage={Math.min(100, ((t.strongSell ?? 0) / trendMax) * 100)}
                      size={32}
                      strokeWidth={4}
                      color={consensusColors.strongSell}
                      trackColor="var(--bg-tertiary)"
                      label={<span className="text-[8px] font-mono font-semibold text-[var(--danger-700)]">{t.strongSell ?? 0}</span>}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {pt ? (
        <div className="card p-4 bg-[var(--bg-secondary)]">
          <p className="label-sm uppercase tracking-wider text-tertiary mb-2">Price Target</p>
          <div className="grid grid-cols-4 gap-3">
            <div>
              <p className="text-[10px] text-tertiary uppercase">Low</p>
              <p className="numeric-md text-[var(--danger-600)]">{pt.targetLow?.toFixed(2) ?? '—'}</p>
            </div>
            <div>
              <p className="text-[10px] text-tertiary uppercase">Mean</p>
              <p className="numeric-md text-[var(--text-primary)] font-bold">{pt.targetMean?.toFixed(2) ?? '—'}</p>
            </div>
            <div>
              <p className="text-[10px] text-tertiary uppercase">Median</p>
              <p className="numeric-md text-primary">{pt.targetMedian?.toFixed(2) ?? '—'}</p>
            </div>
            <div>
              <p className="text-[10px] text-tertiary uppercase">High</p>
              <p className="numeric-md text-[var(--success-600)]">{pt.targetHigh?.toFixed(2) ?? '—'}</p>
            </div>
          </div>
          <p className="text-[11px] text-tertiary mt-2">
            Dominant signal:{' '}
            <span className="font-semibold text-[var(--success-700)]">
              {dominant === 'strongBuy' ? 'Strong Buy' : 'Buy'}
            </span>
          </p>
        </div>
      ) : (
        <div className="card p-4 bg-[var(--bg-secondary)] text-sm text-tertiary">
          No price target consensus available for {symbol}.
        </div>
      )}
    </div>
  )
}
