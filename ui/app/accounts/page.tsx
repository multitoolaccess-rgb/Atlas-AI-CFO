'use client'

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Plus, Landmark, Pencil, Trash2, Loader2, Eye, EyeOff } from 'lucide-react'
import PageLayout from '@/components/layout/PageLayout'
import { AtlasFilterProvider } from '@/components/ui/AtlasFilterContext'
import FloatingTimeRangeBar from '@/components/ui/FloatingTimeRangeBar'
import AnimatedPageSection from '@/components/ui/AnimatedPageSection'
import ErrorBanner from '@/components/ui/ErrorBanner'
import EmptyState from '@/components/ui/EmptyState'
import PageHeader from '@/components/ui/PageHeader'
import TiltCard from '@/components/ui/TiltCard'
import { Button, Input, Select, TabsGroup, Modal } from '@/components/ui'
import ImportStatementUpload from '@/components/imports/ImportStatementUpload'
import { formatNumber } from '@/lib/format'
import {
  rulesService,
  ACCOUNT_SOURCE_LABELS,
  type Account,
  type AccountSource,
  type FamilyMember,
} from '@/lib/api'
import { onDataRefresh, fireDataRefresh } from '@/lib/dataRefresh'

const ACCOUNT_TYPES = [
  { value: 'checking', label: 'Checking' },
  { value: 'savings', label: 'Savings' },
  { value: 'credit_card', label: 'Credit Card' },
  { value: 'debit_card', label: 'Debit Card' },
  { value: 'investment', label: 'Investment' },
  { value: 'loan', label: 'Loan' },
  { value: 'mortgage', label: 'Mortgage' },
  { value: 'hsa', label: 'Health Savings Account' },
  { value: '529', label: '529 Education Plan' },
  { value: '401k', label: '401(k)' },
  { value: 'ira', label: 'IRA' },
  { value: 'crypto', label: 'Crypto' },
  { value: 'other', label: 'Other' },
]

type DataConnectionView = 'accounts' | 'imports' | 'synchronization' | 'data-quality'
const DATA_CONNECTION_VIEWS: readonly DataConnectionView[] = ['accounts', 'imports', 'synchronization', 'data-quality']

export default function AccountsPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const requestedView = searchParams.get('view')
  const initialView: DataConnectionView = DATA_CONNECTION_VIEWS.includes(requestedView as DataConnectionView)
    ? requestedView as DataConnectionView
    : 'accounts'
  const [activeView, setActiveView] = useState<DataConnectionView>(initialView)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)

  // Phase 16 — family members state. The select dropdowns on both the
  // create and edit forms share this list; re-fetched whenever a
  // sibling page fires a data-refresh (Settings Family Members card).
  const [familyMembers, setFamilyMembers] = useState<FamilyMember[]>([])
  const [membersById, setMembersById] = useState<Record<number, FamilyMember>>(
    {},
  )

  // Create form state
  const [showForm, setShowForm] = useState(false)
  const [accountName, setAccountName] = useState('')
  const [accountType, setAccountType] = useState('checking')
  const [institutionName, setInstitutionName] = useState('')
  const [openingBalance, setOpeningBalance] = useState('')
  // Phase 40 — optional account number. Empty string round-trips as
  // ``undefined`` so the BE stores ``account_number=NULL``; the card's
  // "Show numbers" toggle is then a visible no-op for that row.
  // This was the missing input that left EVERY manual Add Account
  // user without an account number on disk (only Fidelity multi-
  // account CSV imports ever set the column, via the parsed X… digits
  // in the filename).
  const [accountNumber, setAccountNumber] = useState('')
  // Phase 40 — free-text note on the create form. Empty string
  // round-trips as ``undefined`` so the BE stores NULL and the
  // card's source chip + description sub-line stay absent.
  const [description, setDescription] = useState('')
  // Phase 16 — defaults to the local user's Self row when the list
  // resolves. The BE route also defaults to Self on POST, so passing
  // an explicit id is purely a UX improvement (the field is non-empty
  // when the user opens the form so they SEE the assignment).
  const [familyMemberId, setFamilyMemberId] = useState<number | ''>('')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  // Edit modal state (Phase 7 — mirrors the Create form, pre-populated).
  const [editingAccount, setEditingAccount] = useState<Account | null>(null)
  const [editName, setEditName] = useState('')
  const [editType, setEditType] = useState('checking')
  const [editBalance, setEditBalance] = useState('')
  // Phase 40 — mirror the Add-Form account-number field so the user
  // can edit or back-fill it after import. Initialised in ``startEdit``
  // from ``acc.account_number ?? ''`` so an empty DB column renders as
  // an empty Input (the "Show numbers" footer stays absent).
  const [editAccountNumber, setEditAccountNumber] = useState('')
  // Phase 40 — free-text note on the Edit modal. Initialised in
  // ``startEdit`` from ``acc.description ?? ''`` so an empty DB
  // column renders as an empty textarea.
  const [editDescription, setEditDescription] = useState('')
  // Phase 16 — mirror the create-form field for the edit modal.
  const [editFamilyMemberId, setEditFamilyMemberId] = useState<number | ''>('')
  const [editSubmitting, setEditSubmitting] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)

  // Delete confirmation modal state (soft-delete via DELETE /api/accounts/{id}).
  const [confirmingDelete, setConfirmingDelete] = useState<Account | null>(null)
  const [deleteSubmitting, setDeleteSubmitting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  // Phase 37 — toggle for showing/hiding full account numbers.
  const [showAccountNumbers, setShowAccountNumbers] = useState(false)

  // Re-fetch when any page fires a data-refresh event (upload, delete, etc.)
  useEffect(() => onDataRefresh(() => setRetryCount((c) => c + 1)), [])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const [a, m] = await Promise.all([
          rulesService.listAccounts(),
          rulesService.listFamilyMembers(),
        ])
        if (!cancelled) {
          setAccounts(a)
          setFamilyMembers(m)
          setMembersById(
            m.reduce<Record<number, FamilyMember>>((acc, member) => {
              acc[member.id] = member
              return acc
            }, {}),
          )
          // Default the create-form family_member_id to Self on first
          // load. Self is guaranteed to exist (the BE bootstraps it
          // on the first GET), so a brand-new user sees their Self
          // row pre-selected when they open the form.
          const selfRow = m.find((row) => row.is_self)
          if (selfRow && familyMemberId === '') {
            setFamilyMemberId(selfRow.id)
          }
          setLoading(false)
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(
            err?.response?.data?.detail ??
              err?.message ??
              'Failed to load accounts.',
          )
          setLoading(false)
        }
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [retryCount, familyMemberId])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setFormError(null)
    try {
      const balance = openingBalance === '' ? 0 : Number(openingBalance)
      const created = await rulesService.createAccount({
        account_name: accountName,
        account_type: accountType,
        institution_name: institutionName,
        current_balance: Number.isFinite(balance) ? balance : 0,
        family_member_id:
          familyMemberId === '' ? undefined : familyMemberId,
        // Phase 40 — optional. Empty / whitespace input maps to
        // ``undefined`` so axios omits the key; the BE stores
        // ``account_number=NULL`` (default) and the "Show numbers"
        // toggle is a visible no-op for this card.
        account_number: accountNumber.trim() || undefined,
        // Phase 40 — optional free-text note. Same null-on-empty
        // pattern as account_number: empty input → omitted key →
        // BE stores description=NULL.
        description: description.trim() || undefined,
      })
      setAccounts((prev) => [...prev, created])
      setAccountName('')
      setAccountType('checking')
      setInstitutionName('')
      setOpeningBalance('')
      setAccountNumber('')
      setDescription('')
      // Reset the family_member_id back to the bootstrapped default
      // (Self) so a follow-up \"Add Account\" opens pre-selected.
      const selfRow = familyMembers.find((row) => row.is_self)
      setFamilyMemberId(selfRow?.id ?? '')
      setShowForm(false)
    } catch (err: any) {
      setFormError(
        err?.response?.data?.detail ??
          err?.message ??
          'Failed to create account.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  // Edit handlers ------------------------------------------------------
  const startEdit = (acc: Account) => {
    setEditingAccount(acc)
    setEditName(acc.account_name)
    setEditType(acc.account_type)
    setEditBalance(String(acc.current_balance))
    setEditAccountNumber(acc.account_number ?? '')
    setEditDescription(acc.description ?? '')
    setEditFamilyMemberId(acc.family_member_id ?? '')
    setEditError(null)
  }

  const cancelEdit = () => {
    if (editSubmitting) return
    setEditingAccount(null)
    setEditError(null)
  }

  const submitEdit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingAccount) return
    setEditSubmitting(true)
    setEditError(null)
    try {
      const balance = Number(editBalance)
      // Phase 40 — only include ``account_number`` in the patch when
      // the user actually typed something. An empty / whitespace-only
      // input maps to ``undefined`` so axios omits the key and the
      // BE's whitelist filter keeps the existing column unchanged
      // (mirrors the create-form behaviour).
      const editPatch: {
        account_name: string
        account_type: string
        current_balance: number
        family_member_id: number | undefined
        account_number?: string
        description?: string
      } = {
        account_name: editName,
        account_type: editType,
        current_balance: Number.isFinite(balance) ? balance : 0,
        family_member_id:
          editFamilyMemberId === '' ? undefined : editFamilyMemberId,
      }
      const trimmedAccountNumber = editAccountNumber.trim()
      if (trimmedAccountNumber !== '') {
        editPatch.account_number = trimmedAccountNumber
      }
      // Phase 40 — same null-on-empty pattern as account_number
      // above: omitted from PATCH when the user clears the field
      // (matches the create-form's "don't write empty" contract).
      const trimmedDescription = editDescription.trim()
      if (trimmedDescription !== '') {
        editPatch.description = trimmedDescription
      }
      const updated = await rulesService.updateAccount(
        editingAccount.id,
        editPatch,
      )
      setAccounts((prev) =>
        prev.map((a) => (a.id === updated.id ? updated : a)),
      )
      setEditingAccount(null)
    } catch (err: any) {
      setEditError(
        err?.response?.data?.detail ??
          err?.message ??
          'Failed to update account.',
      )
    } finally {
      setEditSubmitting(false)
    }
  }

  // Delete handlers ----------------------------------------------------
  const startDelete = (acc: Account) => {
    setConfirmingDelete(acc)
    setDeleteError(null)
  }

  const cancelDelete = () => {
    if (deleteSubmitting) return
    setConfirmingDelete(null)
    setDeleteError(null)
  }

  const submitDelete = async () => {
    if (!confirmingDelete) return
    setDeleteSubmitting(true)
    setDeleteError(null)
    try {
      await rulesService.deleteAccount(confirmingDelete.id)
      // Soft-delete flips is_active=False; listAccounts filters those out.
      // Bump retryCount so the grid re-renders without the deleted row.
      setRetryCount((c) => c + 1)
      setConfirmingDelete(null)
    } catch (err: any) {
      setDeleteError(
        err?.response?.data?.detail ??
          err?.message ??
          'Failed to delete account.',
      )
    } finally {
      setDeleteSubmitting(false)
    }
  }

  // Refresh hook called by ImportStatementUpload after a successful upload
  // — the BE may have lazily created an "Imported Statements" account if
  // no account was selected and no accounts existed before.
  const handleImportComplete = () => {
    setRetryCount((c) => c + 1)
    // Notify other pages (Overview, Portfolio, Activity) to
    // re-fetch so balances and counts update everywhere.
    fireDataRefresh()
  }

  const handleViewChange = (nextView: string) => {
    if (!DATA_CONNECTION_VIEWS.includes(nextView as DataConnectionView)) return
    const view = nextView as DataConnectionView
    setActiveView(view)
    const params = new URLSearchParams(searchParams.toString())
    params.set('view', view)
    router.replace(`?${params.toString()}`, { scroll: false })
  }

  return (
    <PageLayout>
      <AtlasFilterProvider>
      <AnimatedPageSection>
        <PageHeader
          title="Data Connections"
          description="Manage account sources, statement imports, synchronization readiness, and data quality without exposing credentials."
          actions={(
            <>
              <button
                type="button"
                onClick={() => setShowAccountNumbers((v) => !v)}
                title={showAccountNumbers ? 'Hide account numbers' : 'Show account numbers'}
                className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium border border-outline-variant/40 text-secondary hover:text-primary hover:bg-surface-container transition-colors duration-150"
              >
                {showAccountNumbers ? <EyeOff className="w-3.5 h-3.5" aria-hidden="true" /> : <Eye className="w-3.5 h-3.5" aria-hidden="true" />}
                {showAccountNumbers ? 'Hide numbers' : 'Show numbers'}
              </button>
              <Button
                variant="primary"
                onClick={() => setShowForm((s) => !s)}
                icon={<Plus className="w-4 h-4" aria-hidden="true" />}
              >
                {showForm ? 'Cancel' : 'Add Account'}
              </Button>
            </>
          )}
          className="mb-6"
        />

      {/* Floating bar — URL-synced via ?range=… (page-default YTD).
          Visual-only today: accounts are not range-aware yet. */}
      <FloatingTimeRangeBar />

      {error && (
        // variant="warning" (amber) — page-level data-load failure
        // with Retry affordance. Matches Overview / Goals / Portfolio
        // / Settings / Activity. Form-level create/edit error remains
        // variant="danger" (real user action failures).
        <ErrorBanner
          title="Couldn't load accounts:"
          message={error}
          variant="warning"
          onRetry={() => setRetryCount((c) => c + 1)}
        />
      )}

      <TabsGroup
        variant="underline"
        activeId={activeView}
        onChange={handleViewChange}
        items={[
          {
            id: 'accounts',
            label: 'Accounts',
            icon: 'account_balance',
            content: (
              <div data-testid="accounts-tab-panel">
                {showForm && (
                  <form
                    onSubmit={handleCreate}
                    className="card p-6 mb-6"
                    data-testid="create-account-form"
                  >
                    <h2 className="headline-md text-primary mb-4">
                      New account
                    </h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <Input
                        label="Account name"
                        value={accountName}
                        onChange={(e) => setAccountName(e.target.value)}
                        required
                        placeholder="e.g. Chase Checking"
                      />
                      <Select
                        label="Account type"
                        value={accountType}
                        onChange={(e) => setAccountType(e.target.value)}
                        options={ACCOUNT_TYPES}
                      />
                      <Input
                        label="Institution"
                        value={institutionName}
                        onChange={(e) => setInstitutionName(e.target.value)}
                        required
                        placeholder="e.g. Chase"
                      />
                      <Input
                        label="Opening balance"
                        type="number"
                        value={openingBalance}
                        onChange={(e) => setOpeningBalance(e.target.value)}
                        placeholder="0.00"
                      />
                      {/* Phase 40 — optional account number. Empty
                          input is omitted from the payload so the BE
                          stores NULL (the card's "Show numbers"
                          toggle then has nothing to reveal). The
                          Reveal toggle ON the card page is what
                          triggers the masked-vs-full render; this
                          input just gives the data somewhere to
                          live. */}
                      <Input
                        label="Account number"
                        value={accountNumber}
                        onChange={(e) => setAccountNumber(e.target.value)}
                        placeholder="optional — e.g. •••• 1234"
                      />
                      <Select
                        label="Family member"
                        value={
                          familyMemberId === '' ? '' : String(familyMemberId)
                        }
                        onChange={(e) =>
                          setFamilyMemberId(
                            e.target.value === ''
                              ? ''
                              : Number(e.target.value),
                          )
                        }
                        options={familyMembers.map((m) => ({
                          value: String(m.id),
                          label: m.is_self ? `${m.name} (Self)` : m.name,
                        }))}
                      />
                    </div>
                    {formError && (
                      <p
                        className="text-sm text-danger mt-3"
                        role="alert"
                      >
                        {formError}
                      </p>
                    )}
                    <div className="mt-4 flex gap-2">
                      <Button
                        type="submit"
                        variant="primary"
                        disabled={submitting}
                      >
                        {submitting ? 'Creating…' : 'Create account'}
                      </Button>
                      <Button
                        type="button"
                        variant="tertiary"
                        onClick={() => setShowForm(false)}
                      >
                        Cancel
                      </Button>
                    </div>
                  </form>
                )}

                {loading ? (
                  <p
                    className="text-sm text-secondary"
                    data-testid="accounts-loading"
                  >
                    Loading accounts…
                  </p>
                ) : accounts.length === 0 ? (
            <EmptyState
              testId="accounts-empty"
              icon={<Landmark className="h-6 w-6" />}
              title="Connect your first account"
              description="Add an account or upload a statement to give Atlas the source data it needs for balances, cash flow, and planning."
              guidance={<p className="text-sm">Use the Add Account control above for a manual connection, or choose the Statement tab for CSV, PDF, or OFX import.</p>}
            />
                ) : (
                  <div
                    className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
                    data-testid="accounts-grid"
                  >
                    {accounts.map((acc) => (
                      <TiltCard
                        key={acc.id}
                        className="h-full"
                      >
                        <div
                          className="card p-6 h-full"
                          role="article"
                          data-testid={`account-card-${acc.id}`}
                        >
                          <div className="flex items-start justify-between mb-1 gap-2">
                          <h3 className="text-sm font-bold uppercase tracking-wider text-primary truncate">
                            {acc.account_name}
                          </h3>
                          <div className="flex items-center gap-1 flex-shrink-0">
                            {!acc.is_active && (
                              <span className="text-[10px] font-bold uppercase tracking-wider text-warning-700 bg-warning-50 px-2 py-0.5 rounded">
                                Inactive
                              </span>
                            )}
                            <button
                              type="button"
                              onClick={() => startEdit(acc)}
                              aria-label={`Edit ${acc.account_name}`}
                              title="Edit"
                              data-testid={`account-edit-${acc.id}`}
                              className="
                                inline-flex items-center justify-center
                                w-8 h-8 rounded-[var(--radius-sm)]
                                text-[var(--text-tertiary)]
                                hover:text-[var(--text-primary)]
                                hover:bg-[var(--bg-tertiary)]
                                focus-visible:outline-2 focus-visible:outline-offset-2
                                focus-visible:outline-[var(--primary-500)]
                                transition-colors duration-[var(--duration-fast)]
                              "
                            >
                              <Pencil
                                className="w-4 h-4"
                                aria-hidden="true"
                              />
                            </button>
                            <button
                              type="button"
                              onClick={() => startDelete(acc)}
                              aria-label={`Delete ${acc.account_name}`}
                              title="Delete"
                              data-testid={`account-delete-${acc.id}`}
                              className="
                                inline-flex items-center justify-center
                                w-8 h-8 rounded-[var(--radius-sm)]
                                text-[var(--text-tertiary)]
                                hover:text-[var(--danger-600)]
                                hover:bg-[var(--danger-50)]
                                focus-visible:outline-2 focus-visible:outline-offset-2
                                focus-visible:outline-[var(--danger-500)]
                                transition-colors duration-[var(--duration-fast)]
                              "
                            >
                              <Trash2
                                className="w-4 h-4"
                                aria-hidden="true"
                              />
                            </button>
                          </div>
                        </div>
                        <p className="text-xs text-secondary">
                          {acc.account_type}
                          {acc.account_subtype
                            ? ` · ${acc.account_subtype}`
                            : ''}
                        </p>
                        {/* Phase 16 — per-account family-member chip.
                            Renders the color dot + member name (with a
                            "Self" suffix on the bootstrap row) so the
                            accounts list serves as a per-member roll-up. */}
                        {membersById[acc.family_member_id] && (
                          <p
                            className="text-xs text-secondary mt-1 flex items-center gap-2"
                            data-testid={`account-member-chip-${acc.id}`}
                          >
                            <span
                              aria-hidden="true"
                              className="inline-block w-2 h-2 rounded-full"
                              style={{
                                backgroundColor:
                                  membersById[acc.family_member_id]?.color,
                              }}
                            />
                            <span>
                              {membersById[acc.family_member_id].name}
                              {membersById[acc.family_member_id].is_self && (
                                <span className="ml-1 text-[10px] text-emerald-700 font-semibold">
                                  (Self)
                                </span>
                              )}
                            </span>
                          </p>
                        )}
                        {/* Phase 40 — provenance chip + free-text note.
                            The chip renders the coarse create-path
                            (Manual / Imported / Plaid) so the user
                            can scan the grid at a glance for accounts
                            that arrived via upload (clean-up candidate)
                            vs. manually entered. The description sub-
                            line is suppressed when DB-column is
                            ``None`` or ``''`` so a card with no import
                            diagnostic stays tidy. */}
                        <div className="flex items-center gap-2 mt-2 flex-wrap">
                          {acc.source && (
                            <span
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                                acc.source === 'imported'
                                  ? 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)] border border-[var(--border-subtle)]'
                                  : acc.source === 'plaid'
                                  ? 'bg-[var(--primary-50)] text-[var(--primary-700)] border border-[var(--primary-200)]'
                                  : 'bg-[var(--bg-secondary)] text-[var(--text-tertiary)] border border-[var(--border-subtle)]'
                              }`}
                              title={
                                acc.source === 'imported'
                                  ? 'Created automatically from a CSV / PDF / OFX statement or portfolio import.'
                                  : acc.source === 'plaid'
                                  ? 'Linked via Plaid.'
                                  : 'Manually added.'
                              }
                              data-testid={`account-source-chip-${acc.id}`}
                            >
                              {ACCOUNT_SOURCE_LABELS.find((l) => l.value === acc.source)?.label ?? acc.source}
                            </span>
                          )}
                        </div>
                        {acc.description && (
                          <p
                            className="text-[11px] text-[var(--text-tertiary)] mt-1.5 italic leading-snug"
                            data-testid={`account-description-${acc.id}`}
                          >
                            {acc.description}
                          </p>
                        )}
                        <p className="numeric-lg text-primary mt-3">
                          {formatNumber(acc.current_balance)}
                        </p>
                        {acc.account_number && (
                          <p className="text-[11px] text-tertiary mt-2 font-mono">
                            {showAccountNumbers
                              ? acc.account_number
                              : `•••• ${acc.account_number.slice(-4)}`}
                          </p>
                        )}
                        </div>
                      </TiltCard>
                    ))}
                  </div>
                )}
              </div>
            ),
          },
          {
            id: 'imports',
            label: 'Imports',
            icon: 'upload_file',
            content: (
              <div data-testid="imports-tab-panel">
                <ImportStatementUpload
                  accounts={accounts}
                  onImportComplete={handleImportComplete}
                />
              </div>
            ),
          },
          {
            id: 'synchronization',
            label: 'Synchronization',
            icon: 'sync',
            content: (
              <section className="card p-6" data-testid="synchronization-tab-panel">
                <h2 className="headline-md text-primary">Synchronization</h2>
                <p className="text-sm text-secondary mt-2">Connection synchronization is not enabled for this local Atlas workspace yet.</p>
                <p className="text-sm text-tertiary mt-3">No provider, credential, or background sync is implied. Use Imports to add a statement when you need to refresh source data.</p>
              </section>
            ),
          },
          {
            id: 'data-quality',
            label: 'Data quality',
            icon: 'fact_check',
            content: (
              <section className="card p-6" data-testid="data-quality-tab-panel">
                <h2 className="headline-md text-primary">Data quality</h2>
                <p className="text-sm text-secondary mt-2">Atlas reports only what the connected source records support. Missing or stale source data is shown as unavailable rather than estimated.</p>
                <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 text-sm">
                  <div className="rounded-[var(--radius-md)] border border-[var(--border-subtle)] p-4"><dt className="text-tertiary">Active accounts</dt><dd className="numeric-md text-primary mt-1">{loading ? '—' : accounts.length}</dd></div>
                  <div className="rounded-[var(--radius-md)] border border-[var(--border-subtle)] p-4"><dt className="text-tertiary">Source status</dt><dd className="text-primary mt-1">{error ? 'Unavailable' : loading ? 'Loading' : 'Local records available'}</dd></div>
                </dl>
              </section>
            ),
          },
        ]}
      />

      {/* Edit modal — model on the existing Add form (name + type + balance).
          Institution rename is intentionally omitted: AccountResponse does
          not include `institution_name`, so the FE cannot pre-populate it.
          A separate institutional-move endpoint can be added in a follow-up.

          The submit button is rendered as a raw <button> (not the shared
          <Button> primitive) because the Button wrapper does not pass the
          HTML5 `form` attribute through — the form lives in Modal's body
          and the submit lives in Modal's footer, so we use the
          `form="edit-account-form"` HTML5 attribute to associate them. */}
      <Modal
        open={editingAccount !== null}
        onClose={cancelEdit}
        title={
          editingAccount
            ? `Edit ${editingAccount.account_name}`
            : 'Edit account'
        }
        size="md"
        footer={
          <>
            <Button
              variant="tertiary"
              onClick={cancelEdit}
              disabled={editSubmitting}
            >
              Cancel
            </Button>
            <button
              type="submit"
              form="edit-account-form"
              disabled={editSubmitting}
              data-testid="edit-account-submit"
              className="
                inline-flex items-center justify-center gap-2
                px-4 py-2 rounded-lg font-medium
                bg-[var(--danger-500)] text-[var(--text-on-brand)]
                hover:bg-[var(--danger-600)] active:bg-[var(--danger-700)]
                disabled:bg-[var(--slate-400)]
                transition-all duration-150
                focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--primary-500)]
                disabled:cursor-not-allowed
              "
            >
              {editSubmitting && (
                <Loader2
                  className="w-4 h-4 animate-spin"
                  aria-hidden="true"
                />
              )}
              {editSubmitting ? 'Saving…' : 'Save changes'}
            </button>
          </>
        }
      >
        <form
          id="edit-account-form"
          onSubmit={submitEdit}
          className="space-y-4"
          data-testid="edit-account-form"
        >
          <Input
            label="Account name"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            required
            placeholder="e.g. Chase Checking"
          />
          <Select
            label="Account type"
            value={editType}
            onChange={(e) => setEditType(e.target.value)}
            options={ACCOUNT_TYPES}
          />
          <Input
            label="Current balance"
            type="number"
            value={editBalance}
            onChange={(e) => setEditBalance(e.target.value)}
            placeholder="0.00"
          />
          <Select
            label="Family member"
            value={
              editFamilyMemberId === '' ? '' : String(editFamilyMemberId)
            }
            onChange={(e) =>
              setEditFamilyMemberId(
                e.target.value === '' ? '' : Number(e.target.value),
              )
            }
            options={familyMembers.map((m) => ({
              value: String(m.id),
              label: m.is_self ? `${m.name} (Self)` : m.name,
            }))}
          />
          {/* Phase 40 — optional account number (mirror of the Add
              Account form). Empty input maps to "do not include in
              PATCH" via ``submitEdit`` so a user who never set it
              can't accidentally re-write the column to blank/empty
              via PUT semantics (the existing whitelist in
              ``routes/accounts.py`` would otherwise overwrite with
              ``""`` — visible in the DB but rendered as nothing). */}
          <Input
            label="Account number"
            value={editAccountNumber}
            onChange={(e) => setEditAccountNumber(e.target.value)}
            placeholder="optional — e.g. •••• 1234"
          />
          {editError && (
            <p
              className="text-sm text-danger mt-3"
              role="alert"
              data-testid="edit-error"
            >
              {editError}
            </p>
          )}
        </form>
      </Modal>

      {/* Delete confirmation modal — soft-delete via DELETE /api/accounts/{id}.
          The row stays in the DB (FK preservation for transactions +
          import_batches) but flips is_active=False; listAccounts filters it. */}
      <Modal
        open={confirmingDelete !== null}
        onClose={cancelDelete}
        title="Delete account?"
        size="sm"
        footer={
          <>
            <Button
              variant="tertiary"
              onClick={cancelDelete}
              disabled={deleteSubmitting}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={submitDelete}
              disabled={deleteSubmitting}
              icon={
                deleteSubmitting ? (
                  <Loader2
                    className="w-4 h-4 animate-spin"
                    aria-hidden="true"
                  />
                ) : (
                  <Trash2 className="w-4 h-4" aria-hidden="true" />
                )
              }
            >
              {deleteSubmitting ? 'Deleting…' : 'Delete account'}
            </Button>
          </>
        }
      >
        {confirmingDelete && (
          <div className="space-y-3">
            <p className="body-md text-secondary">
              This will deactivate{' '}
              <strong className="text-primary">
                {confirmingDelete.account_name}
              </strong>{' '}
              ({confirmingDelete.account_type}). The account will stop
              appearing in your summary, but existing transactions and import
              history stay linked to it. You can reactivate it later through
              the API.
            </p>
            {deleteError && (
              <p
                className="text-sm text-danger mt-3"
                role="alert"
                data-testid="delete-error"
              >
                {deleteError}
              </p>
            )}
          </div>
        )}
      </Modal>      </AnimatedPageSection>
      </AtlasFilterProvider>
    </PageLayout>
  )
}
