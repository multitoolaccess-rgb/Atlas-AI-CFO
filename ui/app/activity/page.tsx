'use client'

import { useEffect, useState, useMemo, useCallback, useRef } from 'react'
import {
  ArrowDownRight,
  ArrowUpRight,
  Clock,
  Filter,
  Plus,
  Search,
  RefreshCw,
  Sparkles,
  ArrowDownAZ,
  ArrowUpAZ,
  Tag,
  Wand2,
  X,
  CheckCircle2,
  AlertTriangle,
  Database,
  Copy,
  ShieldCheck,
  ShieldX,
  ShieldAlert,
} from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'
import { AtlasFilterProvider, useAtlasFilters, dateRangeFromPreset } from '@/components/ui/AtlasFilterContext'
import FloatingTimeRangeBar from '@/components/ui/FloatingTimeRangeBar'
import ErrorBanner from '@/components/ui/ErrorBanner'
import EmptyState from '@/components/ui/EmptyState'
import PageHeader from '@/components/ui/PageHeader'
import { useEmbeddedMoneyView } from '@/components/money/EmbeddedMoneyView'
import { Select, Button, CategoryDot } from '@/components/ui'
import {
  rulesService,
  type Transaction,
  type Account,
  type Category,
  classifyCashflow,
  CREDIT_ACCOUNT_TYPES,
} from '@/lib/api'
import { onDataRefresh, fireDataRefresh } from '@/lib/dataRefresh'
import {
  computeBookkeepingTotals,
  formatBookkeepingCell,
} from '@/lib/bookkeeping'

// =============================================================
// Phase 11 activity page rewrite — fixes the user's 4 complaints:
//   1) Per-account filter shows nothing  -> missing account_id
//      on TransactionResponse. Fixed server-side; this component
//      now filters by account_id, supports grouping by account_type
//      (a separate filter), and renders rich rows.
//   2) Account-TYPE filter              -> Added. Distinct from
//      the per-account select so the user can pull "all credit
//      cards" without picking each one.
//   3) Add filter + sort options         -> Date range, category,
//      status (pending/completed), search, sort direction, plus
//      the existing account filter. All params go server-side
//      (no client-side post-processing of a giant payload).
//   4) Auto categorize all transactions  -> Bulk button calling
//      POST /api/transactions/categorize. Shows a per-toast
//      of "tagged N of M" inline.
// =============================================================

type SortBy = 'transaction_date' | 'amount' | 'description'
type SortDir = 'asc' | 'desc'
// Phase 28 — added 'untagged' so the activity page can pull every
// row with ``category_id IS NULL`` in one round-trip. Maps to the
// new ``?uncategorized=true`` Query param on ``GET /api/transactions/``.
// The previous design forced a user wanting to see all rows that
// could be promoted to a rule to either (a) scan the whole list
// visually, or (b) trigger the AI auto-tag button (which is a
// side-effecting call, not a filter).
type StatusFilter = 'all' | 'completed' | 'pending' | 'untagged' | 'duplicate' | 'credit_only' | 'debit_only'

function formatAmount(amount: number): { display: string; positive: boolean } {
  const positive = amount > 0
  return {
    positive,
    display:
      (positive ? '+' : '−') +
      Math.abs(amount).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
  }
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  } catch {
    return String(iso)
  }
}

// Distinct account TYPES observed across the loaded accounts (alpha-sorted).
// Used to populate the Account-type filter so picking "Credit" pulls
// every credit-card account the user owns without the user having to
// know the underlying account ids.
function useDistinctAccountTypes(accounts: Account[]): string[] {
  return useMemo(() => {
    const seen = new Set<string>()
    for (const a of accounts) {
      const t = (a.account_type || '').trim()
      if (t) seen.add(t.toLowerCase())
    }
    return Array.from(seen).sort()
  }, [accounts])
}

// Phase D — category options grouped by category group for better UX.
// Categories are sorted within each group so the dropdown reads
// Income → [Base Salary, Interest Earned, ...], Expenses → [Housing, ...], etc.
const CATEGORY_GROUP_ORDER = ['Income', 'Expenses', 'Debt', 'Investments', 'Transfer'] as const

function ActivityContent({ embedded = false }: { embedded?: boolean }) {
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [filterAccount, setFilterAccount] = useState<string>('all')
  const [filterAccountType, setFilterAccountType] = useState<string>('all')
  const [filterCategory, setFilterCategory] = useState<string>('all')
  const [filterStatus, setFilterStatus] = useState<StatusFilter>('all')
  const { timeRange } = useAtlasFilters()
  const initialRange = dateRangeFromPreset(timeRange)
  const [dateFrom, setDateFrom] = useState<string>(initialRange.from)
  const [dateTo, setDateTo] = useState<string>(initialRange.to)
  const [search, setSearch] = useState<string>('')
  // Sync floating bar's preset into the local date filters so the
  // listTransactions query fires with the right from/to range.
  useEffect(() => {
    if (!timeRange) return
    const { from, to } = dateRangeFromPreset(timeRange)
    setDateFrom(from)
    setDateTo(to)
  }, [timeRange])
  const [sortBy, setSortBy] = useState<SortBy>('transaction_date')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)
  const [autoTagMessage, setAutoTagMessage] = useState<string | null>(null)
  const [autoTagging, setAutoTagging] = useState(false)
  const [perRowEditingId, setPerRowEditingId] = useState<number | null>(null)
  // ---- Phase 54+ — duplicate resolution state --------------------
  const duplicateRows = useMemo(
    () => transactions.filter((t) => t.is_duplicate),
    [transactions],
  )
  const [dupResolving, setDupResolving] = useState(false)
  const [dupMessage, setDupMessage] = useState<string | null>(null)
  const [resolvingId, setResolvingId] = useState<number | null>(null)
  // Phase 4 — client-side pagination for the transaction table.
  // Keeps the DOM light for large datasets (1000+ rows) without
  // requiring a virtualization library. 50 rows per page by default.
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 50

  // Compute which transaction IDs are "originals" — i.e. other
  // transactions point TO them via duplicate_of_id. These get an
  // "Original" badge so the user can see the pairing.
  const originalIds = useMemo(() => {
    const ids = new Set<number>()
    for (const t of duplicateRows) {
      if (t.duplicate_of_id) ids.add(t.duplicate_of_id)
    }
    return ids
  }, [duplicateRows])
  // ---- Phase 22: LLM Pass-4 state ----------------------------------
  // The panel is OPEN-cued by the user's click on the toolbar button;
  // suggestions stay rendered until the user Closes, Rejects, or
  // Accepts every row. ``llmSuggestions`` is intentionally separate
  // from the main ``transactions`` array — Accept commits the
  // category via updateTransaction (which mutates ``transactions``),
  // but the panel keeps a memoised snapshot until the user
  // explicitly clears it so mid-stream dismissals don't lose work.
  const [llmPanelOpen, setLlmPanelOpen] = useState(false)
  const [llmLoading, setLlmLoading] = useState(false)
  const [llmError, setLlmError] = useState<string | null>(null)
  const [llmSuggestions, setLlmSuggestions] = useState<
    Array<{
      txn_id: number
      suggested_category: string
      confidence: number
      coerced?: boolean
      cached?: boolean
      // Phase 30h — new-category proposal rows.
      is_new?: boolean
      proposed_category?: string | null
      proposed_parent?: string | null
    }>
  >([])
  const [llmBulkApplying, setLlmBulkApplying] = useState(false)
  const [perLlmAcceptingIds, setPerLlmAcceptingIds] = useState<Set<number>>(
    () => new Set(),
  )

  // Compute the untagged set once per filter mutation. The AI
  // bancker button is disabled when ``untaggedRows`` is empty so
  // a user with zero pending rows never wastes an Ollama round-trip.
  const untaggedRows = useMemo(
    () => transactions.filter((t) => !t.category_id),
    [transactions],
  )

  // Client-side post-filter: when the status filter is "duplicate",
  // we let the backend return all rows (no special server param) and
  // filter locally to show BOTH duplicates AND their originals so the
  // user can see the pairing side-by-side and take action on either.
  const displayTransactions = useMemo(() => {
    if (filterStatus === 'duplicate') {
      // Reuse the component-level originalIds (already computed from
      // duplicateRows) to avoid redundant iteration.
      return transactions.filter(
        (t) => t.is_duplicate || originalIds.has(t.id),
      )
    }
    if (filterStatus === 'credit_only') {
      // Show only transactions that have a populated credit column
      // (payments, refunds — money coming in or debt decreasing).
      return transactions.filter((t) => t.credit != null && t.credit > 0)
    }
    if (filterStatus === 'debit_only') {
      // Show only transactions that have a populated debit column
      // (charges, purchases — money going out or debt increasing).
      return transactions.filter((t) => t.debit != null && t.debit > 0)
    }
    return transactions
  }, [transactions, filterStatus, originalIds])

  // Reset page when the underlying data changes
  useEffect(() => { setPage(0) }, [displayTransactions.length])

  // Build the listTransactions query envelope from the current filter
  // state. Memoized so load doesn't rebuild on unrelated renders.
  const queryParams = useMemo(() => {
    const params: Record<string, unknown> = {
      sort_by: sortBy,
      sort_dir: sortDir,
      limit: 10000,
    }
    if (filterAccount !== 'all') params.account_id = Number(filterAccount)
    if (filterAccountType !== 'all') params.account_type = filterAccountType
    // Phase 30 — either the status filter OR the category filter can
    // surface untagged rows. When either is 'untagged', we send
    // ``uncategorized=true`` (``category_id IS NULL``) and drop
    // ``category_id`` + ``is_pending`` (untagged rows have no
    // meaningful completed/pending status). The status-filter path
    // (Phase 28) and the category-filter path (Phase 30) are
    // symmetric — both produce the same query-param envelope.
    const isUntagged =
      filterStatus === 'untagged' || filterCategory === 'untagged'
    if (isUntagged) {
      params.uncategorized = true
    } else if (filterStatus === 'all' || filterStatus === 'completed' || filterStatus === 'pending') {
      if (filterCategory !== 'all') params.category_id = Number(filterCategory)
      if (filterStatus === 'completed') params.is_pending = false
      if (filterStatus === 'pending') params.is_pending = true
    } else {
      // Client-side filters (duplicate, credit_only, debit_only): let the
      // backend return all rows; filter locally in displayTransactions.
      // Still respect category filter if set.
      if (filterCategory !== 'all') params.category_id = Number(filterCategory)
    }
    if (dateFrom) params.from_date = new Date(dateFrom).toISOString()
    if (dateTo) {
      // Inclusive end-of-day so a user picking "2025-07-02" sees
      // transactions POSTED on that date instead of pre-midnight.
      const end = new Date(dateTo)
      end.setHours(23, 59, 59, 999)
      params.to_date = end.toISOString()
    }
    if (search.trim()) params.search = search.trim()
    return params
  }, [
    filterAccount,
    filterAccountType,
    filterCategory,
    filterStatus,
    dateFrom,
    dateTo,
    search,
    sortBy,
    sortDir,
  ])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [txs, accs, cats] = await Promise.all([
        rulesService.listTransactions(queryParams),
        rulesService.listAccounts(),
        rulesService.listCategories(),
      ])
      setTransactions(txs)
      setAccounts(accs)
      setCategories(cats)
      setLoading(false)
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ??
          err?.message ??
          'Failed to load transactions.',
      )
      setLoading(false)
    }
  }, [queryParams])

  // Re-fetch when any page fires a data-refresh event (upload, delete, etc.)
  useEffect(() => onDataRefresh(() => setRetryCount((c) => c + 1)), [])

  // Re-load ONLY when the filter envelope changes. retryCount is the
  // manual override (the ErrorBanner "Retry" button).
  useEffect(() => {
    let cancelled = false
    const run = async () => {
      await loadData()
      if (cancelled) return
    }
    run()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [retryCount, queryParams])

  const accountTypes = useDistinctAccountTypes(accounts)

  const accountOptions = useMemo(
    () => [
      { value: 'all', label: 'All accounts' },
      ...accounts.map((a) => ({ value: String(a.id), label: a.account_name })),
    ],
    [accounts],
  )
  const accountTypeOptions = useMemo(
    () => [
      { value: 'all', label: 'All account types' },
      ...accountTypes.map((t) => ({
        value: t,
        label: t.charAt(0).toUpperCase() + t.slice(1),
      })),
    ],
    [accountTypes],
  )
  // Phase D — category options grouped by category group for better UX.
  // Categories are sorted within each group so the dropdown reads
  // Income → [Base Salary, Interest Earned, ...], Expenses → [Housing, ...], etc.
  const categoryOptions = useMemo(() => {
    const grouped = new Map<string, Category[]>()
    for (const c of categories) {
      const g = c.group || 'Expenses'
      if (!grouped.has(g)) grouped.set(g, [])
      grouped.get(g)!.push(c)
    }
    const options: Array<{ value: string; label: string; disabled?: boolean }> = [
      { value: 'all', label: 'All categories' },
    ]
    for (const groupName of CATEGORY_GROUP_ORDER) {
      const items = grouped.get(groupName)
      if (!items || items.length === 0) continue
      items.sort((a, b) => a.name.localeCompare(b.name))
      options.push({ value: `__group_${groupName}`, label: `── ${groupName} ──`, disabled: true })
      for (const c of items) {
        options.push({ value: String(c.id), label: `  ${c.name}` })
      }
    }
    // Catch any categories not in the 5 canonical groups.
    for (const [groupName, items] of grouped) {
      if (CATEGORY_GROUP_ORDER.includes(groupName as typeof CATEGORY_GROUP_ORDER[number])) continue
      items.sort((a, b) => a.name.localeCompare(b.name))
      options.push({ value: `__group_${groupName}`, label: `── ${groupName} ──`, disabled: true })
      for (const c of items) {
        options.push({ value: String(c.id), label: `  ${c.name}` })
      }
    }
    options.push({ value: 'untagged', label: 'Untagged' })
    return options
  }, [categories])
  const statusOptions = useMemo(
    () => [
      { value: 'all', label: 'All statuses' },
      { value: 'completed', label: 'Completed' },
      { value: 'pending', label: 'Pending' },
      // Phase 28 — "Untagged" surfaces every row with
      // ``category_id IS NULL`` (the same set the Promote-to-Rule
      // button acts on). The label matches the rest of the filter
      // vocabulary; the "Uncategorized" synonym was deliberately
      // rejected because the categoriser uses "Other" as its
      // bucket name and reusing it would conflate two distinct
      // concepts.
      { value: 'untagged', label: 'Untagged' },
      { value: 'duplicate', label: `Duplicates${duplicateRows.length > 0 ? ` (${duplicateRows.length})` : ''}` },
      { value: 'credit_only', label: 'Credit only' },
      { value: 'debit_only', label: 'Debit only' },
    ],
    [duplicateRows.length],
  )
  const sortByOptions = useMemo(
    () => [
      { value: 'transaction_date', label: 'Sort: Date' },
      { value: 'amount', label: 'Sort: Amount' },
      { value: 'description', label: 'Sort: Description' },
    ],
    [],
  )

  // Phase 52+ — account-type-aware income/expense computation.
  // Uses classifyCashflow() which applies description-based payment/refund
  // detection for credit-card accounts. Purchases ARE expenses, payments
  // ARE transfers (excluded), refunds REDUCE expenses (negative expenseEffect
  // naturally lowers the total). Floor at 0 after the loop so refunds can't
  // produce negative expense totals.
  const { totalIncome, totalExpenses, netBalance } = useMemo(() => {
    let income = 0
    let expenses = 0
    let balance = 0
    for (const t of displayTransactions) {
      const cf = classifyCashflow({
        amount: t.amount,
        account_type: t.account_type ?? null,
        description: t.description ?? null,
      })
      income += cf.incomeEffect
      expenses += cf.expenseEffect
      // Net Balance uses the same formula as Portfolio Net Worth:
      // credit card balances are negated (treated as debt/liabilities)
      // so the number matches across pages.
      const acctType = (t.account_type ?? '').toLowerCase()
      balance += CREDIT_ACCOUNT_TYPES.has(acctType) ? -t.amount : t.amount
    }
    // Refunds can produce negative expenseEffect — floor at 0
    // so the display never shows negative expenses.
    return { totalIncome: income, totalExpenses: Math.max(0, expenses), netBalance: balance }
  }, [displayTransactions])

  // Phase 52+ — dual-column bookkeeping totals (charges vs payments).
  // Computed only across rows that actually carry `debit` / `credit`
  // values (credit-card statements today). Skipped silently for the
  // legacy checkings / savings rows where both columns are NULL —
  // the stripe simply does not render so the strip stays three-card.
  // Renders as a SUB-strip below the existing KPI row so a user
  // scanning top-down sees headline P&L first, then debit/credit
  // accounting detail without losing context.
  const bookkeepingTotals = useMemo(
    () => computeBookkeepingTotals(displayTransactions),
    [displayTransactions],
  )

  const handleAutoCategorize = async () => {
    setAutoTagging(true)
    setAutoTagMessage(null)
    try {
      const result = await rulesService.autoCategorizeAll()
      setAutoTagMessage(
        `Auto-tagged ${result.categorized} of ${result.total} transactions ` +
          `(${result.skipped} already tagged or no merchant match).`,
      )
      // Reload the page so every row's category column reflects the
      // new tags without the user clicking refresh.
      await loadData()
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ??
          err?.message ??
          'Auto-categorize failed.',
      )
    } finally {
      setAutoTagging(false)
    }
  }

  const handleInlineCategoryChange = async (
    txnId: number,
    newCategoryId: number | null,
  ) => {
    setPerRowEditingId(txnId)
    try {
      const updated = await rulesService.updateTransaction(txnId, {
        // 0 / negative → backend maps to NULL (detach)
        category_id: newCategoryId && newCategoryId > 0 ? newCategoryId : null,
      })
      setTransactions((prev) =>
        prev.map((t) => (t.id === txnId ? updated : t)),
      )
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ??
          err?.message ??
          'Failed to update category.',
      )
    } finally {
      setPerRowEditingId(null)
    }
  }

  // Phase — Promote to Rule. Replaces the old '+ Tag' picker:
  // a single click opens a category dropdown + 'Add new category'
  // inline mini-form; on confirm we BOTH create a MerchantRule AND
  // tag the transaction. The transaction's category_id write goes
  // through the standard PUT path so the existing Pass-1
  // ``learn_alias_for_category`` auto-runs and the txn mirrors the
  // rule's tag the moment the user commits.
  //
  // Order matters: we create the rule FIRST so a UNIQUE(category_id,
  // keyword) collision surfaces with a clean error string BEFORE we
  // commit the txn's category_id. If the rule already exists from a
  // prior promote, the BE raises 409 — we still commit the txn's
  // category_id (it's idempotent) and render a small 'rule exists'
  // notice rather than failing the whole flow.
  const handlePromoteToRule = async (
    txnId: number,
    categoryId: number,
    keyword: string,
  ) => {
    const kw = (keyword || '').trim().toUpperCase()
    if (!kw) {
      setError(
        'Cannot promote: the transaction has no merchant text to use as the rule keyword.',
      )
      return
    }
    setPerRowEditingId(txnId)
    let ruleCreated = false
    let ruleExistedAlready = false
    try {
      try {
        // Phase 27 — stamp source='tag-rule' so the Settings page's
        // Source column chip + filter pill can distinguish a
        // rule promoted from the Activity page from a Manual one
        // added directly via /settings. Without this the new rule
        // would land as 'manual' (the BE default) and the user
        // would lose the audit-trail connection "this rule came
        // from the Tag-Rule flow on row X".
        await rulesService.createMerchantRule({
          category_id: categoryId,
          keyword: kw,
          source: 'tag-rule',
        })
        ruleCreated = true
      } catch (err: any) {
        // HTTP 409 is the canonical UNIQUE(category_id, keyword) collision
        // signal from the BE. We consult the status FIRST so other 4xx
        // shapes (e.g. category-not-found 400) keep falling through to
        // the outer catch and don't get falsely classified as "rule
        // existed already". The substring fallback covers unset-status
        // (non-axios) callers (vitest mocks, older clients).
        const status =
          (err?.response?.status as number | undefined) ??
          (typeof err?.status === 'number' ? err.status : undefined)
        const detail =
          (err?.response?.data?.detail as string | undefined) ?? ''
        if (
          status === 409 ||
          (typeof detail === 'string' &&
            detail.toLowerCase().includes('already exists'))
        ) {
          ruleExistedAlready = true
        } else {
          throw err
        }
      }
      // Commit the txn's category_id regardless (idempotent).
      const updated = await rulesService.updateTransaction(txnId, {
        category_id: categoryId,
      })
      setTransactions((prev) =>
        prev.map((t) => (t.id === txnId ? updated : t)),
      )

      // Phase 31 — after creating the rule, auto-categorize ALL
      // transactions so any other rows matching the new keyword
      // get tagged immediately without the user having to switch
      // to the Activity page and click "Auto-categorize" manually.
      let autoCatMsg = ''
      try {
        const autoResult = await rulesService.autoCategorizeAll()
        if (autoResult.total > 0) {
          autoCatMsg =
            ` Auto-categorize: tagged ${autoResult.categorized} of ` +
            `${autoResult.total} (${autoResult.skipped} already tagged).`
        }
        // Reload the full list so any other rows the new rule tagged
        // surface their updated category columns without a manual refresh.
        await loadData()
      } catch {
        // Auto-categorize is a best-effort post-step; if Ollama is
        // offline or the BE returns a transient 500, the rule was
        // still created + the row was tagged. The user can run
        // auto-categorize manually from the toolbar.
        autoCatMsg = ' (auto-categorize skipped — try the toolbar button).'
      }

      if (ruleCreated) {
        setAutoTagMessage(
          `Promoted: new rule “${kw}” → ${updated.category_name ?? 'category'} and tagged this transaction.${autoCatMsg}`,
        )
      } else if (ruleExistedAlready) {
        setAutoTagMessage(
          `Tagged — rule “${kw}” already existed; tagging this transaction to match.${autoCatMsg}`,
        )
      }
      // Burst the data-refresh bus so /settings Merchant Rules
      // re-fetches the new rule on next visit.
      fireDataRefresh()
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ??
          err?.message ??
          'Failed to promote to rule.',
      )
    } finally {
      setPerRowEditingId(null)
    }
  }

  const handleResetFilters = () => {
    setFilterAccount('all')
    setFilterAccountType('all')
    setFilterCategory('all')
    setFilterStatus('all')
    setDateFrom('')
    setDateTo('')
    setSearch('')
    setSortBy('transaction_date')
    setSortDir('desc')
    setPage(0)
  }

  // ---------------------------------------------------------------
  // Phase 22 — LLM Pass-4 handlers. Invoked by the
  // “AI auto-tag” button on the toolbar; render routes the cached
  // results into the preview/accept panel that lives between the
  // filter card and the transactions table.
  // ---------------------------------------------------------------
  const handleAiCategorizeUntagged = async () => {
    if (untaggedRows.length === 0) return
    // Cap at 100 candidates (5 BE batches × 20 cap) so the FE doesn't
    // mistakenly burn a gulp of inference on a 500-row backlog. The
    // remaining rows surface in a follow-up click rather than a
    // hung-page-modal.
    const candidates = untaggedRows.slice(0, 20 * 5)
    setLlmLoading(true)
    setLlmError(null)
    setLlmPanelOpen(true)
    setLlmSuggestions([])
    try {
      const CHUNK = 20
      const all: typeof llmSuggestions = []
      for (let i = 0; i < candidates.length; i += CHUNK) {
        const chunk = candidates.slice(i, i + CHUNK).map((t) => ({
          transaction_id: t.id,
          merchant_name: t.merchant_name ?? null,
          description: t.description,
          amount: t.amount,
        }))
        const result = await rulesService.categorizeWithLlm(chunk)
        all.push(...result.suggestions)
      }
      setLlmSuggestions(all)
    } catch (err: any) {
      setLlmError(
        err?.response?.data?.detail ??
          err?.message ??
          'AI categorize failed.',
      )
    } finally {
      setLlmLoading(false)
    }
  }

  const handleAcceptLlmSuggestion = async (s: (typeof llmSuggestions)[number]) => {
    // Phase 30h — new-category proposals skip the taxonomy lookup
    // entirely (the category does not exist yet): the BE creates it
    // (+ parent) and an llm-source merchant rule, then tags the txn.
    const cat = s.is_new
      ? undefined
      : categories.find((c) => c.name === s.suggested_category)
    if (!s.is_new && !cat) {
      setLlmError(
        `Could not find category "${s.suggested_category}" in your local taxonomy. ` +
          `Click Skip to drop this suggestion.`,
      )
      return
    }
    setPerLlmAcceptingIds((prev) => {
      const next = new Set(prev)
      next.add(s.txn_id)
      return next
    })
    try {
      if (s.is_new && s.proposed_category) {
        const txn = transactions.find((t) => t.id === s.txn_id)
        const keyword = txn?.merchant_name || txn?.description || null
        await rulesService.acceptCategoryProposal({
          transaction_id: s.txn_id,
          proposed_category: s.proposed_category,
          proposed_parent: s.proposed_parent ?? null,
          keyword,
        })
        // The new category now exists — refresh the taxonomy so the
        // table's category chip + filters pick it up.
        const cats = await rulesService.listCategories()
        setCategories(cats)
      } else {
        // Also create a visible merchant rule (source='llm') so the
        // accepted categorization shows up in Settings → Merchant
        // Rules — the plain tag path only writes an invisible
        // merchant_alias (Pass 1 exact match). Mirror the
        // Promote-to-Rule keyword logic: merchant_name first, else
        // description, uppercased. A 409 UNIQUE(category_id, keyword)
        // collision means the rule already exists — that's fine, keep
        // tagging. No keyword (no merchant text at all) → skip the
        // rule, just tag.
        const txn = transactions.find((t) => t.id === s.txn_id)
        const kw = (txn?.merchant_name || txn?.description || '')
          .trim()
          .toUpperCase()
        if (kw) {
          try {
            await rulesService.createMerchantRule({
              category_id: cat!.id,
              keyword: kw,
              source: 'llm',
            })
          } catch (ruleErr: any) {
            const status =
              ruleErr?.response?.status ?? ruleErr?.status
            if (status !== 409) throw ruleErr
          }
        }
        await handleInlineCategoryChange(s.txn_id, cat!.id)
      }
      setLlmSuggestions((prev) => prev.filter((x) => x.txn_id !== s.txn_id))
    } catch (err: any) {
      setLlmError(
        err?.response?.data?.detail ??
          err?.message ??
          'Could not apply this suggestion.',
      )
    } finally {
      setPerLlmAcceptingIds((prev) => {
        const next = new Set(prev)
        next.delete(s.txn_id)
        return next
      })
    }
  }

  const handleAcceptAllLlmSuggestions = async () => {
    setLlmBulkApplying(true)
    try {
      // Sequential, NOT Promise.all — the inline handler is
      // read-modify-write against the shared `transactions` state
      // and concurrent PUTs would race the local cache. With 1k+ of
      // pending rows the button is disabled (we cap candidates at
      // 100) so a sequential loop is fine.
      for (const s of llmSuggestions) {
        await handleAcceptLlmSuggestion(s)
      }
    } finally {
      setLlmBulkApplying(false)
    }
  }

  const handleRejectLlmSuggestion = (txnId: number) => {
    setLlmSuggestions((prev) => prev.filter((s) => s.txn_id !== txnId))
  }

  const handleCloseLlmPanel = () => {
    setLlmPanelOpen(false)
    setLlmSuggestions([])
    setLlmError(null)
  }

  // Phase 54+ — per-row duplicate resolution handler.
  const handleResolveSingleDuplicate = async (
    txnId: number,
    action: 'keep_both' | 'keep_original' | 'keep_this',
  ) => {
    setResolvingId(txnId)
    try {
      const result = await rulesService.resolveDuplicate(txnId, action)
      setDupMessage(result.message)
      setTimeout(() => setDupMessage(null), 5000)
      await loadData()
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ??
          err?.message ??
          'Failed to resolve duplicate.',
      )
    } finally {
      setResolvingId(null)
    }
  }

  // Phase 54+ — bulk duplicate resolution handlers.
  const handleResolveDuplicates = async (
    action: 'keep_all' | 'keep_original' | 'keep_this',
  ) => {
    setDupResolving(true)
    setDupMessage(null)
    try {
      const result = await rulesService.resolveAllDuplicates(action)
      await loadData()
      // Clear the message after a brief delay so the user sees it
      // before the banner disappears (if all dupes resolved).
      setDupMessage(result.message)
      setTimeout(() => setDupMessage(null), 5000)
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ??
          err?.message ??
          'Failed to resolve duplicates.',
      )
    } finally {
      setDupResolving(false)
    }
  }

  // Shared categorize toolbar — rendered in the standalone page header and
  // in the embedded (Cash Flow → Transactions) view so the LLM Pass-4
  // auto-tag option stays reachable under the canonical information
  // architecture.
  const categorizeActions = (
    <div className="flex items-center gap-2">
      <Button
        type="button"
        variant="tertiary"
        size="sm"
        onClick={() => setRetryCount((c) => c + 1)}
        icon={<RefreshCw className="w-4 h-4" aria-hidden="true" />}
        data-testid="activity-refresh-button"
      >
        Refresh
      </Button>
      <Button
        type="button"
        variant="primary"
        size="sm"
        onClick={handleAutoCategorize}
        disabled={autoTagging || loading}
        icon={
          autoTagging ? (
            <RefreshCw
              className="w-4 h-4 animate-spin"
              aria-hidden="true"
            />
          ) : (
            <Sparkles className="w-4 h-4" aria-hidden="true" />
          )
        }
        data-testid="activity-auto-categorize-button"
      >
        {autoTagging ? 'Tagging…' : 'Auto-categorize'}
      </Button>
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={handleAiCategorizeUntagged}
        disabled={
          llmLoading ||
          autoTagging ||
          loading ||
          untaggedRows.length === 0
        }
        icon={
          llmLoading ? (
            <RefreshCw
              className="w-4 h-4 animate-spin"
              aria-hidden="true"
            />
          ) : (
            <Wand2 className="w-4 h-4" aria-hidden="true" />
          )
        }
        data-testid="activity-ai-categorize-button"
        title={
          untaggedRows.length === 0
            ? 'No untagged rows to send to Ollama'
            : `Send ${Math.min(untaggedRows.length, 100)} untagged ` +
              `transaction(s) to Ollama (Pass 4) for AI tagging.`
        }
      >
        {llmLoading
          ? 'Asking Ollama…'
          : untaggedRows.length === 0
            ? 'AI auto-tag (none)'
            : `AI auto-tag (${untaggedRows.length})`}
      </Button>
    </div>
  )

  return (
    <>
      {!embedded && <PageHeader
        title="Transaction History"
        description="Every recorded transaction across your accounts. Filter by account, type, category, status, or date; sort by any column."
        actions={categorizeActions}
        className="mb-6"
      />}

      {/* Floating bar — URL-synced via ?range=… (page-default YTD).
          When the user picks a preset on the bar, the effect below
          syncs the page's own dateFrom/dateTo state to match, so the
          listTransactions query fires with the right range. The
          granular From/To inputs below still work independently for
          custom date-range filtering. */}
      {!embedded && <FloatingTimeRangeBar />}

      {error && (
        // variant="warning" (amber) — page-level data-load failure
        // (transactions + accounts + categories list). Matches
        // Overview / Goals / Portfolio / Settings / Accounts.
        <ErrorBanner
          title="Couldn't load activity:"
          message={error}
          variant="warning"
          onRetry={() => setRetryCount((c) => c + 1)}
        />
      )}
      {autoTagMessage && !error && (
        <div            className="
              mb-4 p-3 rounded-lg
              bg-[var(--success-50)] text-[var(--success-700)]
              border border-[var(--success-200)]
            "
          role="status"
          data-testid="activity-auto-tag-message"
        >
          <p className="text-sm">{autoTagMessage}</p>
        </div>
      )}

      {/* Phase 54+ — duplicate resolution banner. Shows when duplicate
          transactions are detected. User can keep all, keep original,
          or keep this (delete originals). */}
      {duplicateRows.length > 0 && (
        <div                  className="
                    mb-4 p-4 rounded-lg
                    bg-[var(--warning-50)] text-[var(--warning-700)]
                    border border-[var(--warning-200)]
                  "
          role="alert"
          data-testid="activity-duplicate-banner"
        >
          <div className="flex items-start gap-3">
            <Copy className="w-5 h-5 mt-0.5 shrink-0" aria-hidden="true" />
            <div className="flex-1">
              <p className="font-semibold text-sm">
                {duplicateRows.length} likely-duplicate transaction{duplicateRows.length > 1 ? 's' : ''} detected
              </p>
              <p className="text-xs mt-1 opacity-80">
                These transactions match existing records (same amount, date, and description).
                Choose how to resolve them:
              </p>
              <div className="flex flex-wrap gap-2 mt-3">
                <Button
                  type="button"
                  variant="primary"
                  size="sm"
                  onClick={() => handleResolveDuplicates('keep_all')}
                  disabled={dupResolving}
                  icon={<ShieldCheck className="w-3.5 h-3.5" aria-hidden="true" />}
                  data-testid="activity-dup-keep-all"
                >
                  {dupResolving ? 'Resolving…' : 'Keep all (accept duplicates)'}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => handleResolveDuplicates('keep_original')}
                  disabled={dupResolving}
                  icon={<ShieldX className="w-3.5 h-3.5" aria-hidden="true" />}
                  data-testid="activity-dup-keep-original"
                >
                  {dupResolving ? 'Resolving…' : 'Keep originals only (delete duplicates)'}
                </Button>
                <Button
                  type="button"
                  variant="tertiary"
                  size="sm"
                  onClick={() => handleResolveDuplicates('keep_this')}
                  disabled={dupResolving}
                  icon={<ShieldAlert className="w-3.5 h-3.5" aria-hidden="true" />}
                  data-testid="activity-dup-keep-this"
                >
                  {dupResolving ? 'Resolving…' : 'Keep duplicates only (delete originals)'}
                </Button>
              </div>
              {dupMessage && !error && duplicateRows.length > 0 && (
                <p className="text-xs mt-2 text-[var(--success-700)]" data-testid="activity-dup-message">
                  {dupMessage}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Aggregate strip showing the user the shape of what they
          just filtered. Two counters (income / expenses) so a glance
          answers "did the filter shrink my totals correctly?" without
          firing the dashboard endpoint.
          Phase 52+ — includes a period label so the user can see at a
          glance whether they're looking at MTD (default, matches the
          Dashboard KPI strip) or a custom range. */}
      {!loading && displayTransactions.length > 0 && (
        <>
          <PeriodLabel dateFrom={dateFrom} dateTo={dateTo} rowCount={displayTransactions.length} queryLimit={10000} />
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <SummaryStat
              label="Income"
              value={totalIncome.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              tone="success"
            />
            <SummaryStat
              label="Expenses"
              value={totalExpenses.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              tone="danger"
            />
            <SummaryStat
              label="Net Worth"
              value={(netBalance >= 0 ? '+' : '−') + Math.abs(netBalance).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              tone={netBalance >= 0 ? 'success' : 'danger'}
            />
            <SummaryStat
              label="Rows"
              value={String(displayTransactions.length)}
              tone="neutral"
            />
          </div>
          {/*
            Phase 52+ — bookkeeping sub-strip. Only renders when at least
            one row carries populated debit/credit values (i.e. the filter
            surfaced credit-card activity). Gives the user a one-glance
            answer to "what did the bank charge me, what did I pay back,
            and what's the net Δ to my outstanding debt for this period?"
            without forcing a fresh /api/dashboard/summary round-trip.
          */}
          {bookkeepingTotals.populatedRows > 0 && (
            <div
              className="
                card p-3 mb-4
                bg-[var(--bg-secondary)]
                border border-outline-variant/30
              "
              data-testid="activity-bookkeeping-strip"
              role="region"
              aria-label="Bookkeeping — charges vs payments"
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="label-xs font-semibold text-tertiary">
                  Bookkeeping
                </span>
                <span
                  className="label-sm text-tertiary"
                  data-testid="activity-bookkeeping-row-count"
                >
                  ({bookkeepingTotals.populatedRows} of {displayTransactions.length} rows have debit / credit columns)
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <SummaryStat
                  label="Charges (Debit)"
                  value={bookkeepingTotals.charges.toLocaleString('en-US', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                  tone="danger"
                />
                <SummaryStat
                  label="Payments (Credit)"
                  value={bookkeepingTotals.payments.toLocaleString('en-US', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                  tone="success"
                />
                <SummaryStat
                  label="Net Δ to debt"
                  value={
                    (bookkeepingTotals.netDebtDelta >= 0 ? '+' : '−') +
                    Math.abs(bookkeepingTotals.netDebtDelta).toLocaleString('en-US', {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })
                  }
                  tone={bookkeepingTotals.netDebtDelta > 0 ? 'danger' : 'success'}
                />
              </div>
            </div>
          )}
        </>
      )}

      {/* Phase 22 — LLM preview/accept panel. Rendered between the
          title row and the filter card so the suggestions sit in
          the user's eye-line above the table. The panel is hidden
          until the user clicks the toolbar `AI auto-tag` button;
          closing the panel (via the X button or via the surrounding
          data-refresh reset) discards pending suggestions without
          committing them. */}
      {llmPanelOpen && (
        <div
          className="card p-4 mb-4"
          data-testid="activity-llm-panel"
          role="region"
          aria-label="AI tagging suggestions"
        >
          <div className="flex items-center gap-2 mb-3">
            <Wand2
              className="w-4 h-4 text-[var(--primary-600)]"
              aria-hidden="true"
            />
            <h2 className="label-md text-primary">
              AI suggestions (Pass 4 — Ollama)
            </h2>
            <span
              className="label-sm text-tertiary"
              data-testid="activity-llm-pending-count"
            >
              ({llmSuggestions.length} pending)
            </span>
            <button
              type="button"
              onClick={handleCloseLlmPanel}
              className="
                ml-auto p-1 rounded-[var(--radius-sm)]
                text-tertiary hover:text-primary hover:bg-[var(--bg-tertiary)]
                focus-visible:outline-2 focus-visible:outline-offset-2
                focus-visible:outline-[var(--primary-500)]
              "
              aria-label="Close AI suggestions panel"
              data-testid="activity-llm-panel-close"
            >
              <X className="w-4 h-4" aria-hidden="true" />
            </button>
          </div>

          {llmError && (
            <div
              className="
                mb-3 p-3 rounded-[var(--radius-md)]
                bg-[var(--warning-50)] text-[var(--warning-700)]
                border border-[var(--warning-200)]
              "
              role="alert"
              data-testid="activity-llm-error"
            >
              <p className="text-sm">{llmError}</p>
            </div>
          )}

          {llmLoading && (
            <p
              className="text-sm text-secondary flex items-center gap-2"
              data-testid="activity-llm-loading"
            >
              <RefreshCw
                className="w-4 h-4 animate-spin text-[var(--primary-600)]"
                aria-hidden="true"
              />
              Asking Ollama for Pass 4 suggestions…
            </p>
          )}

          {!llmLoading && llmSuggestions.length > 0 && (
            <>
              <div className="flex items-center gap-2 mb-3">
                <Button
                  type="button"
                  variant="primary"
                  size="sm"
                  onClick={handleAcceptAllLlmSuggestions}
                  disabled={llmBulkApplying}
                  icon={<CheckCircle2 className="w-4 h-4" aria-hidden="true" />}
                  data-testid="activity-llm-accept-all"
                >
                  {llmBulkApplying ? 'Applying…' : 'Accept all'}
                </Button>
                <span className="label-sm text-tertiary">
                  Review each preview row before applying.
                </span>
              </div>
              <ul className="space-y-2" role="list">
                {llmSuggestions.map((s) => {
                  const txn = transactions.find((t) => t.id === s.txn_id)
                  const accepting = perLlmAcceptingIds.has(s.txn_id)
                  const headline =
                    txn?.merchant_name ||
                    txn?.description ||
                    `Transaction #${s.txn_id}`
                  return (
                    <li
                      key={s.txn_id}
                      className="
                        flex items-center justify-between gap-3
                        p-3 rounded-[var(--radius-md)]
                        bg-[var(--bg-tertiary)]
                        border border-outline-variant/20
                        transition-colors duration-[var(--duration-fast)]
                      "
                      data-testid={`activity-llm-row-${s.txn_id}`}
                      role="listitem"
                    >
                      <div className="flex-1 min-w-0">
                        <p
                          className="body-md text-on-surface truncate"
                          title={headline}
                        >
                          {headline}
                        </p>
                        <div className="flex items-center gap-2 mt-1 flex-wrap">
                          <span className="label-sm text-[var(--primary-700)] font-semibold">
                            {s.suggested_category}
                          </span>
                          {s.is_new && s.proposed_category && (
                            <span
                              className="
                                inline-flex items-center gap-1
                                px-1.5 py-0.5 rounded
                                bg-[var(--primary-50)]
                                text-[var(--primary-700)]
                                text-[10px] font-semibold
                              "
                              data-testid={`activity-llm-proposal-${s.txn_id}`}
                              title={`The model proposes creating a new category "${s.proposed_category}"${s.proposed_parent ? ` under ${s.proposed_parent}` : ''}. Accept to create it + a merchant rule.`}
                            >
                              <Sparkles className="w-3 h-3" aria-hidden="true" />
                              propose new: {s.proposed_category}
                              {s.proposed_parent ? ` (under ${s.proposed_parent})` : ''}
                            </span>
                          )}
                          <span className="label-sm text-tertiary">
                            {(s.confidence * 100).toFixed(0)}% confidence
                          </span>
                          {s.coerced && (
                            <span
                            className="
                              inline-flex items-center gap-1
                              px-1.5 py-0.5 rounded
                              bg-[var(--warning-100)]
                              text-[var(--warning-700)]
                              text-[10px] font-semibold
                            "
                            data-testid={`activity-llm-coerced-${s.txn_id}`}
                            title="The model suggested a non-canonical name; the server coerced it to 'Other'."
                          >
                            <AlertTriangle
                              className="w-3 h-3"
                              aria-hidden="true"
                            />
                            needs review
                            </span>
                          )}
                          {s.cached && (
                            <span
                            className="
                              inline-flex items-center gap-1
                              px-1.5 py-0.5 rounded
                              bg-[var(--info-50)]
                              text-[var(--info-700)]
                              text-[10px] font-semibold
                            "
                            data-testid={`activity-llm-cached-${s.txn_id}`}
                            title="This row came from the 7-day in-process prompt cache; no Ollama round-trip was burned."
                          >
                            <Database
                              className="w-3 h-3"
                              aria-hidden="true"
                            />
                            cached
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          type="button"
                          onClick={() => handleRejectLlmSuggestion(s.txn_id)}
                          className="
                            px-3 py-1.5 rounded-[var(--radius-sm)]
                            text-tertiary hover:text-primary
                            label-sm underline-offset-2 hover:underline
                            focus-visible:outline-2 focus-visible:outline-offset-2
                            focus-visible:outline-[var(--primary-500)]
                          "
                          data-testid={`activity-llm-reject-${s.txn_id}`}
                        >
                          Skip
                        </button>
                        <Button
                          type="button"
                          variant="primary"
                          size="sm"
                          onClick={() => handleAcceptLlmSuggestion(s)}
                          disabled={accepting || llmBulkApplying}
                          icon={
                            accepting ? (
                              <RefreshCw
                                className="w-3 h-3 animate-spin"
                                aria-hidden="true"
                              />
                            ) : (
                              <CheckCircle2
                                className="w-3 h-3"
                                aria-hidden="true"
                              />
                            )
                          }
                          data-testid={`activity-llm-accept-${s.txn_id}`}
                        >
                          {accepting ? 'Applying…' : 'Accept'}
                        </Button>
                      </div>
                    </li>
                  )
                })}
              </ul>
            </>
          )}

          {!llmLoading && llmSuggestions.length === 0 && !llmError && (
            <p
              className="text-sm text-tertiary"
              data-testid="activity-llm-empty"
            >
              No suggestions yet. Click “Accept” on a row to apply it,
              or “Skip” to drop it.
            </p>
          )}
        </div>
      )}

      {/* Embedded toolbar — the canonical Cash Flow → Transactions view
          hides the standalone PageHeader, so surface the same categorize
          actions here to keep heuristic + LLM auto-tag reachable. */}
      {embedded && (
        <div className="card p-3 mb-4 flex flex-wrap items-center gap-2" data-testid="activity-embedded-toolbar">
          <span className="label-md text-secondary mr-auto">Categorize</span>
          {categorizeActions}
        </div>
      )}

      {/* Filter row */}
      <div className="card p-4 mb-4 space-y-3">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-[var(--text-tertiary)]" aria-hidden="true" />
          <span className="label-md text-secondary">Filters</span>
          <button
            type="button"
            onClick={handleResetFilters}
            className="ml-auto label-sm text-tertiary hover:text-primary underline-offset-2 hover:underline"
            data-testid="activity-reset-filters"
          >
            Reset all
          </button>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          <Select
            aria-label="Filter by account"
            value={filterAccount}
            onChange={(e) => setFilterAccount(e.target.value)}
            options={accountOptions}
            data-testid="activity-filter-account"
          />
          <Select
            aria-label="Filter by account type"
            value={filterAccountType}
            onChange={(e) => setFilterAccountType(e.target.value)}
            options={accountTypeOptions}
            data-testid="activity-filter-account-type"
          />
          <Select
            aria-label="Filter by category"
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
            options={categoryOptions}
            data-testid="activity-filter-category"
          />
          <Select
            aria-label="Filter by status"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value as StatusFilter)}
            options={statusOptions}
            data-testid="activity-filter-status"
          />
          <DateField
            label="From"
            value={dateFrom}
            onChange={setDateFrom}
            testId="activity-filter-date-from"
          />
          <DateField
            label="To"
            value={dateTo}
            onChange={setDateTo}
            testId="activity-filter-date-to"
          />
          <Select
            aria-label="Sort by"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortBy)}
            options={sortByOptions}
            data-testid="activity-sort-by"
          />
          <SortDirToggle value={sortDir} onChange={setSortDir} />
        </div>
        <SearchField value={search} onChange={setSearch} />
      </div>

      {loading ? (
        <p className="text-sm text-secondary">Loading transactions…</p>
      ) : displayTransactions.length === 0 ? (<EmptyState
              testId="activity-empty"
              icon={<Clock className="h-6 w-6" />}
              title={queryParams && Object.keys(queryParams).filter((k) => k !== 'sort_by' && k !== 'sort_dir' && k !== 'limit').length > 1 ? 'No matching transactions' : 'Your activity will appear here'}
              description={queryParams && Object.keys(queryParams).filter((k) => k !== 'sort_by' && k !== 'sort_dir' && k !== 'limit').length > 1 ? 'Try widening the current filters to see more of your recorded activity.' : 'Upload a statement or add an account to start building a reliable activity history.'}
              guidance={<p className="text-sm">Atlas only shows recorded source data here. It does not invent transactions when the source is empty.</p>}
            />
      ) : (
        <div
          className="card p-6"
          data-testid="activity-table"
        >
          {/* Pagination header — Phase 4 */}
          {displayTransactions.length > PAGE_SIZE && (
            <div className="flex items-center justify-between mb-3">
              <span className="label-sm text-[var(--text-tertiary)]">
                Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, displayTransactions.length)} of {displayTransactions.length}
              </span>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setPage(0)}
                  disabled={page === 0}
                  className="px-2 py-1 rounded-[var(--radius-sm)] text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  data-testid="activity-page-first"
                  aria-label="First page"
                >
                  «
                </button>
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="px-2 py-1 rounded-[var(--radius-sm)] text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  data-testid="activity-page-prev"
                  aria-label="Previous page"
                >
                  ‹
                </button>
                {Array.from({ length: Math.ceil(displayTransactions.length / PAGE_SIZE) }, (_, i) => i)
                  .filter((i) => {
                    const totalPages = Math.ceil(displayTransactions.length / PAGE_SIZE)
                    if (totalPages <= 7) return true
                    if (i === 0 || i === totalPages - 1) return true
                    return Math.abs(i - page) <= 1
                  })
                  .reduce<(number | 'ellipsis')[]>((acc, i, idx, arr) => {
                    if (idx > 0 && i - (arr[idx - 1] as number) > 1) acc.push('ellipsis')
                    acc.push(i)
                    return acc
                  }, [])
                  .map((p, idx) =>
                    p === 'ellipsis' ? (
                      <span key={`e-${idx}`} className="px-1 text-xs text-[var(--text-disabled)]">…</span>
                    ) : (
                      <button
                        key={p}
                        type="button"
                        onClick={() => setPage(p as number)}
                        className={`px-2 py-1 rounded-[var(--radius-sm)] text-xs font-medium transition-colors ${
                          p === page
                            ? 'bg-[var(--primary-500)] text-white'
                            : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'
                        }`}
                        data-testid={`activity-page-${p}`}
                        aria-label={`Page ${(p as number) + 1}`}
                        aria-current={p === page ? 'page' : undefined}
                      >
                        {(p as number) + 1}
                      </button>
                    )
                  )}
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.min(Math.ceil(displayTransactions.length / PAGE_SIZE) - 1, p + 1))}
                  disabled={page >= Math.ceil(displayTransactions.length / PAGE_SIZE) - 1}
                  className="px-2 py-1 rounded-[var(--radius-sm)] text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  data-testid="activity-page-next"
                  aria-label="Next page"
                >
                  ›
                </button>
                <button
                  type="button"
                  onClick={() => setPage(Math.ceil(displayTransactions.length / PAGE_SIZE) - 1)}
                  disabled={page >= Math.ceil(displayTransactions.length / PAGE_SIZE) - 1}
                  className="px-2 py-1 rounded-[var(--radius-sm)] text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  data-testid="activity-page-last"
                  aria-label="Last page"
                >
                  »
                </button>
              </div>
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="text-left">
                <tr className="border-b border-outline-variant/20">
                  <th className="pb-4 label-md text-[var(--text-tertiary)] text-right whitespace-nowrap">#</th>
                  <th className="pb-4 label-md text-[var(--text-tertiary)]">Description</th>
                  <th className="pb-4 label-md text-[var(--text-tertiary)]">Merchant</th>
                  <th className="pb-4 label-md text-[var(--text-tertiary)]">Account</th>
                  <th className="pb-4 label-md text-[var(--text-tertiary)]">Category</th>
                  <th
                    className="pb-4 label-md text-[var(--text-tertiary)] whitespace-nowrap"
                    title="Charge posted to the account (debt increases). Bank-statement column."
                  >
                    Debit
                  </th>
                  <th
                    className="pb-4 label-md text-[var(--text-tertiary)] whitespace-nowrap"
                    title="Payment / refund applied (debt decreases). Bank-statement column."
                  >
                    Credit
                  </th>
                  <th className="pb-4 label-md text-[var(--text-tertiary)]">Amount</th>
                  <th className="pb-4 label-md text-[var(--text-tertiary)]">Status</th>
                  <th className="pb-4 label-md text-[var(--text-tertiary)] text-right">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/10">
                {displayTransactions.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map((tx) => {
                  const { display, positive } = formatAmount(tx.amount)
                  const Icon = positive ? ArrowUpRight : ArrowDownRight
                  const {
                    debitDisplay,
                    creditDisplay,
                    populated: bookkeepingPopulated,
                  } = formatBookkeepingCell(tx.debit, tx.credit)
                  return (
                    <tr
                      key={tx.id}
                      className={`group hover:bg-[var(--slate-100)] transition-colors ${
                        // Highlight duplicate/original rows when in duplicate filter mode
                        filterStatus === 'duplicate' && tx.is_duplicate
                          ? 'bg-[var(--danger-50)]'
                          : filterStatus === 'duplicate' && originalIds.has(tx.id)
                            ? 'bg-[var(--primary-50)]'
                            : ''
                      }`}
                      data-testid={`activity-row-${tx.id}`}
                    >
                      <td className="py-4 text-right">
                        <span className="label-sm text-tertiary font-mono">
                          {tx.id}
                        </span>
                      </td>
                      <td className="py-4">
                        <span className="body-md font-semibold text-[var(--text-primary)]">
                          {tx.description}
                        </span>
                      </td>
                      <td className="py-4 body-md text-[var(--text-secondary)]">
                        {tx.merchant_name ?? '—'}
                      </td>
                      <td className="py-4 body-md text-[var(--text-secondary)]">
                        {tx.account_name ?? '—'}
                        {tx.account_type ? (
                          <span className="ml-2 label-sm text-tertiary">
                            ({tx.account_type})
                          </span>
                        ) : null}
                      </td>
                      <td className="py-4 body-md">
                        <CategoryCell
                          txnId={tx.id}
                          merchantKeyword={tx.merchant_name ?? tx.description ?? ''}
                          currentCategoryId={tx.category_id ?? null}
                          currentCategoryName={tx.category_name ?? null}
                          categories={categories}
                          isEditing={perRowEditingId === tx.id}
                          onCategoryChosen={(cid, kw) =>
                            cid === null
                              ? handleInlineCategoryChange(tx.id, null)
                              : handlePromoteToRule(
                                  tx.id,
                                  cid,
                                  kw || (tx.merchant_name ?? tx.description ?? ''),
                                )
                          }
                          onCategoryCreated={(newCat) => {
                            setCategories((prev) => {
                              if (prev.find((c) => c.id === newCat.id)) return prev
                              return [...prev, newCat]
                            })
                          }}
                        />
                      </td>
                      {/* Phase 52+ — Debit / Credit columns. We surface
                          both columns even when one side is empty so
                          the user can see the bank's native layout.
                          Debit = expense (red), Credit = payment (green)
                          — independent of the signed `Amount` to the right.
                          Rows from legacy single-column imports render
                          "—" on both sides and the eye falls back to Amount. */}
                      <td
                        className={`py-4 body-md font-mono tabular-nums whitespace-nowrap ${
                          bookkeepingPopulated && tx.debit
                            ? 'text-[var(--danger-700)] font-semibold'
                            : 'text-tertiary'
                        }`}
                        data-testid={`activity-row-${tx.id}-debit`}
                      >
                        {debitDisplay}
                      </td>
                      <td
                        className={`py-4 body-md font-mono tabular-nums whitespace-nowrap ${
                          bookkeepingPopulated && tx.credit
                            ? 'text-[var(--success-700)] font-semibold'
                            : 'text-tertiary'
                        }`}
                        data-testid={`activity-row-${tx.id}-credit`}
                      >
                        {creditDisplay}
                      </td>
                      <td
                        className={`py-4 body-md font-bold inline-flex items-center gap-1 ${
                          bookkeepingPopulated
                            ? 'text-tertiary font-normal'
                            : positive
                              ? 'text-success-600'
                              : 'text-error'
                        }`}
                        data-testid={`activity-row-${tx.id}-amount`}
                        title={
                          bookkeepingPopulated
                            ? 'Amount = Debit − Credit. Already shown in the Debit/Credit columns for this row.'
                            : 'Signed amount (legacy single-column import).'
                        }
                      >
                        {bookkeepingPopulated ? (
                          '—'
                        ) : (
                          <>
                            <Icon className="w-4 h-4" aria-hidden="true" />
                            {display}
                          </>
                        )}
                      </td>
                      <td className="py-4">
                        <div className="flex flex-col gap-1.5 items-start">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span
                              className={`px-2 py-0.5 rounded-md text-[11px] font-semibold ${
                                tx.is_pending
                                  ? 'bg-[var(--warning-100)] text-[var(--warning-700)]'
                                  : 'bg-[var(--success-50)] text-[var(--success-700)]'
                              }`}
                            >
                              {tx.is_pending ? 'Pending' : 'Completed'}
                            </span>
                            {originalIds.has(tx.id) && (
                              <span
                                className="
                                  inline-flex items-center gap-1
                                  px-1.5 py-0.5 rounded
                                  bg-[var(--primary-100)] text-[var(--primary-700)]
                                  text-[10px] font-bold uppercase tracking-wider
                                "
                                data-testid={`activity-row-${tx.id}-original`}
                                title="Original transaction — a duplicate was detected pointing to this row"
                              >
                                <ShieldCheck className="w-2.5 h-2.5" aria-hidden="true" />
                                Original
                              </span>
                            )}
                            {tx.is_duplicate && (
                              <span
                                className="
                                  inline-flex items-center gap-1
                                  px-1.5 py-0.5 rounded
                                  bg-[var(--danger-100)] text-[var(--danger-700)]
                                  text-[10px] font-bold uppercase tracking-wider
                                "
                                data-testid={`activity-row-${tx.id}-duplicate`}
                                title={tx.duplicate_of_id
                                  ? `Likely duplicate of transaction #${tx.duplicate_of_id} (same amount, date, and description)`
                                  : 'Likely duplicate — review and resolve'}
                              >
                                <Copy className="w-2.5 h-2.5" aria-hidden="true" />
                                Duplicate
                              </span>
                            )}
                          </div>
                          {tx.is_duplicate && (
                            <div
                              className="flex items-center gap-1 flex-wrap"
                              data-testid={`activity-row-${tx.id}-dup-actions`}
                            >
                              <button
                                type="button"
                                disabled={resolvingId === tx.id}
                                onClick={() => handleResolveSingleDuplicate(tx.id, 'keep_both')}
                                className="
                                  text-[9px] font-medium px-1 py-0.5 rounded
                                  text-[var(--success-700)] hover:bg-[var(--success-50)]
                                  transition-colors disabled:opacity-50
                                "
                                title="Accept both transactions as legitimate"
                                data-testid={`activity-row-${tx.id}-dup-keep-both`}
                              >
                                ✓ Keep both
                              </button>
                              <button
                                type="button"
                                disabled={resolvingId === tx.id}
                                onClick={() => handleResolveSingleDuplicate(tx.id, 'keep_original')}
                                className="
                                  text-[9px] font-medium px-1 py-0.5 rounded
                                  text-[var(--danger-700)] hover:bg-[var(--danger-50)]
                                  transition-colors disabled:opacity-50
                                "
                                title="Delete this duplicate, keep the original"
                                data-testid={`activity-row-${tx.id}-dup-discard-this`}
                              >
                                ✕ Discard this
                              </button>
                              <button
                                type="button"
                                disabled={resolvingId === tx.id}
                                onClick={() => handleResolveSingleDuplicate(tx.id, 'keep_this')}
                                className="
                                  text-[9px] font-medium px-1 py-0.5 rounded
                                  text-[var(--primary-700)] hover:bg-[var(--primary-50)]
                                  transition-colors disabled:opacity-50
                                "
                                title="Delete the original, keep this one instead"
                                data-testid={`activity-row-${tx.id}-dup-keep-this`}
                              >
                                ↺ Keep this
                              </button>
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="py-4 body-md text-[var(--text-secondary)] text-right">
                        {formatDate(tx.transaction_date)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  )
}

export default function ActivityPage() {
  const embedded = useEmbeddedMoneyView()
  if (embedded) return <ActivityContent embedded />
  return (
    <PageLayout>
      <AtlasFilterProvider>
        <ActivityContent />
      </AtlasFilterProvider>
    </PageLayout>
  )
}

// -----------------------------------------------------------------
// Sub-components — local-only, not exported. Phase 11 keeps the
// surface minimal so the activity route stays the source of truth
// for filter combinations (vs wrapping each chip in its own file.
// -----------------------------------------------------------------

/** Phase 52+ — period label above the Activity summary strip.
 *  Shows the date range being viewed so the user can tell at a glance
 *  whether they're looking at MTD (default, matches Dashboard KPI strip)
 *  or a custom/lifetime range. Includes the BE limit disclaimer when
 *  viewing all-time ("Lifetime" with no date filter) so the user
 *  understands the 500-row ceiling. */
function PeriodLabel({
  dateFrom,
  dateTo,
  rowCount,
  queryLimit,
}: {
  dateFrom: string
  dateTo: string
  rowCount: number
  queryLimit: number
}) {
  const fmt = (d: string) => {
    if (!d) return null
    const parsed = new Date(d + 'T00:00:00')
    if (isNaN(parsed.getTime())) return null
    return parsed.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  }
  const fromLabel = fmt(dateFrom)
  const toLabel = fmt(dateTo)

  const isLifetime = !dateFrom && !dateTo
  const isNearLimit = !isLifetime && rowCount >= queryLimit

  return (
    <div className="flex items-center gap-2 mb-2 text-xs text-tertiary">
      <Clock className="w-3.5 h-3.5" aria-hidden="true" />
      {isLifetime ? (
        <span>
          Showing all time (up to {queryLimit} most recent transactions)
        </span>
      ) : fromLabel && toLabel ? (
        <span>
          {fromLabel} — {toLabel}
          {isNearLimit && (
            <span className="ml-1 text-[var(--warning-700)]">
              · capped at {queryLimit} rows
            </span>
          )}
        </span>
      ) : fromLabel ? (
        <span>Since {fromLabel}</span>
      ) : toLabel ? (
        <span>Until {toLabel}</span>
      ) : (
        <span>All time</span>
      )}
    </div>
  )
}

function SummaryStat({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone: 'success' | 'danger' | 'neutral'
}) {
  const toneClasses =
    tone === 'success'
      ? 'text-[var(--success-700)]'
      : tone === 'danger'
      ? 'text-[var(--danger-700)]'
      : 'text-[var(--text-primary)]'
  return (
    <div
      className="card p-3 bg-[var(--bg-tertiary)]"
      data-testid={`activity-summary-${label.toLowerCase()}`}
    >
      <div className="label-sm text-tertiary font-medium">
        {label}
      </div>
      <div className={`text-base font-semibold mt-1 ${toneClasses}`}>
        {value}
      </div>
    </div>
  )
}

function DateField({
  label,
  value,
  onChange,
  testId,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  testId?: string
}) {
  return (
    <label className="space-y-1">
      <span className="label-sm text-tertiary">{label}</span>
      <input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="
          block w-full rounded-[var(--radius-md)]
          border border-outline-variant/40
          bg-[var(--bg-secondary)]
          text-on-surface px-3 py-2 text-sm
          focus-visible:outline-2 focus-visible:offset-2
          focus-visible:outline-[var(--primary-500)]
        "
        data-testid={testId}
      />
    </label>
  )
}

function SortDirToggle({
  value,
  onChange,
}: {
  value: SortDir
  onChange: (v: SortDir) => void
}) {
  const Icon = value === 'asc' ? ArrowUpAZ : ArrowDownAZ
  return (
    <button
      type="button"
      onClick={() => onChange(value === 'asc' ? 'desc' : 'asc')}
      className="
        self-end inline-flex items-center justify-center gap-1
        h-10 px-3 rounded-[var(--radius-md)]
        border border-outline-variant/40
        bg-[var(--bg-secondary)] text-on-surface
        text-sm font-medium
        hover:bg-[var(--bg-tertiary)]
        focus-visible:outline-2 focus-visible:offset-2
        focus-visible:outline-[var(--primary-500)]
      "
      data-testid="activity-sort-dir"
      aria-label={`Sort direction: ${value}. Click to flip.`}
    >
      <Icon className="w-4 h-4" aria-hidden="true" />
      {value === 'asc' ? 'Ascending' : 'Descending'}
    </button>
  )
}

function SearchField({
  value,
  onChange,
}: {
  value: string
  onChange: (v: string) => void
}) {
  return (
    <label className="space-y-1 block">
      <span className="label-sm text-tertiary flex items-center gap-1">
        <Search className="w-3.5 h-3.5" aria-hidden="true" />
        Search description or merchant
      </span>
      <input
        type="search"
        placeholder="e.g. Starbucks, Amazon, payroll…"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="
          block w-full rounded-[var(--radius-md)]
          border border-outline-variant/40
          bg-[var(--bg-secondary)]
          text-on-surface px-3 py-2 text-sm
          focus-visible:outline-2 focus-visible:offset-2
          focus-visible:outline-[var(--primary-500)]
        "
        data-testid="activity-search"
      />
    </label>
  )
}

function CategoryCell({
  txnId,
  merchantKeyword,
  currentCategoryId,
  currentCategoryName,
  categories,
  isEditing,
  onCategoryChosen,
  onCategoryCreated,
}: {
  txnId: number
  merchantKeyword: string
  currentCategoryId: number | null
  currentCategoryName: string | null
  categories: Category[]
  isEditing: boolean
  // Phase 25+ — semantic rename. The callback now represents any category
  // selection (choose / re-choose / detach); `null` is the canonical detach
  // sentinel so the BE-resolved category id `0` can never be confused with
  // a real user action. The parent maps `cid === null` to the standard
  // ``handleInlineCategoryChange(..., null)`` path.
  // Phase 31 — keyword param so the user can edit the rule keyword
  // in the promote panel before committing. ``keyword`` is the
  // current value of the editable input (may differ from the
  // original merchant text).
  onCategoryChosen: (categoryId: number | null, keyword?: string) => void
  onCategoryCreated: (newCategory: {
    id: number
    name: string
    description?: string | null
    icon?: string | null
    color?: string | null
  }) => void
}) {
  // Phase 25 - Promote-to-Rule affordance replaces the prior + Tag picker.
  // A single click opens a category dropdown with an inline Add-new-category
  // mini-form. On confirm, the parent commits BOTH a MerchantRule
  // (DB-backed substring) and the transaction's category_id so the same
  // action tags this row AND teaches future imports. Re-tagging a row that
  // already has a category invokes the BE's UNIQUE(category_id, keyword)
  // check; the 409 'already exists' branch is swallowed by
  // handlePromoteToRule and re-committed as an idempotent category_id PUT.
  const [pickerOpen, setPickerOpen] = useState(false)
  const [creatingCategory, setCreatingCategory] = useState(false)
  const [newCategoryName, setNewCategoryName] = useState('')
  const [creatingSubmitting, setCreatingSubmitting] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const wrapperRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!pickerOpen) return
    const onPointer = (e: MouseEvent | TouchEvent) => {
      const target = e.target as Node | null
      if (target && wrapperRef.current && !wrapperRef.current.contains(target)) {
        setPickerOpen(false)
        setCreatingCategory(false)
      }
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setPickerOpen(false)
        setCreatingCategory(false)
      }
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('touchstart', onPointer, { passive: true })
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('touchstart', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [pickerOpen])

  const trimmedKeyword = (merchantKeyword || '').trim().toUpperCase()
  // Phase 31 — editable keyword in the promote panel so the user
  // can refine the rule text before committing (e.g. trim noise
  // like "POS DEBIT 1234" → "POS DEBIT"). Initialised from the
  // merchant text on each open.
  const [editedKeyword, setEditedKeyword] = useState(trimmedKeyword)
  const triggerDisabled = isEditing || !trimmedKeyword

  const handleCreateCategory = async (e: React.FormEvent) => {
    e.preventDefault()
    const name = newCategoryName.trim()
    if (!name) {
      setCreateError('Type a category name first.')
      return
    }
    if (!trimmedKeyword) {
      setCreateError(
        'This row has no merchant text - promote from a row with a recognisable merchant name.',
      )
      return
    }
    setCreatingSubmitting(true)
    setCreateError(null)
    try {
      const newCat =      await rulesService.createCategory({ name })
      onCategoryCreated(newCat)
      setNewCategoryName('')
      setCreatingCategory(false)
      // Chain into the promote flow - the parent commits the
      // MerchantRule + the txn's category_id.
      const kw = (editedKeyword || trimmedKeyword).trim().toUpperCase()
      onCategoryChosen(newCat.id, kw)
      setPickerOpen(false)
    } catch (err: any) {
      setCreateError(
        err?.response?.data?.detail ??
          err?.message ??
          'Failed to create category.',
      )
    } finally {
      setCreatingSubmitting(false)
    }
  }

  // Branch 1 - tagged + not editing + picker not currently open.
  // Phase 29 — the per-row chip now wears the canonical category
  // color (from `category.color` via the props chain from
  // ActivityPage's `categories` array) so every tagged row carries
  // the same hex as the SpendingByCategory donut + the Settings
  // rule-list badge. The pre-Phase-29 purple tint was hardcoded
  // to var(--primary-50) so EVERY category looked identical.
  if (currentCategoryId && !isEditing && !pickerOpen) {
    const categoryForChip = categories.find(
      (c) => c.id === currentCategoryId,
    )
    const categoryColor = categoryForChip?.color || 'var(--primary-500)'
    return (
      <div className="inline-flex items-center gap-1.5 flex-wrap">
        <button
          type="button"
          onClick={() => onCategoryChosen(null)}
          className="
            inline-flex items-center gap-1.5 px-2 py-0.5
            rounded-[var(--radius-sm)] text-[11px] font-semibold
            text-white
            transition-all duration-[var(--duration-fast)]
            hover:opacity-90 active:scale-[0.97]
            focus-visible:outline-2 focus-visible:offset-2
            focus-visible:outline-[var(--primary-500)]
            shadow-sm
          "
          style={{ backgroundColor: categoryColor }}
          title={`Click to detach (currently tagged "${currentCategoryName ?? ''}").`}
          data-testid={`activity-category-button-${txnId}`}
        >
          {categoryForChip?.icon ? (
            <span aria-hidden="true">{categoryForChip.icon}</span>
          ) : (
            <Tag className="w-3 h-3" aria-hidden="true" />
          )}
          {currentCategoryName ?? 'Tagged'}
        </button>
        <button
          type="button"
          onClick={() => setPickerOpen(true)}
          className="label-sm text-tertiary hover:text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:offset-2 focus-visible:outline-[var(--primary-500)] px-1 py-0.5 rounded"
          title="Add a substring rule from this merchant"
          data-testid={`activity-promote-link-${txnId}`}
        >
          Promote rule
        </button>
      </div>
    )
  }
  // Branch 2 - picker affordance (untagged / editing / open).
  const triggerLabel = isEditing ? 'Promoting...' : 'Promote to rule'
  const triggerClass = isEditing
    ? 'border-[var(--slate-300)] text-[var(--text-tertiary)] cursor-wait'
    : pickerOpen
      ? 'border-[var(--primary-500)] bg-[var(--primary-50)] text-[var(--primary-700)]'
      : 'border-[var(--primary-300)] text-[var(--primary-600)] hover:bg-[var(--primary-50)] hover:border-[var(--primary-500)]'

  return (
    <div ref={wrapperRef} className="relative inline-block">
      <button
        type="button"
        onClick={() => {
          if (triggerDisabled) return
          setPickerOpen((o) => !o)
        }}
        disabled={triggerDisabled}
        title={
          isEditing
            ? 'Tagging in progress.'
            : trimmedKeyword
              ? 'Promote this merchant to a substring rule and tag this transaction.'
              : 'No merchant text on this row -- re-import or pick a row with a recognisable merchant name.'
        }
        aria-haspopup="dialog"
        aria-expanded={pickerOpen}
        aria-label={
          currentCategoryId
            ? `Add a substring rule from this merchant (currently ${currentCategoryName ?? 'tagged'})`
            : 'Promote to substring rule and tag this transaction'
        }
        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-[var(--radius-sm)] max-w-[12rem] border border-dashed text-[11px] font-semibold focus-visible:outline-2 focus-visible:offset-2 focus-visible:outline-[var(--primary-500)] disabled:opacity-70 ${triggerClass}`}
        data-testid={`activity-promote-trigger-${txnId}`}
      >
        {isEditing ? (
          <RefreshCw className="w-3 h-3 animate-spin" aria-hidden="true" />
        ) : (
          <Plus className="w-3 h-3" aria-hidden="true" />
        )}
        {triggerLabel}
      </button>
      {pickerOpen && !isEditing && (
        <div
          role="dialog"
          aria-label="Promote to substring rule"
          className="absolute left-0 top-full mt-1 z-30 w-72 max-h-[26rem] overflow-auto bg-[var(--bg-primary)] border border-[var(--border-color)] rounded-[var(--radius-md)] shadow-[var(--shadow-4)] py-1 animate-fadeIn"
          data-testid={`activity-promote-panel-${txnId}`}
        >
          <div className="px-3 pt-2 pb-1 border-b border-outline-variant/30">
            <p className="label-xs font-semibold text-tertiary mb-1">
              Rule keyword
            </p>
            <input
              type="text"
              value={editedKeyword}
              onChange={(e) => setEditedKeyword(e.target.value)}
              placeholder={trimmedKeyword || 'Type a keyword…'}
              className="block w-full rounded-[var(--radius-sm)] border border-[var(--slate-300)] bg-[var(--bg-primary)] text-on-surface px-2 py-1.5 text-[12px] focus-visible:outline-2 focus-visible:offset-2 focus-visible:outline-[var(--primary-500)]"
              data-testid={`activity-promote-keyword-input-${txnId}`}
            />
            <p className="text-[10px] text-tertiary mt-0.5">
              {editedKeyword.trim() !== trimmedKeyword
                ? 'Edited — the rule will use your text above, not the original merchant name.'
                : 'Tags this row + adds the MerchantRule shown.'}
            </p>
          </div>

          {!creatingCategory && (
            <button
              type="button"
              onClick={() => {
                setCreatingCategory(true)
                setCreateError(null)
              }}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-[11px] text-[var(--primary-700)] bg-[var(--primary-50)] hover:bg-[var(--primary-100)] border-b border-outline-variant/20 focus-visible:outline-none"
              data-testid={`activity-promote-new-category-${txnId}`}
            >
              <Plus className="w-3 h-3" aria-hidden="true" />
              Add new category...
            </button>
          )}

          {creatingCategory && (
            <form
              onSubmit={handleCreateCategory}
              className="px-3 pt-2 pb-3 border-b border-outline-variant/20 bg-[var(--bg-secondary)]"
              data-testid={`activity-promote-new-category-form-${txnId}`}
            >
              <label className="block text-[10px] font-semibold text-tertiary mb-1">
                New category name
              </label>
              <input
                type="text"
                value={newCategoryName}
                onChange={(e) => setNewCategoryName(e.target.value)}
                placeholder="e.g. Pet Supplies"
                autoFocus
                disabled={creatingSubmitting}
                className="block w-full rounded-[var(--radius-sm)] border border-[var(--slate-300)] bg-[var(--bg-primary)] text-on-surface px-2 py-1.5 text-[12px] focus-visible:outline-2 focus-visible:offset-2 focus-visible:outline-[var(--primary-500)]"
                data-testid={`activity-promote-new-category-input-${txnId}`}
              />
              {createError && (
                <p
                  className="text-[10px] text-danger mt-1"
                  role="alert"
                  data-testid={`activity-promote-new-category-error-${txnId}`}
                >
                  {createError}
                </p>
              )}
              <div className="flex items-center gap-2 mt-2">
                <button
                  type="submit"
                  disabled={creatingSubmitting}
                  className="inline-flex items-center justify-center px-2.5 py-1 rounded-[var(--radius-sm)] text-[11px] font-semibold bg-[var(--primary-500)] text-[var(--text-on-brand)] hover:bg-[var(--primary-600)] disabled:bg-[var(--slate-400)] disabled:cursor-not-allowed"
                  data-testid={`activity-promote-new-category-submit-${txnId}`}
                >
                  {creatingSubmitting ? 'Creating...' : 'Create + promote'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setCreatingCategory(false)
                    setCreateError(null)
                    setNewCategoryName('')
                  }}
                  disabled={creatingSubmitting}
                  className="inline-flex items-center justify-center px-2.5 py-1 rounded-[var(--radius-sm)] text-[11px] text-tertiary hover:text-primary focus-visible:outline-2 focus-visible:offset-2 focus-visible:outline-[var(--primary-500)]"
                >
                  Cancel
                </button>
              </div>
            </form>
          )}

          <ul role="listbox" aria-label="Category choices" className="py-1">
            {categories.length === 0 ? (
              <li
                className="px-3 py-2 text-[11px] text-tertiary"
                data-testid={`activity-promote-empty-${txnId}`}
              >
                No categories yet - click Add new category...
              </li>
            ) : (
              categories.map((c) => {
                const isSelected = c.id === currentCategoryId
                return (
                  <li key={c.id}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      onClick={() => {
                        const kw = (editedKeyword || trimmedKeyword).trim().toUpperCase()
                        onCategoryChosen(c.id, kw)
                        setPickerOpen(false)
                      }}
                      className={`w-full flex items-center gap-2 px-3 py-1.5 text-left text-[11px] transition-colors duration-[var(--duration-fast)] focus-visible:outline-none ${
                        isSelected
                          ? 'bg-[var(--primary-50)] text-[var(--primary-700)] font-semibold'
                          : 'text-[var(--text-primary)] hover:bg-[var(--slate-100)] focus:bg-[var(--slate-100)]'
                      }`}
                      data-testid={`activity-promote-option-${txnId}-${c.id}`}
                    >
                      {c.icon ? (
                        <span aria-hidden="true">{c.icon}</span>
                      ) : (
                        <Tag className="w-3 h-3" aria-hidden="true" />
                      )}
                      <CategoryDot
                        category={{ name: c.name, color: c.color }}
                        size="sm"
                      />
                      {c.name}
                    </button>
                  </li>
                )
              })
            )}
          </ul>
        </div>
      )}
    </div>
  )
}
