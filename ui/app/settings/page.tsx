'use client'

import { useEffect, useRef, useState } from 'react'
import PageLayout from '@/components/layout/PageLayout'
import ErrorBanner from '@/components/ui/ErrorBanner'
import { Button, Input, Select } from '@/components/ui'
import Modal from '@/components/ui/Modal'
import {
  rulesService,
  type Profile,
  type MerchantRule,
  type Category,
} from '@/lib/api'
import type { FamilyMember, MerchantRuleSource } from '@/lib/api'
import {
  MERCHANT_RULE_SOURCE_OPTIONS,
  RELATIONSHIP_OPTIONS,
  WORKING_STATUS_OPTIONS,
  type Relationship,
  type WorkingStatus,
} from '@/lib/api'
import { classifyErrorMessage } from '@/lib/errors'
import { fireDataRefresh } from '@/lib/dataRefresh'
import AppearanceSection from '@/components/settings/AppearanceSection'
import ReadinessSection from '@/components/settings/ReadinessSection'
import PageHeader from '@/components/ui/PageHeader'

/**
 * Phase F2 #2 -- delegate to the centralized classifier imported
 * above so this page and the Overview render the same friendly
 * messages. The 502 -> "Downstream service is unavailable..." map
 * kills the "Session expired" flash that surfaces on JWT_SECRET drift
 * between rules-service and Finlynq.
 */
const CURRENCY_OPTIONS = [
  { value: 'USD', label: 'USD — US Dollar' },
  { value: 'EUR', label: 'EUR — Euro' },
  { value: 'GBP', label: 'GBP — British Pound' },
  { value: 'JPY', label: 'JPY — Japanese Yen' },
  { value: 'CAD', label: 'CAD — Canadian Dollar' },
  { value: 'AUD', label: 'AUD — Australian Dollar' },
]

/** Phase 27 — per-source chip colour map. Drives the per-row badge
 *  + the filter-pill active state so the user sees the same colour
 *  vocabulary next to every "system" / "manual" / etc. identifier.
 *  Kept in one place so a future tweak (e.g. greener "imported")
 *  lands at one site, not five. */
const SOURCE_COLOR: Record<MerchantRuleSource, string> = {
  system: '#475569',     // slate — neutral, the "always there" baseline
  manual: '#0369a1',     // deep sky — user-initiated, readable on light canvas
  'tag-rule': '#0f766e', // deep teal — Activity page's promote flow
  llm: '#c2410c',        // deep orange — forward-compat for Pass-4 writes
  imported: '#15803d',   // deep green — CSV audit trail
}

/** Phase 27 — label text for the per-source chip + filter pill.
 *  Stores the human-readable text so the FE never echoes the raw
 *  enum value verbatim (e.g. renders "System seed (fizzy)" rather
 *  than "system"). Falls back to the raw value if a future source
 *  type slips through the BE without being added here. */
function sourceLabel(s: string | undefined | null): string {
  const opt = MERCHANT_RULE_SOURCE_OPTIONS.find((o) => o.value === s)
  if (opt) return opt.label
  return s ?? '—'
}

/**
 * Phase 24 + 27 sub-component — the Merchant Rules card body.
 *
 * Lives at file scope so the JSX in :func:`SettingsPage` stays
 * readable. The card mirrors the layout of the Family Members card:
 * a single ``card p-6 max-w-2xl`` block with a heading + list +
 * add-form. Rules render grouped by category so the user can see at
 * a glance which keywords resolve to "Food & Dining" vs
 * "Bills & Utilities".
 *
 * Each rule row carries:
 *  - a Source chip (Phase 27) so the user can answer "did this come
 *    from the seed, from a Tag Rule, or from a CSV import?" at a
 *    glance,
 *  - Edit + Delete affordances (Phase 26),
 *  - Restore for archived rows (Phase 26).
 *
 * The card header also hosts (Phase 27):
 *  - source filter pills (a row of chips so the user can scope the
 *    list to "system only" or "manual only" etc.),
 *  - Export button (downloads a CSV of every rule via the
 *    ``exportMerchantRules`` helper + a Blob URL),
 *  - Import button + hidden <input type="file"> (uploads a CSV via
 *    the ``importMerchantRules`` helper, then renders the BE
 *    summary inline: inserted / skipped_existing / per-row errors).
 *
 * Action handlers live on the parent (``SettingsPage``) so the file
 * upload lifecycle is observable in the page-level React DevTools
 * tree; this component only renders UI + delegates.
 */
function MerchantRulesCard({
  rules,
  categories,
  loading,
  error,
  onRetry,
  archivedFilter,
  onToggleArchived,
  showForm,
  onToggleForm,
  form,
  submitting,
  formError,
  onSubmit,
  onStartDelete,
  onStartEdit,
  onStartRestore,
  restoreRuleId,
  restoreRuleError,
  showCategoryForm,
  onToggleCategoryForm,
  newCategoryName,
  setNewCategoryName,
  addCategorySubmitting,
  addCategoryError,
  onSubmitCategory,
  // Phase 33 — Category filter dropdown.
  categoryFilter,
  onChangeCategoryFilter,
  // Phase 27 — Source filter + Export + Import wiring.
  // Phase 27 — Source filter + Export + Import wiring.
  sourceFilter,
  onChangeSourceFilter,
  exporting,
  importExportBanner,
  onExport,
  onImportFilePicked,
  importing,
  /** Phase 29 — Clean up duplicates affordance. The parent owns
   *  the wizard modal + Apply handler; this prop is just a
   *  click trigger. The button renders a tooltip that
   *  documents the two-layer dedup (L1 substring + L2 LLM)
   *  so the user understands what they're getting into. */
  onOpenDedupeWizard,
}: {
  rules: MerchantRule[]
  categories: Category[]
  loading: boolean
  error: string | null
  onRetry: () => void
  archivedFilter: 'active' | 'archived' | 'all'
  onToggleArchived: () => void
  showForm: boolean
  onToggleForm: () => void
  form: {
    categoryId: string
    setCategoryId: (v: string) => void
    keyword: string
    setKeyword: (v: string) => void
  }
  submitting: boolean
  formError: string | null
  onSubmit: (e: React.FormEvent) => Promise<void> | void
  onStartDelete: (rule: MerchantRule) => void
  /** Phase 26 — Edit affordance mirrors the Family Members card's
   *  ``startEditMember`` handler. Opens the Edit modal pre-filled
   *  with the current keyword/category/priority. */
  onStartEdit: (rule: MerchantRule) => void
  /** Phase 26 — Restore affordance for soft-deleted (``is_archived``)
   *  rules. Single-click PUT ``is_archived=false``; no confirmation
   *  modal because restoring is non-destructive (re-adds the rule
   *  to the categorizer's scan list). */
  onStartRestore: (rule: MerchantRule) => void
  /** Phase 26 — per-row in-flight tracker so the Restore button on
   *  a row that is mid-restore renders "Restoring…" + disabled, while
   *  every other Restore button stays live. ``null`` == no row in
   *  flight. */
  restoreRuleId: number | null
  /** Phase 26 — surfaces GET/PUT errors from the restore path on the
   *  card banner. Reads alongside ``error`` (the list-load error)
   *  so a 4xx restore error doesn't get bucketed as a list-load
   *  failure and a stale retry. */
  restoreRuleError: string | null
  /** Phase 25 — inline "Add new category" affordance so a category
   *  that doesn't yet exist can be created FROM this card without
   *  bouncing the user to a separate page. Parent owns the POST. */
  showCategoryForm: boolean
  onToggleCategoryForm: () => void
  newCategoryName: string
  setNewCategoryName: (v: string) => void
  addCategorySubmitting: boolean
  addCategoryError: string | null
  onSubmitCategory: (e: React.FormEvent) => Promise<void> | void
  /** Phase 33 — current category filter. ``''`` means no filter
   *  (show all categories). When set to a non-empty category id
   *  string, only rules in that category are displayed (server-
   *  side filtered via ``?category_id=``). */
  categoryFilter: string
  /** Phase 33 — category dropdown change handler. ``''`` clears
   *  the filter so the list shows rules from every category. */
  onChangeCategoryFilter: (next: string) => void
  /** Phase 27 — current source filter. ``'all'`` is the unset
   *  sentinel so the pill row's <button> list can disable the
   *  "All" pill with a single comparison. */
  sourceFilter: MerchantRuleSource | 'all'
  /** Phase 27 — pill click handler. ``'all'`` clears the filter so
   *  the list shows rows from every provenance. */
  onChangeSourceFilter: (next: MerchantRuleSource | 'all') => void
  /** Phase 27 — in-flight guard on Export so a fat-finger double
   *  click doesn't trigger two CSV downloads. */
  exporting: boolean
  /** Phase 27 — last-action banner (export success / import
   *  summary). The parent owns the message text; this component
   *  just renders. */
  importExportBanner: {
    variant: 'success' | 'warning' | 'danger'
    title: string
    message: string
  } | null
  /** Phase 27 — Export button click handler. Fires the Blob URL
   *  download in the parent (where the helper lives). */
  onExport: () => void
  /** Phase 27 — called when the user picks a file from the hidden
   *  <input type="file">. Parent owns the upload so the in-flight
   *  flag + summary banner stay in lockstep. */
  onImportFilePicked: (file: File) => void
  /** Phase 27 — in-flight guard on Import so a user can't pile
   *  uploads while the first is still parsing on the BE. */
  importing: boolean
  /** Phase 29 — open the dedup wizard modal. The wizard lives in
   *  the parent's JSX so this component just hosts the trigger
   *  button. The modal handles the scan + Apply flow. */
  onOpenDedupeWizard: () => void
}) {
  // Group rules by category for the list view. The Settings card
  // renders one section per category — matching the Family Members
  // "Self first, then everyone else" pattern. We sort categories
  // alphabetically so the order is deterministic across sessions.
  // Phase D — group rules by category, then by category group.
  // Build a group lookup from the categories prop.
  const groupByName = new Map<string, string>()
  for (const c of categories) {
    groupByName.set(c.name.toLowerCase(), c.group || 'Expenses')
  }

  const byCategory = new Map<string, MerchantRule[]>()
  for (const rule of rules) {
    const cat = rule.category_name ?? '— Uncategorised —'
    if (!byCategory.has(cat)) byCategory.set(cat, [])
    byCategory.get(cat)!.push(rule)
  }
  const sortedCategories = Array.from(byCategory.keys()).sort((a, b) => {
    const ga = groupByName.get(a.toLowerCase()) || 'Z'
    const gb = groupByName.get(b.toLowerCase()) || 'Z'
    if (ga !== gb) return ga.localeCompare(gb)
    return a.localeCompare(b)
  })

  // Phase 27 — hidden <input type="file"> ref so the parent can
  // trigger a click programmatically when the user hits the
  // visible Import button (avoids the OS-native file picker
  // being shown twice).
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const sourceFilterOptions: Array<{ value: MerchantRuleSource | 'all'; label: string }> = [
    { value: 'all', label: 'All sources' },
    ...MERCHANT_RULE_SOURCE_OPTIONS.map((o) => ({ value: o.value, label: o.label })),
  ]

  return (
    <div className="mt-8 card p-6 max-w-2xl" data-testid="merchant-rules-card">
      <div className="flex items-start justify-between gap-4 mb-2">
        <div>
          <h2 className="headline-md text-primary">Merchant Rules</h2>
          <p className="text-sm text-secondary mt-1">
            Add or remove substring keywords the auto-categorizer uses
            to tag incoming transactions. Rules you add here are
            picked up on the next categorization batch — no BE
            redeploy required.
          </p>
        </div>
        <button
          type="button"
          onClick={onToggleArchived}
          className="text-xs text-secondary hover:text-primary px-2 py-1
                     rounded transition-colors duration-150
                     border border-outline-variant/40"
          title={
            archivedFilter === 'active'
              ? 'Show only archived (soft-deleted) rules.'
              : archivedFilter === 'archived'
                ? 'Show all rules (active + archived).'
                : 'Show only active rules.'
          }
          data-testid="merchant-rules-toggle-archived"
        >
          {archivedFilter === 'active'
            ? 'Active only'
            : archivedFilter === 'archived'
              ? 'Archived only'
              : 'All rules'}
        </button>
      </div>

      {/* Phase 33 — Category filter dropdown. Scoped next to the
          Source filter pills so all filter controls sit together
          in a single visual row. Uses the ``categories`` list
          prop (already loaded by the parent). */}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Select
          label="Category"
          value={categoryFilter}
          onChange={(e) => onChangeCategoryFilter(e.target.value)}
          options={[
            { value: '', label: 'All categories' },
            ...categories.map((c) => ({
              value: String(c.id),
              label: c.name,
            })),
          ]}
          data-testid="merchant-rules-category-filter"
        />
      </div>

      {/* Phase 29 — Clean up duplicates button. Sits at the head of
          the action row (before Export/Import) because it's the
          natural next step for a user who notices redundant rules
          in the list — "I should consolidate these" maps to this
          button. The wizard opens in the parent (where the
          state + Apply handler live). */}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="primary"
          onClick={onOpenDedupeWizard}
          data-testid="merchant-rules-dedupe"
          title="Find duplicate or near-duplicate rules and merge them. Combines a deterministic substring scan with an optional LLM semantic pass."
        >
          Clean up duplicates
        </Button>
      </div>

      {/* Phase 27 — Export + Import buttons + per-source filter pills.
          Sits inline below the card header so the user has a single
          row of actions before the list itself. The hidden
          <input type="file"> clicks via ``fileInputRef.current?.click()``
          so the visible Import button is the only thing the user
          touches (smooth UX; no surprise OS dialog from the keyboard). */}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="tertiary"
          onClick={onExport}
          disabled={exporting}
          data-testid="merchant-rules-export"
          title="Download every rule as a CSV (includes archived rules)"
        >
          {exporting ? 'Preparing…' : 'Export CSV'}
        </Button>
        <Button
          type="button"
          variant="tertiary"
          onClick={() => fileInputRef.current?.click()}
          disabled={importing}
          data-testid="merchant-rules-import"
          title="Upload a CSV exported from this page. Duplicate (category_id, keyword) pairs are skipped."
        >
          {importing ? 'Importing…' : 'Import CSV'}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          data-testid="merchant-rules-import-file"
          onChange={(e) => {
            const file = e.target.files?.[0]
            // Always reset the input's value after a pick so the
            // SAME file can be re-imported without a manual diff.
            // Browsers cache identical File objects by reference
            // otherwise, and a re-pick of the exact same file
            // would silently no-op on ``onChange``.
            e.target.value = ''
            if (file) onImportFilePicked(file)
          }}
        />
      </div>

      {/* Phase 27 — source filter pills. Active pill carries the
          source colour in a solid fill; inactive pills carry a
          dashed border so the user can read the row at a glance. */}
      <div
        className="mt-3 flex flex-wrap items-center gap-1.5"
        data-testid="merchant-rules-source-filter"
        role="tablist"
        aria-label="Filter rules by source"
      >
        <span className="label-xs uppercase tracking-wider text-tertiary mr-1">
          Source:
        </span>
        {sourceFilterOptions.map((opt) => {
          const isActive = sourceFilter === opt.value
          const tint =
            opt.value === 'all' ? '#475569' : SOURCE_COLOR[opt.value]
          return (
            <button
              key={opt.value}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => onChangeSourceFilter(opt.value)}
              data-testid={`merchant-rules-source-filter-${opt.value}`}
              className={
                isActive
                  ? 'px-2.5 py-1 rounded-full text-[11px] font-semibold text-white transition-colors duration-150'
                  : 'px-2.5 py-1 rounded-full text-[11px] font-semibold border border-dashed hover:bg-[var(--bg-tertiary)] transition-colors duration-150'
              }
              style={isActive ? { backgroundColor: tint } : { borderColor: tint, color: tint }}
            >
              {opt.label}
            </button>
          )
        })}
      </div>

      {importExportBanner && (
        <ErrorBanner
          title={importExportBanner.title}
          message={importExportBanner.message}
          variant={importExportBanner.variant}
        />
      )}

      {error && (
        <ErrorBanner
          title="Couldn't load merchant rules:"
          message={error}
          variant="warning"
          onRetry={onRetry}
        />
      )}

      {restoreRuleError && (
        <ErrorBanner
          title="Couldn't restore rule:"
          message={restoreRuleError}
          variant="warning"
        />
      )}

      {loading ? (
        <p
          className="text-sm text-secondary mt-3"
          data-testid="merchant-rules-loading"
        >
          Loading rules…
        </p>
      ) : byCategory.size === 0 ? (
        <div
          className="text-sm text-secondary p-4 mt-3 border border-dashed rounded-lg"
          data-testid="merchant-rules-empty"
        >
          No merchant rules match the current filters. Click{' '}
          <strong>Add rule</strong> to create one, or clear the source
          filter pill to see every row.
        </div>
      ) : (
        <div className="space-y-4 mt-4 mb-4" data-testid="merchant-rules-list">
          {(() => {
            // Phase D — render group headers between category groups.
            const GROUP_COLORS: Record<string, string> = {
              Income: '#047857', Expenses: '#B91C1C', Debt: '#B45309',
              Investments: '#0369A1', Transfer: '#4B5563',
            }
            const elements: React.ReactNode[] = []
            let lastGroup = ''
            for (const catName of sortedCategories) {
              const group = byCategory.get(catName) ?? []
              const catGroup = groupByName.get(catName.toLowerCase()) || 'Expenses'
              if (catGroup !== lastGroup) {
                lastGroup = catGroup
                const gColor = GROUP_COLORS[catGroup] || '#94a3b8'
                elements.push(
                  <div key={`group-header-${catGroup}`} className="flex items-center gap-2 mt-3 mb-1">
                    <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: gColor }} />
                    <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: gColor }}>
                      {catGroup}
                    </span>
                  </div>,
                )
              }
              elements.push(
                <div key={catName}>
                  <h3
                    className="label-xs uppercase tracking-wider text-secondary
                               border-b border-outline-variant/30 pb-1 mb-2"
                  >
                    {catName}{' '}
                    <span className="text-tertiary">({group.length})</span>
                  </h3>
                <ul className="space-y-1.5">
                  {group.map((rule) => (
                    <li
                      key={rule.id}
                      className="flex items-center gap-3 px-3 py-1.5
                                 rounded-lg border border-outline-variant/30
                                 text-sm"
                      data-testid={`merchant-rule-row-${rule.id}`}
                    >
                      <span
                        aria-hidden="true"
                        className="inline-flex items-center justify-center
                                   w-6 h-6 rounded-md bg-surface-container
                                   text-on-surface-variant text-[10px] font-mono"
                        title={`Priority ${rule.priority} (lower = scanned first)`}
                      >
                        {rule.priority}
                      </span>
                      {/* Phase 27 — per-row Source chip. Coloured via
                          the SOURCE_COLOR map; the user's at-a-glance
                          answer to "did this come from the seed or from
                          a Tag Rule?". The label echoes the human-
                          friendly text ("System seed (fizzy)" rather
                          than "system") so non-coders parse it. */}
                      <span
                        className="inline-flex items-center px-2 py-0.5
                                   rounded-full text-[10px] font-bold
                                   uppercase tracking-wider text-white"
                        style={{
                          backgroundColor: SOURCE_COLOR[rule.source] ?? '#94a3b8',
                        }}
                        title={`Source: ${sourceLabel(rule.source)}`}
                        data-testid={`merchant-rule-source-${rule.id}`}
                      >
                        {sourceLabel(rule.source)}
                      </span>
                      <span
                        className={
                          rule.is_archived
                            ? 'flex-1 font-mono text-[12px] text-tertiary line-through'
                            : 'flex-1 font-mono text-[12px] text-primary'
                        }
                      >
                        {rule.keyword}
                      </span>
                      {rule.is_archived && (
                        <span
                          aria-label="Archived"
                          title="Soft-deleted rule"
                          className="text-[10px] uppercase tracking-wider
                                     text-tertiary"
                          data-testid={`merchant-rule-archived-${rule.id}`}
                        >
                          archived
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={() => onStartEdit(rule)}
                        aria-label={`Edit rule ${rule.keyword}`}
                        className="text-xs text-secondary hover:text-primary
                                   px-2 py-1 rounded transition-colors duration-150"
                        data-testid={`merchant-rule-edit-${rule.id}`}
                      >
                        Edit
                      </button>
                      {!rule.is_archived ? (
                        <button
                          type="button"
                          onClick={() => onStartDelete(rule)}
                          aria-label={`Delete rule ${rule.keyword}`}
                          className="text-xs text-secondary hover:text-[var(--danger-600)]
                                     px-2 py-1 rounded transition-colors duration-150"
                          data-testid={`merchant-rule-delete-${rule.id}`}
                        >
                          Delete
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => onStartRestore(rule)}
                          disabled={restoreRuleId === rule.id}
                          aria-label={`Restore rule ${rule.keyword}`}
                          className="text-xs text-secondary hover:text-[var(--primary-600)]
                                     disabled:opacity-40 disabled:cursor-not-allowed
                                     px-2 py-1 rounded transition-colors duration-150"
                          data-testid={`merchant-rule-restore-${rule.id}`}
                        >
                          {restoreRuleId === rule.id ? 'Restoring…' : 'Restore'}
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )
            }
            return elements
          })()}
        </div>
      )}

      <Button
        variant="secondary"
        onClick={onToggleForm}
        data-testid="add-merchant-rule"
      >
        {showForm ? 'Cancel' : 'Add rule'}
      </Button>

      {/* Phase 25 — sibling affordance so the user can grow the
        category taxonomy from this card without bouncing elsewhere.
        Renders inline BELOW 'Add rule' / inline ABOVE the rule
        submission so a user who doesn't see their target category
        in the dropdown can create one first. */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          variant="tertiary"
          onClick={onToggleCategoryForm}
          data-testid="settings-add-category"
        >
          {showCategoryForm ? 'Cancel' : 'Add new category'}
        </Button>
        <span className="label-sm text-tertiary">
          Need a category the rules dropdown doesn&apos;t list? Create one
          here first, then add the rule.
        </span>
      </div>

      {showCategoryForm && (
        <form
          onSubmit={onSubmitCategory}
          className="mt-3 space-y-3"
          data-testid="settings-add-category-form"
        >
          <Input
            label="Category name"
            value={newCategoryName}
            onChange={(e) => setNewCategoryName(e.target.value)}
            required
            placeholder="e.g. Pet Supplies"
            data-testid="settings-add-category-input"
          />
          {addCategoryError && (
            <p className="text-sm text-danger" role="alert">
              {addCategoryError}
            </p>
          )}
          <div className="flex gap-2">
            <Button
              type="submit"
              variant="primary"
              disabled={addCategorySubmitting}
              data-testid="settings-add-category-submit"
            >
              {addCategorySubmitting ? 'Creating…' : 'Create category'}
            </Button>
            <Button
              type="button"
              variant="tertiary"
              onClick={onToggleCategoryForm}
              disabled={addCategorySubmitting}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}

      {/* Phase 25 — the rule form's category dropdown now reads
        from the canonical categories list (not ``byCategory.keys()``
        which only included categories that already had rules). The
        previous build silently dropped categories with zero rules
        from the dropdown — a fresh-user false-negative. */}
      {showForm && (
        <form
          onSubmit={onSubmit}
          className="mt-4 space-y-3"
          data-testid="create-merchant-rule-form"
        >
          <Select
            label="Category"
            value={form.categoryId}
            onChange={(e) => form.setCategoryId(e.target.value)}
            options={[
              { value: '', label: '— Pick a category —' },
              ...categories.map((c) => ({
                value: String(c.id),
                label: c.name,
              })),
            ]}
            data-testid="create-rule-category"
          />
          <Input
            label="Keyword"
            value={form.keyword}
            onChange={(e) => form.setKeyword(e.target.value)}
            required
            placeholder="e.g. FID BPG SVC"
            data-testid="create-rule-keyword"
          />
          <p className="text-xs text-tertiary -mt-1">
            Stored upper-cased server-side. Matched as a case-insensitive
            substring. Priority is auto-assigned to the bottom of the
            category (max + 10) so a new rule never displaces an existing
            one in the scan order.
          </p>
          {formError && (
            <p className="text-sm text-danger" role="alert">
              {formError}
            </p>
          )}
          <div className="flex gap-2">
            <Button
              type="submit"
              variant="primary"
              disabled={submitting}
              data-testid="create-rule-submit"
            >
              {submitting ? 'Adding…' : 'Add rule'}
            </Button>
            <Button
              type="button"
              variant="tertiary"
              onClick={onToggleForm}
              disabled={submitting}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}
    </div>
  )
}

export default function SettingsPage() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)

  // Form state
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [currency, setCurrency] = useState('USD')
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Reconcile state
  const [reconciling, setReconciling] = useState(false)
  const [reconcileMessage, setReconcileMessage] = useState<string | null>(null)
  const [reconcileError, setReconcileError] = useState<string | null>(null)

  // Delete-all-data state
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  // Phase 16 — Family Members card state. Mirrors the goal-management
  // dashboard pattern: parallel `loading` / list state, per-row edit modal,
  // and a confirm-archive modal whose error message surfaces the BE 409
  // "N active account(s) still linked" detail if the user tries to archive
  // a Spouse / Kid that still owns active accounts.
  const [familyMembers, setFamilyMembers] = useState<FamilyMember[]>([])
  const [membersLoading, setMembersLoading] = useState(true)
  const [membersError, setMembersError] = useState<string | null>(null)
  const [membersRetryCount, setMembersRetryCount] = useState(0)

  const [showMemberForm, setShowMemberForm] = useState(false)
  const [memberName, setMemberName] = useState('')
  const [memberColor, setMemberColor] = useState('#3b82f6')
  // Phase 16+ — household profile fields. Defaults are all
  // "unset" (empty string for selects, '' for age) so the form
  // lands in two clicks (name+color) and the user can layer in
  // relationship/working_status/age later via edit.
  const [memberRelationship, setMemberRelationship] = useState<Relationship | ''>('')
  const [memberWorkingStatus, setMemberWorkingStatus] = useState<WorkingStatus | ''>('')
  const [memberAge, setMemberAge] = useState<string>('')
  const [memberSubmitting, setMemberSubmitting] = useState(false)
  const [memberFormError, setMemberFormError] = useState<string | null>(null)

  const [editingMember, setEditingMember] = useState<FamilyMember | null>(null)
  const [editMemberName, setEditMemberName] = useState('')
  const [editMemberColor, setEditMemberColor] = useState('#3b82f6')
  // Phase 16+ — mirror the create-form household-profile fields.
  // ``editMemberRelationship`` stays read-only on the Self row so
  // the user never sees an auto-reverted value (the BE locks the
  // Self relationship to 'Self'); for non-Self rows the dropdown
  // is freely editable.
  const [editMemberRelationship, setEditMemberRelationship] = useState<Relationship | ''>('')
  const [editMemberWorkingStatus, setEditMemberWorkingStatus] = useState<WorkingStatus | ''>('')
  const [editMemberAge, setEditMemberAge] = useState<string>('')
  const [editMemberSubmitting, setEditMemberSubmitting] = useState(false)
  const [editMemberError, setEditMemberError] = useState<string | null>(null)
  const [confirmingMemberDelete, setConfirmingMemberDelete] = useState<FamilyMember | null>(null)
  const [memberDeleteSubmitting, setMemberDeleteSubmitting] = useState(false)
  const [memberDeleteError, setMemberDeleteError] = useState<string | null>(null)

  // Phase 24 — Merchant Rules card state. Mirrors the Family Members
  // card pattern: parallel loading / list state, add form, per-row
  // delete confirmation. The settings card is intentionally simpler
  // than Family Members — there's no edit modal (priority is not
  // user-editable in v1) and no archive-toggle (DELETE is the
  // soft-delete path on the BE; UN-archive is via the un-archive
  // toggle in this card).
  const [rules, setRules] = useState<MerchantRule[]>([])
  const [rulesLoading, setRulesLoading] = useState(true)
  const [rulesError, setRulesError] = useState<string | null>(null)
  const [rulesRetryCount, setRulesRetryCount] = useState(0)
  const [showRuleForm, setShowRuleForm] = useState(false)
  const [newRuleCategory, setNewRuleCategory] = useState('')
  const [newRuleKeyword, setNewRuleKeyword] = useState('')
  const [ruleSubmitting, setRuleSubmitting] = useState(false)
  const [ruleFormError, setRuleFormError] = useState<string | null>(null)
  // Phase 32 — tri-state archived filter. 'active' = show only active
  // rules (default), 'archived' = show only archived rules, 'all' = show both.
  // Always fetches with include_archived=true so the BE returns all rows;
  // FE-side filtering keeps the toggle instant (no refetch on toggle).
  const [archivedFilter, setArchivedFilter] = useState<'active' | 'archived' | 'all'>('active')
  const [confirmingRuleDelete, setConfirmingRuleDelete] = useState<MerchantRule | null>(null)
  const [ruleDeleteSubmitting, setRuleDeleteSubmitting] = useState(false)
  const [ruleDeleteError, setRuleDeleteError] = useState<string | null>(null)
  // Phase 26 — Edit / Restore merchant rule state. Mirrors the
  // Family Members edit-modal pattern (startEditMember -> submitEditMember)
  // so a user can correct a mis-keyworded rule OR change its target
  // category without a hard delete + re-add cycle. ``editingRule``
  // drives Modal ``open``: ``null`` means closed. ``restoreRuleId``
  // is a per-id in-flight flag so only the one being restored shows
  // "Restoring…" (mirrors the Family Members self-row disabled state).
  const [editingRule, setEditingRule] = useState<MerchantRule | null>(null)
  const [editRuleCategoryId, setEditRuleCategoryId] = useState('')
  const [editRuleKeyword, setEditRuleKeyword] = useState('')
  const [editRulePriority, setEditRulePriority] = useState('')
  const [editRuleSubmitting, setEditRuleSubmitting] = useState(false)
  const [editRuleError, setEditRuleError] = useState<string | null>(null)
  const [restoreRuleId, setRestoreRuleId] = useState<number | null>(null)
  const [restoreRuleError, setRestoreRuleError] = useState<string | null>(null)
  // Phase 25 — categories list + add-category-form state. Categories
  // are loaded once on mount + refreshed whenever the user creates a
  // new one from the inline form below. Sharing the same source of
  // truth as the rule-form dropdown so a freshly-created category
  // surfaces in ``categories`` without a page reload.
  const [categories, setCategories] = useState<Category[]>([])
  const [showCategoryForm, setShowCategoryForm] = useState(false)
  const [newCategoryName, setNewCategoryName] = useState('')
  const [addCategorySubmitting, setAddCategorySubmitting] = useState(false)
  const [addCategoryError, setAddCategoryError] = useState<string | null>(null)
  // Phase 27 — Source filter (drives both the ?source= Query and
  // the pill row's active state) + Export/Import in-flight flags +
  // the importExportBanner that surfaces the BE summary
  // (``inserted: N, skipped_existing: K, errors: [...]``) inline.
  // Phase 29 — Clean up duplicates wizard state. ``showDedupeWizard``
  // opens the modal; ``dedupeResult`` holds the response from
  // ``findDuplicateMerchantRules``; ``dedupeLoading`` is the in-flight
  // flag (the modal shows a spinner while the L1/L2 round-trip
  // resolves); ``includeLlm`` toggles the L2 pass; ``dedupeBanner``
  // surfaces a partial-success / failure banner; ``dedupeApplyResult``
  // is set on a successful Apply call (closed by the user clicking
  // "Done"). All state lives in the parent so the in-card banner
  // and the modal's footer can read from the same source of truth.
  const [sourceFilter, setSourceFilter] = useState<MerchantRuleSource | 'all'>('all')
  // Phase 33 — category filter dropdown. '' means all categories.
  const [categoryFilter, setCategoryFilter] = useState<string>('')
  const [exporting, setExporting] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importExportBanner, setImportExportBanner] = useState<
    | {
        variant: 'success' | 'warning' | 'danger'
        title: string
        message: string
      }
    | null
  >(null)
  // Phase 29 — dedup wizard state.
  const [showDedupeWizard, setShowDedupeWizard] = useState(false)
  const [dedupeResult, setDedupeResult] = useState<{
    groups: Array<{
      canonical: { id: number; keyword: string }
      candidates: Array<{
        id: number
        keyword: string
        method: 'substring' | 'llm'
        confidence: number
        rationale: string
      }>
    }>
    l1_count: number
    l2_count: number
    /** Phase 29 — the L2 pass status so the FE can render honest
     *  partial-success banners. ``'ok'`` = L2 ran clean,
     *  ``'offline'`` = Ollama unreachable (L1-only payload),
     *  ``'malformed'`` = L2 returned unparseable JSON,
     *  ``'skipped'`` = the L1-only endpoint was hit so L2 was
     *  never attempted (the user explicitly didn't opt in). */
    l2_status: 'ok' | 'offline' | 'malformed' | 'skipped'
  } | null>(null)
  const [dedupeLoading, setDedupeLoading] = useState(false)
  const [includeLlm, setIncludeLlm] = useState(false)
  const [dedupeBanner, setDedupeBanner] = useState<
    | {
        variant: 'success' | 'warning' | 'danger'
        title: string
        message: string
      }
    | null
  >(null)
  const [acceptedCandidates, setAcceptedCandidates] = useState<number[]>([])
  const [dedupeApplying, setDedupeApplying] = useState(false)
  const [dedupeApplyResult, setDedupeApplyResult] = useState<
    | { archived: number; skipped: number }
    | null
  >(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const p = await rulesService.getProfile()
        if (!cancelled) {
          setProfile(p)
          setFullName(p.full_name ?? '')
          setEmail(p.email ?? '')
          setCurrency(p.currency_preference ?? 'USD')
          setLoading(false)
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(classifyErrorMessage(err))
          setLoading(false)
        }
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [retryCount])

  // Phase 16 — Family Members list fetcher. Mirrors the profile-load
  // effect: per-retry refetch via `membersRetryCount`, so the
  // ErrorBanner retry button can drive the same path.
  useEffect(() => {
    let cancelled = false
    const loadMembers = async () => {
      setMembersLoading(true)
      setMembersError(null)
      try {
        const rows = await rulesService.listFamilyMembers()
        if (!cancelled) {
          setFamilyMembers(rows)
          setMembersLoading(false)
        }
      } catch (err: any) {
        if (!cancelled) {
          setMembersError(classifyErrorMessage(err))
          setMembersLoading(false)
        }
      }
    }
    loadMembers()
    return () => {
      cancelled = true
    }
  }, [membersRetryCount])

  // Phase 24 + 27 + 32 — Merchant Rules list fetcher. Always fetches
  // with ``include_archived=true`` so the BE returns ALL rows; the
  // FE-side ``archivedFilter`` slices the list without a refetch.
  // The source filter pill still drives ``?source=...``.
  useEffect(() => {
    let cancelled = false
    const loadRules = async () => {
      setRulesLoading(true)
      setRulesError(null)
      try {
        const rows = await rulesService.listMerchantRules({
          include_archived: true,
          source: sourceFilter === 'all' ? undefined : sourceFilter,
          category_id: categoryFilter ? Number(categoryFilter) : undefined,
        })
        if (!cancelled) {
          // Phase 32 — FE-side archived filter. Slices the full response
          // so toggling is instant (no network round-trip).
          const filtered =
            archivedFilter === 'active'
              ? rows.filter((r) => !r.is_archived)
              : archivedFilter === 'archived'
                ? rows.filter((r) => r.is_archived)
                : rows
          setRules(filtered)
          setRulesLoading(false)
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setRulesError(classifyErrorMessage(err))
          setRulesLoading(false)
        }
      }
    }
    loadRules()
    return () => {
      cancelled = true
    }
  }, [rulesRetryCount, archivedFilter, sourceFilter, categoryFilter])

  // Phase 25 — categories list fetcher (drives the rule form's
  // category <Select> dropdown so the chosen value matches a real
  // Category.id). Refetched via ``categoriesRetryCount`` so the
  // handleAddCategory success path can ``+1`` and surface the new
  // category in the rule dropdown on the next render WITHOUT a
  // page reload.
  const [categoriesRetryCount, setCategoriesRetryCount] = useState(0)
  useEffect(() => {
    let cancelled = false
    const loadCategories = async () => {
      try {
        const rows = await rulesService.listCategories()
        if (!cancelled) setCategories(rows)
      } catch {
        if (!cancelled) setCategories([])
      }
    }
    loadCategories()
    return () => {
      cancelled = true
    }
  }, [categoriesRetryCount])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setSaveMessage(null)
    setSaveError(null)
    try {
      const updated = await rulesService.updateProfile({
        full_name: fullName,
        email,
        currency_preference: currency,
      })
      setProfile(updated)
      setSaveMessage('Settings saved.')
    } catch (err: any) {
      setSaveError(classifyErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteAllData = async () => {
    setDeleting(true)
    setDeleteMessage(null)
    setDeleteError(null)
    try {
      const result = await rulesService.deleteAllData()
      const parts: string[] = []
      if (result.deleted_transactions > 0) parts.push(`${result.deleted_transactions} transactions`)
      if (result.deleted_import_batches > 0) parts.push(`${result.deleted_import_batches} import batches`)
      if (result.deleted_goals > 0) parts.push(`${result.deleted_goals} goals`)
      if (result.deleted_accounts > 0) parts.push(`${result.deleted_accounts} accounts`)
      setDeleteMessage(
        parts.length > 0
          ? `Deleted: ${parts.join(', ')}. Navigate to the Overview to see your updated dashboard.`
          : 'No data to delete — your account is already clean.'
      )
      // Notify every page to refresh — all balances / counts changed.
      fireDataRefresh()
    } catch (err: unknown) {
      setDeleteError(classifyErrorMessage(err))
    } finally {
      setDeleting(false)
      setShowDeleteModal(false)
    }
  }

  const handleReconcile = async () => {
    setReconciling(true)
    setReconcileMessage(null)
    setReconcileError(null)
    try {
      const result = await rulesService.reconcileBalances()
      setReconcileMessage(
        `Reconciled ${result.reconciled} account${result.reconciled === 1 ? '' : 's'}. All balances are now in sync.`
      )
      fireDataRefresh()
    } catch (err: unknown) {
      setReconcileError(classifyErrorMessage(err))
    } finally {
      setReconciling(false)
    }
  }

  // Phase 16 — Family Members card handlers --------------------------------

  const handleCreateMember = async (e: React.FormEvent) => {
    e.preventDefault()
    setMemberSubmitting(true)
    setMemberFormError(null)
    try {
      await rulesService.createFamilyMember({
        name: memberName.trim(),
        color: memberColor,
        // Phase 16+ — ship household-profile fields only when the
        // user filled them in. Empty strings / blank age submit as
        // ``undefined`` so the Pydantic schema treats them as
        // unset (column stays NULL) rather than committing literal
        // empty strings (which the Literal enums would 422 on).
        relationship:
          memberRelationship === '' ? undefined : memberRelationship,
        working_status:
          memberWorkingStatus === '' ? undefined : memberWorkingStatus,
        age: memberAge === '' ? undefined : Number(memberAge),
      })
      setMemberName('')
      setMemberColor('#3b82f6')
      setMemberRelationship('')
      setMemberWorkingStatus('')
      setMemberAge('')
      setShowMemberForm(false)
      setMembersRetryCount((c) => c + 1)
    } catch (err: any) {
      setMemberFormError(classifyErrorMessage(err))
    } finally {
      setMemberSubmitting(false)
    }
  }

  const startEditMember = (member: FamilyMember) => {
    setEditingMember(member)
    setEditMemberName(member.name)
    setEditMemberColor(member.color)
    // Phase 16+ — pre-fill household-profile fields so the Edit
    // modal lands with the current values ready to revise. NULL/
    // undefined on the BE side maps to the empty-string UI sentinel
    // so the <select> shows the "Not set" placeholder ("") rather
    // than a stale selected option from a previous edit.
    setEditMemberRelationship(member.relationship ?? '')
    setEditMemberWorkingStatus(member.working_status ?? '')
    setEditMemberAge(
      member.age == null ? '' : String(member.age),
    )
    setEditMemberError(null)
  }

  const cancelEditMember = () => {
    if (editMemberSubmitting) return
    setEditingMember(null)
  }

  const submitEditMember = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingMember) return
    setEditMemberSubmitting(true)
    setEditMemberError(null)
    try {
      await rulesService.updateFamilyMember(editingMember.id, {
        name: editMemberName.trim(),
        color: editMemberColor,
        // Phase 16+ — ship only what the user touched. ``undefined``
        // keys are silently dropped server-side by Pydantic
        // ``model_dump()`` (whitelist contract): an unset age
        // doesn't accidentally clear the stored age.
        relationship:
          editMemberRelationship === ''
            ? undefined
            : editMemberRelationship,
        working_status:
          editMemberWorkingStatus === ''
            ? undefined
            : editMemberWorkingStatus,
        age:
          editMemberAge === '' ? undefined : Number(editMemberAge),
      })
      setEditingMember(null)
      setMembersRetryCount((c) => c + 1)
    } catch (err: any) {
      setEditMemberError(classifyErrorMessage(err))
    } finally {
      setEditMemberSubmitting(false)
    }
  }

  const startDeleteMember = (member: FamilyMember) => {
    setConfirmingMemberDelete(member)
    setMemberDeleteError(null)
  }

  const cancelDeleteMember = () => {
    if (memberDeleteSubmitting) return
    setConfirmingMemberDelete(null)
  }

  const submitDeleteMember = async () => {
    if (!confirmingMemberDelete) return
    setMemberDeleteSubmitting(true)
    setMemberDeleteError(null)
    try {
      await rulesService.deleteFamilyMember(confirmingMemberDelete.id)
      setConfirmingMemberDelete(null)
      setMembersRetryCount((c) => c + 1)
      // Notify every page to refresh — downstream renderers
      // (Accounts page cards) re-render to remove the chip badge.
      fireDataRefresh()
    } catch (err: any) {
      setMemberDeleteError(classifyErrorMessage(err))
    } finally {
      setMemberDeleteSubmitting(false)
    }
  }

  // Phase 24 — Merchant Rules card handlers ----------------------------

  // Phase 25 — Add new category handler. The BE's POST /api/categories/
  // returns 201 + the new Category row; we append to local state AND
  // increment ``categoriesRetryCount`` so the useEffect-driven fetch
  // runs again (defence-in-depth — the optimistic append alone is
  // enough, but a refresh keeps the categories list in lockstep with
  // the canonical store if a future Phase adds server-side
  // validation that mutates the row on create).
  const handleAddCategory = async (e: React.FormEvent) => {
    e.preventDefault()
    setAddCategorySubmitting(true)
    setAddCategoryError(null)
    try {
      const newCat = await rulesService.createCategory({
        name: newCategoryName.trim(),
      })
      setNewCategoryName('')
      setShowCategoryForm(false)
      // Append optimistically so the user sees the new option in the
      // rule dropdown immediately.
      setCategories((prev) =>
        prev.find((c) => c.id === newCat.id) ? prev : [...prev, newCat],
      )
      // Burst the data-refresh bus so the Activity page's Promote-to-
      // Rule popover (which renders a category list from the parent
      // activity page's fetchCategories effect) sees the new option
      // on its next data-refresh tick.
      fireDataRefresh()
      setCategoriesRetryCount((c) => c + 1)
    } catch (err: any) {
      setAddCategoryError(classifyErrorMessage(err))
    } finally {
      setAddCategorySubmitting(false)
    }
  }

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault()
    setRuleSubmitting(true)
    setRuleFormError(null)
    try {
      const catId = Number(newRuleCategory)
      if (!Number.isInteger(catId) || catId <= 0) {
        throw new Error('Pick a category.')
      }
      // Confirm category actually exists — guards against a stale
      // category dropdown if the user revisits an old session and
      // a category was deleted out from under them.
      const target = categories.find((c) => c.id === catId)
      if (!target) {
        throw new Error('That category no longer exists.')
      }
      await rulesService.createMerchantRule({
        category_id: catId,
        keyword: newRuleKeyword.trim(),
      })
      setNewRuleCategory('')
      setNewRuleKeyword('')
      setShowRuleForm(false)
      setRulesRetryCount((c) => c + 1)
      // Phase 31 — auto-categorize immediately after creating a
      // rule so any existing transactions matching the new keyword
      // get tagged automatically. Surface the result in the
      // importExportBanner so the user sees the impact inline.
      try {
        const autoResult = await rulesService.autoCategorizeAll()
        if (autoResult.total > 0) {
          setImportExportBanner({
            variant: 'success',
            title: 'Rule created + auto-categorized:',
            message:
              `Tagged ${autoResult.categorized} of ${autoResult.total} ` +
              `transactions (${autoResult.skipped} already tagged).`,
          })
        }
      } catch {
        // Best-effort — the rule was created; auto-categorize is
        // a convenience post-step. The user can run it manually
        // from the Activity page.
      }
      // Burst the data-refresh bus so the Activity page re-fetches
      // any near-realtime tag projections (the categorizer's next
      // bulk run picks up the new rule).
      fireDataRefresh()
    } catch (err: any) {
      const friendly =
        err && typeof err === 'object' && 'response' in err
          ? classifyErrorMessage(err)
          : err instanceof Error
            ? err.message
            : 'Failed to create rule.'
      setRuleFormError(friendly)
    } finally {
      setRuleSubmitting(false)
    }
  }

  const startDeleteRule = (rule: MerchantRule) => {
    setConfirmingRuleDelete(rule)
    setRuleDeleteError(null)
  }

  const cancelDeleteRule = () => {
    if (ruleDeleteSubmitting) return
    setConfirmingRuleDelete(null)
  }

  const submitDeleteRule = async () => {
    if (!confirmingRuleDelete) return
    setRuleDeleteSubmitting(true)
    setRuleDeleteError(null)
    try {
      await rulesService.deleteMerchantRule(confirmingRuleDelete.id)
      setConfirmingRuleDelete(null)
      setRulesRetryCount((c) => c + 1)
    } catch (err: any) {
      setRuleDeleteError(classifyErrorMessage(err))
    } finally {
      setRuleDeleteSubmitting(false)
    }
  }

  // Phase 26 -- Edit merchant rule (mirrors startEditMember /
  // submitEditMember in the Family Members card above). Pre-fills
  // the modal from the current row state, guards priority coercion
  // (the BE accepts ``Optional[int]`` but a NaN input would silently
  // 400 -- we surface the bad input inline rather than submit).
  const startEditRule = (rule: MerchantRule) => {
    setEditingRule(rule)
    setEditRuleCategoryId(String(rule.category_id))
    setEditRuleKeyword(rule.keyword)
    setEditRulePriority(String(rule.priority))
    setEditRuleError(null)
  }

  const cancelEditRule = () => {
    if (editRuleSubmitting) return
    setEditingRule(null)
  }

  const submitEditRule = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingRule) return
    setEditRuleSubmitting(true)
    setEditRuleError(null)
    try {
      const catId = Number(editRuleCategoryId)
      if (!Number.isInteger(catId) || catId <= 0) {
        throw new Error('Pick a category.')
      }
      const target = categories.find((c) => c.id === catId)
      if (!target) {
        throw new Error('That category no longer exists.')
      }
      const parsedPriority = Number(editRulePriority)
      if (
        editRulePriority !== '' &&
        (!Number.isInteger(parsedPriority) || parsedPriority < 1 || parsedPriority > 999)
      ) {
        throw new Error('Priority must be a whole number between 1 and 999.')
      }
      const trimmedKeyword = editRuleKeyword.trim()
      if (!trimmedKeyword) {
        throw new Error('Keyword cannot be empty.')
      }
      await rulesService.updateMerchantRule(editingRule.id, {
        category_id: catId,
        keyword: trimmedKeyword,
        priority: parsedPriority,
      })
      setEditingRule(null)
      setRulesRetryCount((c) => c + 1)
      // Burst the data-refresh bus so the Activity page's auto-categorize
      // picks up the revised rule on its next batch.
      fireDataRefresh()
    } catch (err: any) {
      const friendly =
        err && typeof err === 'object' && 'response' in err
          ? classifyErrorMessage(err)
          : err instanceof Error
            ? err.message
            : 'Failed to save rule.'
      setEditRuleError(friendly)
    } finally {
      setEditRuleSubmitting(false)
    }
  }

  // Phase 26 -- Restore an archived rule (PUT is_archived=false).
  // Single-click action with no confirmation modal: archiving is the
  // destructive path (rule stops matching categorizer scans), so
  // restoring needs no fat-finger gate. Per-row in-flight state via
  // ``restoreRuleId`` so multiple Restore buttons can co-exist on the
  // list (mirrors the Family Members self-row disabled pattern).
  const handleRestoreRule = async (rule: MerchantRule) => {
    setRestoreRuleId(rule.id)
    setRestoreRuleError(null)
    try {
      await rulesService.updateMerchantRule(rule.id, { is_archived: false })
      setRulesRetryCount((c) => c + 1)
      fireDataRefresh()
    } catch (err: any) {
      setRestoreRuleError(classifyErrorMessage(err))
    } finally {
      setRestoreRuleId(null)
    }
  }

  // Phase 32 — cycle through tri-state archived filter.
  const handleToggleArchived = () => {
    setArchivedFilter((prev) =>
      prev === 'active' ? 'archived' : prev === 'archived' ? 'all' : 'active',
    )
  }

  // Phase 27 + 32 — Export current view as a CSV blob. Always exports
  // with archived rules included (the archivedFilter is for display
  // only; Export is a data-dump operation).
  const handleExportRules = async () => {
    setExporting(true)
    setImportExportBanner(null)
    try {
      const { blob, filename } = await rulesService.exportMerchantRules(
        true,
      )
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      // Append \u2014 appending is required for Firefox; for Chrome
      // / Safari a.click() works without, but Firefox silently
      // no-ops on detached anchors.
      document.body.appendChild(a)
      a.click()
      // Defer revoke so the browser has time to register the
      // download. 0 ms is enough; the GC would clean up later
      // but revoking earlier frees memory under a bulk export.
      setTimeout(() => {
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
      }, 0)
      setImportExportBanner({
        variant: 'success',
        title: 'Export complete:',
        message: `Downloaded ${filename} (${blob.size} bytes).`,
      })
    } catch (err: any) {
      setImportExportBanner({
        variant: 'danger',
        title: "Couldn't export:",
        message: classifyErrorMessage(err),
      })
    } finally {
      setExporting(false)
    }
  }

  // Phase 29 — Run the dedup wizard. Called by the modal's
  // "Run scan" / "Re-run with LLM" button. The modal lives in the
  // parent's JSX so the in-flight state can read from
  // ``dedupeLoading``; this handler updates ``dedupeResult`` and
  // ``dedupeBanner`` so the modal re-renders with the new groups.
  // The acceptedCandidates list is NOT cleared on a re-run so the
  // user can keep their picks across an L2 escalation.
  const handleRunDedupe = async () => {
    setDedupeLoading(true)
    setDedupeBanner(null)
    setDedupeApplyResult(null)
    try {
      const result = await rulesService.findDuplicateMerchantRules({
        includeLlm,
      })
      setDedupeResult(result)
      const totalCount = result.groups.reduce(
        (acc, g) => acc + g.candidates.length,
        0,
      )
      if (totalCount === 0) {
        // Phase 29 — honest partial-success branches. The FE trusts
        // the BE's ``l2_status`` field rather than cross-checking
        // it against ``includeLlm``: the L1-only endpoint always
        // returns ``l2_status='skipped'`` and the L1+L2 endpoint
        // returns ``'ok' | 'offline' | 'malformed'``, so the field
        // is the single source of truth. Branching on the response
        // (not on local state) keeps the wizard's banner honest
        // even if a future code path bypasses the checkbox.
        if (result.l2_status === 'offline') {
          setDedupeBanner({
            variant: 'warning',
            title: 'AI-assisted check was skipped:',
            message:
              "Your rules are clean according to the substring scan, but the AI-assisted check couldn't run (the local AI helper is offline). The substring scan alone returned zero pairs — start the local AI helper and re-run, or scan again with 'Also check semantically' turned off to confirm.",
          })
        } else if (result.l2_status === 'malformed') {
          setDedupeBanner({
            variant: 'warning',
            title: 'AI-assisted check returned a malformed response:',
            message:
              "Your rules are clean according to the substring scan, but the AI-assisted check returned something we couldn't parse. The substring scan alone returned zero pairs — try re-running in a moment, or scan again with 'Also check semantically' turned off to confirm.",
          })
        } else {
          setDedupeBanner({
            variant: 'success',
            title: 'No duplicates found:',
            message: result.l2_status === 'skipped'
              ? 'Your rules are clean. The substring check returned zero pairs. Toggle "Also check semantically" to run the AI-assisted pass.'
              : 'Your rules are clean. The substring check and the AI-assisted check both returned zero pairs.',
          })
        }
      } else {
        const l2Part =
          includeLlm && result.l2_count > 0
            ? ` (${result.l2_count} found by the AI-assisted check)`
            : ''
        setDedupeBanner({
          variant: 'warning',
          title: `${totalCount} duplicate pair${totalCount === 1 ? '' : 's'} found${l2Part}:`,
          message:
            'Tick the candidates you want to merge into the canonical, then click Apply. The canonical is never deleted.',
        })
      }
    } catch (err: any) {
      setDedupeBanner({
        variant: 'danger',
        title: "Couldn't scan for duplicates:",
        message: classifyErrorMessage(err),
      })
    } finally {
      setDedupeLoading(false)
    }
  }

  // Phase 29 — Apply the user's accepted candidates. Sends the
  // acceptedCandidate ids to the BE's soft-delete endpoint; the BE
  // archives (is_archived=True) each, idempotently. A successful
  // Apply triggers a refetch of the rules list and the data-refresh
  // bus so the categorizer picks up the change on its next batch.
  const handleApplyDedupe = async () => {
    if (!dedupeResult || acceptedCandidates.length === 0) return
    setDedupeApplying(true)
    setDedupeBanner(null)
    try {
      const result = await rulesService.applyDuplicateMerchantRules(
        acceptedCandidates,
      )
      setDedupeApplyResult(result)
      setDedupeBanner({
        variant: 'success',
        title: 'Merge complete:',
        message:
          `Archived ${result.archived} rule${result.archived === 1 ? '' : 's'}` +
          (result.skipped > 0
            ? ` (${result.skipped} already archived or missing).`
            : '.'),
      })
      // Phase 32 — remove applied candidates from the local
      // dedupeResult groups so the user can continue checking
      // and applying without closing the wizard. The UI stays
      // open with the remaining candidates.
      if (dedupeResult) {
        const appliedIds = new Set(acceptedCandidates)
        const updatedGroups = dedupeResult.groups
          .map((g) => ({
            ...g,
            candidates: g.candidates.filter((c) => !appliedIds.has(c.id)),
          }))
          .filter((g) => g.candidates.length > 0)
        setDedupeResult({
          ...dedupeResult,
          groups: updatedGroups,
        })
      }
      setAcceptedCandidates([])
      setRulesRetryCount((c) => c + 1)
      fireDataRefresh()
    } catch (err: any) {
      setDedupeBanner({
        variant: 'danger',
        title: "Couldn't merge:",
        message: classifyErrorMessage(err),
      })
    } finally {
      setDedupeApplying(false)
    }
  }

  // Phase 29 + 32 — Close the dedupe wizard. Clears the result +
  // banner + accepted-candidate list + apply-result so a re-open
  // starts fresh. ``includeLlm`` is NOT reset — it's a session-level
  // preference.
  const closeDedupeWizard = () => {
    if (dedupeLoading || dedupeApplying) return
    setShowDedupeWizard(false)
    setDedupeResult(null)
    setDedupeBanner(null)
    setDedupeApplyResult(null)
    setAcceptedCandidates([])
  }

  // Phase 27 — Import a CSV picked from the hidden <input>. Sends
  // the file as multipart via the ``importMerchantRules`` helper,
  // then renders a structured summary so the user can read
  // "Imported N — K already existed — M had errors" without
  // bouncing anywhere.
  const handleImportRulesFile = async (file: File) => {
    setImporting(true)
    setImportExportBanner(null)
    try {
      const result = await rulesService.importMerchantRules(file)
      const parts: string[] = []
      parts.push(`Imported ${result.inserted} rule${result.inserted === 1 ? '' : 's'}.`)
      if (result.skipped_existing > 0) {
        parts.push(
          `Skipped ${result.skipped_existing} that already existed (your current state was preserved).`,
        )
      }
      if (result.errors.length > 0) {
        const sample = result.errors
          .slice(0, 3)
          .map((e) => `row ${e.row}: ${e.reason}`)
          .join('; ')
        const more = result.errors.length > 3 ? ` (+${result.errors.length - 3} more)` : ''
        parts.push(`${result.errors.length} row${result.errors.length === 1 ? '' : 's'} skipped: ${sample}${more}.`)
      }
      const variant: 'success' | 'warning' =
        result.errors.length === 0 ? 'success' : 'warning'
      setImportExportBanner({
        variant,
        title:
          variant === 'success'
            ? 'Import complete:'
            : 'Import finished with errors:',
        message: parts.join(' '),
      })
      setRulesRetryCount((c) => c + 1)
      fireDataRefresh()
    } catch (err: any) {
      setImportExportBanner({
        variant: 'danger',
        title: "Couldn't import:",
        message: classifyErrorMessage(err),
      })
    } finally {
      setImporting(false)
    }
  }

  return (
    <PageLayout>
      <PageHeader
        eyebrow="System"
        title="Settings"
        description="Appearance, profile, currency, household preferences, and safe data maintenance controls."
        className="mb-6"
      />

      <AppearanceSection />
      <ReadinessSection />

      {error && (
        // variant="warning" (amber) — the profile-load failure is
        // recoverable via Retry; not a destructive action-fail.
        // Matches Overview / Goals / Portfolio / Activity / Accounts.
        <ErrorBanner
          title="Couldn't load settings:"
          message={error}
          variant="warning"
          onRetry={() => setRetryCount((c) => c + 1)}
        />
      )}

      <form
        onSubmit={handleSave}
        className="card p-6 max-w-2xl"
        data-testid="settings-form"
      >
        <h2 className="headline-md text-primary mb-4">Profile</h2>

        {loading ? (
          <p className="text-sm text-secondary">Loading profile…</p>
        ) : (
          <div className="space-y-4">
            <Input
              label="Full name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />
            <Input
              label="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <Select
              label="Currency"
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              options={CURRENCY_OPTIONS}
            />

            {saveMessage && (
              <p className="text-sm text-success-600" role="status">
                {saveMessage}
              </p>
            )}
            {saveError && (
              <p className="text-sm text-danger" role="alert">
                {saveError}
              </p>
            )}

            <div className="pt-2">
              <Button type="submit" variant="primary" disabled={saving}>
                {saving ? 'Saving…' : 'Save changes'}
              </Button>
            </div>
          </div>
        )}
      </form>

      <div className="mt-8 card p-6 max-w-2xl">
        <h2 className="headline-md text-primary mb-2">Account info</h2>
        <dl className="text-sm text-secondary space-y-1">
          <div className="flex justify-between">
            <dt>User ID</dt>
            <dd className="font-mono">{profile?.id ?? '—'}</dd>
          </div>
          <div className="flex justify-between">
            <dt>Backend</dt>
            <dd className="font-mono">
              {process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000'}
            </dd>
          </div>
        </dl>
      </div>

      {/* Data maintenance — reconcile balances */}
      <div className="mt-8 card p-6 max-w-2xl">
        <h2 className="headline-md text-primary mb-2">Data Maintenance</h2>
        <p className="text-sm text-secondary mb-4">
          Recalculate all account balances from their transaction history.
          Use this if balances ever look out of sync after imports or
          deletions.
        </p>

        {reconcileMessage && (
          <p className="text-sm text-success-600 mb-3" role="status">
            {reconcileMessage}
          </p>
        )}
        {reconcileError && (
          <p className="text-sm text-danger mb-3" role="alert">
            {reconcileError}
          </p>
        )}

        <Button
          variant="secondary"
          onClick={handleReconcile}
          disabled={reconciling}
        >
          {reconciling ? 'Reconciling…' : 'Reconcile Balances'}
        </Button>
      </div>

      {/* Danger zone — delete all data */}
      <div className="mt-8 card p-6 max-w-2xl border-[var(--danger-200)]">
        <h2 className="headline-md text-[var(--danger-600)] mb-2">Danger Zone</h2>
        <p className="text-sm text-secondary mb-4">
          Permanently delete all your financial data: transactions, import
          batches, accounts, and goals. Your profile and settings are
          preserved. This action cannot be undone.
        </p>

        {deleteMessage && (
          <p className="text-sm text-success-600 mb-3" role="status">
            {deleteMessage}
          </p>
        )}
        {deleteError && (
          <p className="text-sm text-danger mb-3" role="alert">
            {deleteError}
          </p>
        )}

        <Button
          variant="danger"
          onClick={() => setShowDeleteModal(true)}
          disabled={deleting}
        >
          {deleting ? 'Deleting…' : 'Delete All Data'}
        </Button>
      </div>

      {/* Confirmation modal */}
      <Modal
        open={showDeleteModal}
        onClose={() => setShowDeleteModal(false)}
        title="Delete All Data?"
        size="sm"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setShowDeleteModal(false)}
              disabled={deleting}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={handleDeleteAllData}
              disabled={deleting}
            >
              {deleting ? 'Deleting…' : 'Yes, delete everything'}
            </Button>
          </>
        }
      >
        <p className="text-sm text-secondary">
          This will permanently remove all transactions, import batches,
          accounts, and goals. Your profile, categories, and institution
          names will be kept.
        </p>
        <p className="text-sm text-[var(--danger-600)] font-medium mt-3">
          This cannot be undone.
        </p>
      </Modal>

      {/* Phase 16 — Family Members card. Mirrors the layout of the
        Profile card above: a single ``card p-6 max-w-2xl`` block
        with a heading + list + add form. Members are grouped so
        Self runs at the top (the BE list sorts by
        ``is_self DESC, created_at ASC``). The chip color mirrors
        the BE ``color`` column. The Self member has a "(Self)"
        suffix badge; it cannot be archived via the
        ``startDeleteMember -> submitDeleteMember`` path because
        the BE raises 400 (the UI surfaces the BE detail in the
        ``memberDeleteError`` slot). */}
      <div className="mt-8 card p-6 max-w-2xl" data-testid="family-members-card">
        <h2 className="headline-md text-primary mb-2">Family Members</h2>
        <p className="text-sm text-secondary mb-4">
          Group your accounts by household member. Every user has a
          <strong> Self</strong> member (created automatically) that
          every account defaults to. Add members for spouses, kids, or
          anyone whose finances you track alongside your own.
        </p>

        {membersError && (
          <ErrorBanner
            title="Couldn't load family members:"
            message={membersError}
            variant="warning"
            onRetry={() => setMembersRetryCount((c) => c + 1)}
          />
        )}

        {membersLoading ? (
          <p className="text-sm text-secondary" data-testid="family-members-loading">
            Loading members…
          </p>
        ) : familyMembers.length === 0 ? (
          <div
            className="text-sm text-secondary p-4 border border-dashed rounded-lg"
            data-testid="family-members-empty"
          >
            No family members yet. Click <strong>Add member</strong> to
            create your first one (besides the Self row, which is created
            automatically on first visit).
          </div>
        ) : (
          <ul className="space-y-2 mb-4" data-testid="family-members-list">
            {familyMembers.map((member) => (
              <li
                key={member.id}
                className="flex items-center gap-3 p-3 rounded-lg border border-[var(--slate-200)]"
                data-testid={`family-member-row-${member.id}`}
              >
                <span
                  aria-hidden="true"
                  className="inline-block w-3 h-3 rounded-full flex-shrink-0"
                  style={{ backgroundColor: member.color }}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-primary">
                    {member.name}
                    {member.is_self && (
                      <span
                        className="ml-2 text-[10px] font-bold uppercase tracking-wider
                                   text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded"
                        data-testid={`family-member-self-badge-${member.id}`}
                      >
                        Self
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-secondary font-mono">
                    {member.color}
                  </div>
                  {/* Phase 16+ — household profile sub-line. Renders
                      each filled field as a pipe-separated chip; if
                      every field is unset, falls back to a single
                      em-dash so the row height stays consistent
                      across members (no jagged list). The Self row
                      always has ``relationship=='Self'`` (locked on
                      the BE), so the Self's sub-line is never empty. */}
                  <div
                    className="text-xs text-secondary mt-0.5"
                    data-testid={`family-member-profile-${member.id}`}
                  >
                    {[
                      member.relationship,
                      member.working_status,
                      member.age != null ? `${member.age} yrs` : null,
                    ]
                      .filter(Boolean)
                      .join(' • ') || '—'}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => startEditMember(member)}
                  aria-label={`Edit ${member.name}`}
                  className="text-xs text-secondary hover:text-primary
                             px-2 py-1 rounded transition-colors duration-150"
                >
                  Edit
                </button>
                <button
                  type="button"
                  onClick={() => startDeleteMember(member)}
                  aria-label={`Archive ${member.name}`}
                  disabled={member.is_self}
                  title={
                    member.is_self
                      ? 'The Self member cannot be archived.'
                      : 'Archive this family member.'
                  }
                  data-testid={`family-member-archive-${member.id}`}
                  className="text-xs text-secondary hover:text-[var(--danger-600)]
                             disabled:opacity-40 disabled:cursor-not-allowed
                             px-2 py-1 rounded transition-colors duration-150"
                >
                  Archive
                </button>
              </li>
            ))}
          </ul>
        )}

        <Button
          variant="secondary"
          onClick={() => setShowMemberForm((s) => !s)}
          data-testid="add-family-member"
        >
          {showMemberForm ? 'Cancel' : 'Add member'}
        </Button>

        {showMemberForm && (
          <form
            onSubmit={handleCreateMember}
            className="mt-4 space-y-3"
            data-testid="create-family-member-form"
          >
            <Input
              label="Name"
              value={memberName}
              onChange={(e) => setMemberName(e.target.value)}
              required
              placeholder="e.g. Spouse"
            />
            <div>
              <label
                htmlFor="member-color"
                className="text-xs text-secondary uppercase tracking-wider block mb-2"
              >
                Color
              </label>
              <div className="flex items-center gap-3">
                <input
                  id="member-color"
                  type="color"
                  value={memberColor}
                  onChange={(e) => setMemberColor(e.target.value)}
                  required
                  className="h-10 w-14 rounded border border-[var(--slate-300)] cursor-pointer"
                />
                <span className="text-xs font-mono text-secondary">
                  {memberColor}
                </span>
              </div>
              <p className="text-xs text-secondary mt-2">
                Pick a distinct color so each member is easy to identify on
                the Accounts page.
              </p>
            </div>
            {/* Phase 16+ — household profile trio. All three are
                OPTIONAL on POST so the user can land a row fast
                (name + color) and revise the rest via edit. A
                submit with EMPTY strings maps to ``undefined`` on
                the wire and is silently dropped server-side, so
                the column stays NULL until the user touches the
                field. */}
            <Select
              label="Relationship"
              value={memberRelationship === '' ? '' : String(memberRelationship)}
              onChange={(e) =>
                setMemberRelationship(
                  e.target.value === ''
                    ? ''
                    : (e.target.value as Relationship),
                )
              }
              options={[
                { value: '', label: '— Not set —' },
                ...RELATIONSHIP_OPTIONS.filter((o) => o.value !== 'Self').map(
                  (o) => ({ value: o.value, label: o.label }),
                ),
              ]}
              data-testid="create-member-relationship"
            />
            <Select
              label="Working status"
              value={memberWorkingStatus === '' ? '' : String(memberWorkingStatus)}
              onChange={(e) =>
                setMemberWorkingStatus(
                  e.target.value === ''
                    ? ''
                    : (e.target.value as WorkingStatus),
                )
              }
              options={[
                { value: '', label: '— Not set —' },
                ...WORKING_STATUS_OPTIONS.map((o) => ({
                  value: o.value,
                  label: o.label,
                })),
              ]}
              data-testid="create-member-working-status"
            />
            <Input
              label="Age"
              type="number"
              min={0}
              max={120}
              step={1}
              value={memberAge}
              onChange={(e) => setMemberAge(e.target.value)}
              placeholder="e.g. 35"
              data-testid="create-member-age"
            />
            {memberFormError && (
              <p className="text-sm text-danger" role="alert">
                {memberFormError}
              </p>
            )}
            <div className="flex gap-2">
              <Button
                type="submit"
                variant="primary"
                disabled={memberSubmitting}
              >
                {memberSubmitting ? 'Creating…' : 'Create member'}
              </Button>
              <Button
                type="button"
                variant="tertiary"
                onClick={() => setShowMemberForm(false)}
              >
                Cancel
              </Button>
            </div>
          </form>
        )}
      </div>

      {/* Edit modal — same shape as the Goal-editor pattern in the
        dashboard's GoalManager card. Submit lives in the footer via
        a native <button form="..."> because the Button primitive
        does not pass the HTML5 ``form`` attribute through. */}
      <Modal
        open={editingMember !== null}
        onClose={cancelEditMember}
        title={
          editingMember
            ? `Edit ${editingMember.name}`
            : 'Edit family member'
        }
        size="sm"
        footer={
          <>
            <Button
              variant="tertiary"
              onClick={cancelEditMember}
              disabled={editMemberSubmitting}
            >
              Cancel
            </Button>
            <button
              type="submit"
              form="edit-family-member-form"
              disabled={editMemberSubmitting}
              className="inline-flex items-center justify-center gap-2
                         px-4 py-2 rounded-lg font-medium
                         bg-[var(--primary-500)] text-[var(--text-on-brand)]
                         hover:bg-[var(--primary-600)] active:bg-[var(--primary-700)]
                         disabled:bg-[var(--slate-400)]
                         transition-all duration-150
                         disabled:cursor-not-allowed"
            >
              {editMemberSubmitting ? 'Saving…' : 'Save changes'}
            </button>
          </>
        }
      >
        <form
          id="edit-family-member-form"
          onSubmit={submitEditMember}
          className="space-y-3"
          data-testid="edit-family-member-form"
        >
          <Input
            label="Name"
            value={editMemberName}
            onChange={(e) => setEditMemberName(e.target.value)}
            required
          />
          <div>
            <label
              htmlFor="edit-member-color"
              className="text-xs text-secondary uppercase tracking-wider block mb-2"
            >
              Color
            </label>
            <input
              id="edit-member-color"
              type="color"
              value={editMemberColor}
              onChange={(e) => setEditMemberColor(e.target.value)}
              className="h-10 w-14 rounded border border-[var(--slate-300)] cursor-pointer"
            />
          </div>
          {/* Phase 16+ — household profile trio on the Edit modal.
              ``editMemberRelationship`` is DISABLED while editing
              the Self row: the BE locks ``relationship=='Self'``
              for Self rows regardless of input, so showing an
              enabled dropdown would mislead the user into
              thinking they're editing a value when the BE will
              silently override. The BE lock + the FE disable are
              in lockstep so the user NEVER sees an auto-reverted
              change. */}
          <Select
            label="Relationship"
            value={editMemberRelationship === '' ? '' : String(editMemberRelationship)}
            onChange={(e) =>
              setEditMemberRelationship(
                e.target.value === ''
                  ? ''
                  : (e.target.value as Relationship),
              )
            }
            options={[
              { value: '', label: '— Not set —' },
              ...RELATIONSHIP_OPTIONS.map((o) => ({
                value: o.value,
                label: o.label,
              })),
            ]}
            disabled={editingMember?.is_self === true}
            data-testid="edit-member-relationship"
          />
          <Select
            label="Working status"
            value={editMemberWorkingStatus === '' ? '' : String(editMemberWorkingStatus)}
            onChange={(e) =>
              setEditMemberWorkingStatus(
                e.target.value === ''
                  ? ''
                  : (e.target.value as WorkingStatus),
              )
            }
            options={[
              { value: '', label: '— Not set —' },
              ...WORKING_STATUS_OPTIONS.map((o) => ({
                value: o.value,
                label: o.label,
              })),
            ]}
            data-testid="edit-member-working-status"
          />
          <Input
            label="Age"
            type="number"
            min={0}
            max={120}
            step={1}
            value={editMemberAge}
            onChange={(e) => setEditMemberAge(e.target.value)}
            placeholder="e.g. 35"
            data-testid="edit-member-age"
          />
          {editMemberError && (
            <p className="text-sm text-danger" role="alert">
              {editMemberError}
            </p>
          )}
        </form>
      </Modal>

      <Modal
        open={confirmingMemberDelete !== null}
        onClose={cancelDeleteMember}
        title="Archive family member?"
        size="sm"
        footer={
          <>
            <Button
              variant="tertiary"
              onClick={cancelDeleteMember}
              disabled={memberDeleteSubmitting}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={submitDeleteMember}
              disabled={memberDeleteSubmitting || confirmingMemberDelete?.is_self}
            >
              {memberDeleteSubmitting ? 'Archiving…' : 'Archive'}
            </Button>
          </>
        }
      >
        {confirmingMemberDelete && (
          <div className="space-y-3">
            <p className="body-md text-secondary">
              This will archive{' '}
              <strong className="text-primary">
                {confirmingMemberDelete.name}
              </strong>
              . They&apos;ll stop appearing in the Accounts page member select.
              Linked accounts are NOT reassigned — archive only succeeds when
              zero active accounts reference this member.
            </p>
            {memberDeleteError && (
              <p className="text-sm text-danger" role="alert">
                {memberDeleteError}
              </p>
            )}
          </div>
        )}
      </Modal>

      <MerchantRulesCard
        rules={rules}
        categories={categories}
        loading={rulesLoading}
        error={rulesError}
        onRetry={() => setRulesRetryCount((c) => c + 1)}
        archivedFilter={archivedFilter}
        onToggleArchived={handleToggleArchived}
        showForm={showRuleForm}
        onToggleForm={() => setShowRuleForm((s) => !s)}
        form={{
          categoryId: newRuleCategory,
          setCategoryId: setNewRuleCategory,
          keyword: newRuleKeyword,
          setKeyword: setNewRuleKeyword,
        }}
        submitting={ruleSubmitting}
        formError={ruleFormError}
        onSubmit={handleCreateRule}
        onStartDelete={startDeleteRule}
        onStartEdit={startEditRule}
        onStartRestore={handleRestoreRule}
        restoreRuleId={restoreRuleId}
        restoreRuleError={restoreRuleError}
        showCategoryForm={showCategoryForm}
        onToggleCategoryForm={() => setShowCategoryForm((s) => !s)}
        newCategoryName={newCategoryName}
        setNewCategoryName={setNewCategoryName}
        addCategorySubmitting={addCategorySubmitting}
        addCategoryError={addCategoryError}
        onSubmitCategory={handleAddCategory}
        // Phase 27 — Source filter + Export + Import wiring.
        sourceFilter={sourceFilter}
        onChangeSourceFilter={setSourceFilter}
        // Phase 33 — Category filter.
        categoryFilter={categoryFilter}
        onChangeCategoryFilter={setCategoryFilter}
        exporting={exporting}
        importExportBanner={importExportBanner}
        onExport={handleExportRules}
        onImportFilePicked={handleImportRulesFile}
        importing={importing}
        onOpenDedupeWizard={() => setShowDedupeWizard(true)}
      />

      <Modal
        open={confirmingRuleDelete !== null}
        onClose={cancelDeleteRule}
        title="Delete merchant rule?"
        size="sm"
        footer={
          <>
            <Button
              variant="tertiary"
              onClick={cancelDeleteRule}
              disabled={ruleDeleteSubmitting}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={submitDeleteRule}
              disabled={ruleDeleteSubmitting}
            >
              {ruleDeleteSubmitting ? 'Deleting…' : 'Delete'}
            </Button>
          </>
        }
      >
        {confirmingRuleDelete && (
          <div className="space-y-3">
            <p className="body-md text-secondary">
              This will soft-delete the rule{' '}
              <strong className="text-primary font-mono">
                {confirmingRuleDelete.keyword}
              </strong>{' '}
              from category{' '}
              <strong className="text-primary">
                {confirmingRuleDelete.category_name ?? '—'}
              </strong>
              . Future categorizations will no longer match it.
            </p>
            <p className="text-sm text-tertiary">
              You can restore it later from the archived filter
              toggle (set it to &quot;Archived only&quot; or &quot;All rules&quot;).
              The boot-time seed helper will not re-insert
              this keyword on the next BE restart.
            </p>
            {ruleDeleteError && (
              <p className="text-sm text-danger" role="alert">
                {ruleDeleteError}
              </p>
            )}
          </div>
        )}
      </Modal>

      <Modal
        open={editingRule !== null}
        onClose={cancelEditRule}
        title={
          editingRule
            ? `Edit rule: ${editingRule.keyword}`
            : 'Edit merchant rule'
        }
        size="sm"
        footer={
          <>
            <Button
              variant="tertiary"
              onClick={cancelEditRule}
              disabled={editRuleSubmitting}
            >
              Cancel
            </Button>
            <button
              type="submit"
              form="edit-merchant-rule-form"
              disabled={editRuleSubmitting}
              className="inline-flex items-center justify-center gap-2
                         px-4 py-2 rounded-lg font-medium
                         bg-[var(--primary-500)] text-[var(--text-on-brand)]
                         hover:bg-[var(--primary-600)] active:bg-[var(--primary-700)]
                         disabled:bg-[var(--slate-400)]
                         transition-all duration-150
                         disabled:cursor-not-allowed"
            >
              {editRuleSubmitting ? 'Saving…' : 'Save changes'}
            </button>
          </>
        }
      >
        <form
          id="edit-merchant-rule-form"
          onSubmit={submitEditRule}
          className="space-y-3"
          data-testid="edit-merchant-rule-form"
        >
          <Select
            label="Category"
            value={editRuleCategoryId}
            onChange={(e) => setEditRuleCategoryId(e.target.value)}
            options={[
              { value: '', label: '— Pick a category —' },
              ...categories.map((c) => ({
                value: String(c.id),
                label: c.name,
              })),
            ]}
            data-testid="edit-rule-category"
          />
          <Input
            label="Keyword"
            value={editRuleKeyword}
            onChange={(e) => setEditRuleKeyword(e.target.value)}
            required
            placeholder="e.g. FID BPG SVC"
            data-testid="edit-rule-keyword"
          />
          <p className="text-xs text-tertiary -mt-1">
            Stored upper-cased server-side. Matched as a case-insensitive substring.
          </p>
          <Input
            label="Priority"
            type="number"
            min={1}
            max={999}
            step={1}
            value={editRulePriority}
            onChange={(e) => setEditRulePriority(e.target.value)}
            placeholder="e.g. 100"
            data-testid="edit-rule-priority"
          />
          <p className="text-xs text-tertiary -mt-1">
            Lower priority numbers are scanned first within each category.
          </p>
          {editRuleError && (
            <p className="text-sm text-danger" role="alert">
              {editRuleError}
            </p>
          )}
        </form>
      </Modal>

      {/* Phase 29 — Clean up duplicates wizard modal. Two-step flow:
          (a) Run scan (L1 by default, opt-in L2) — the modal body
          shows progress and the dedup result; the user reviews the
          candidates and ticks the ones they want to merge.
          (b) Apply — soft-deletes the accepted candidates. The
          canonical is NEVER sent to Apply (only candidates). The
          modal renders an error banner for L2 failures (Ollama
          offline, malformed upstream body, etc.) and a success
          banner showing the archived count. The footer has
          Run scan / Apply / Close so the user can iterate
          (re-run with L2 on, re-apply, etc.) without leaving the
          modal. */}
      <Modal
        open={showDedupeWizard}
        onClose={closeDedupeWizard}
        title="Clean up duplicate rules"
        size="lg"
        footer={
          <>
            <Button
              variant="tertiary"
              onClick={closeDedupeWizard}
              disabled={dedupeLoading || dedupeApplying}
            >
              Close
            </Button>
            {dedupeApplyResult ? (
              <>
                <span className="text-sm text-success-600 mr-auto">
                  Archived {dedupeApplyResult.archived} rule
                  {dedupeApplyResult.archived === 1 ? '' : 's'}.
                </span>
                <Button
                  variant="secondary"
                  onClick={handleRunDedupe}
                  disabled={dedupeLoading}
                  data-testid="dedupe-run"
                >
                  {dedupeLoading
                    ? 'Scanning…'
                    : 'Re-run scan'}
                </Button>
                <Button
                  variant="primary"
                  onClick={handleApplyDedupe}
                  disabled={
                    dedupeLoading ||
                    dedupeApplying ||
                    acceptedCandidates.length === 0
                  }
                  data-testid="dedupe-apply"
                >
                  {dedupeApplying
                    ? 'Applying…'
                    : acceptedCandidates.length === 0
                      ? 'Apply (none selected)'
                      : `Apply selected (${acceptedCandidates.length})`}
                </Button>
              </>
            ) : (
              <>
                <Button
                  variant="secondary"
                  onClick={handleRunDedupe}
                  disabled={dedupeLoading}
                  data-testid="dedupe-run"
                >
                  {dedupeLoading
                    ? 'Scanning…'
                    : dedupeResult
                      ? 'Re-run scan'
                      : includeLlm
                        ? 'Run scan (L1 + L2)'
                        : 'Run scan (L1)'}
                </Button>
                <Button
                  variant="primary"
                  onClick={handleApplyDedupe}
                  disabled={
                    dedupeLoading ||
                    dedupeApplying ||
                    acceptedCandidates.length === 0
                  }
                  data-testid="dedupe-apply"
                >
                  {dedupeApplying
                    ? 'Applying…'
                    : acceptedCandidates.length === 0
                      ? 'Apply (none selected)'
                      : `Apply selected (${acceptedCandidates.length})`}
                </Button>
              </>
            )}
          </>
        }
      >
        <div className="space-y-4" data-testid="dedupe-wizard-body">
          <p className="text-sm text-secondary">
            Find merchant rules that point to the same merchant text and
            merge them. The <strong>canonical</strong> is the shorter, more
            general rule (it absorbs every transaction the longer one
            would have caught); it is <strong>never</strong> deleted.
          </p>

          {/* L2 opt-in — disabled while a scan is in flight so the
              user can't toggle mid-call. The label echoes the BE's
              contract: L2 needs Ollama running on the BE host. */}
          <label className="flex items-center gap-2 text-sm text-secondary">
            <input
              type="checkbox"
              checked={includeLlm}
              onChange={(e) => setIncludeLlm(e.target.checked)}
              disabled={dedupeLoading}
              data-testid="dedupe-include-llm"
              className="h-4 w-4 rounded border-outline"
            />
            <span>
              Also check semantically (slower — uses a local AI
              helper — but catches pairs like <code>WAL-MART</code>{' '}
              vs <code>WALMART</code> that substring alone misses).
            </span>
          </label>

          {dedupeBanner && (
            <ErrorBanner
              title={dedupeBanner.title}
              message={dedupeBanner.message}
              variant={dedupeBanner.variant}
            />
          )}

          {dedupeLoading && !dedupeResult && (
            <div
              className="text-sm text-secondary p-4 border border-dashed rounded-lg"
              data-testid="dedupe-loading"
            >
              Scanning your rules for duplicates…
            </div>
          )}

          {dedupeResult && dedupeResult.groups.length > 0 && (
            <ul
              className="space-y-3 max-h-96 overflow-y-auto pr-1"
              data-testid="dedupe-group-list"
            >
              {dedupeResult.groups.map((g) => (
                <li
                  key={g.canonical.id}
                  className="border border-outline-variant/40 rounded-lg p-3"
                  data-testid={`dedupe-group-${g.canonical.id}`}
                >
                  <div className="text-xs text-tertiary uppercase tracking-wider mb-1">
                    Keep (canonical)
                  </div>
                  <div className="font-mono text-sm text-primary mb-2">
                    {g.canonical.keyword}
                  </div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-tertiary uppercase tracking-wider">
                      Archive (candidates)
                    </span>
                    {/* Phase 32 — Select all checkbox for the group.
                        Toggling it adds/removes all candidate IDs
                        from ``acceptedCandidates`` at once. */}
                    <label className="flex items-center gap-1.5 text-[11px] text-secondary cursor-pointer">
                      <input
                        type="checkbox"
                        checked={
                          g.candidates.length > 0 &&
                          g.candidates.every((c) =>
                            acceptedCandidates.includes(c.id),
                          )
                        }
                        ref={(el) => {
                          // Indeterminate state: some but not all checked.
                          if (el) {
                            const someChecked = g.candidates.some((c) =>
                              acceptedCandidates.includes(c.id),
                            )
                            const allChecked = g.candidates.every((c) =>
                              acceptedCandidates.includes(c.id),
                            )
                            el.indeterminate = someChecked && !allChecked
                          }
                        }}
                        disabled={dedupeApplying}
                        onChange={(e) => {
                          const ids = g.candidates.map((c) => c.id)
                          setAcceptedCandidates((prev) =>
                            e.target.checked
                              ? [...new Set([...prev, ...ids])]
                              : prev.filter((x) => !ids.includes(x)),
                          )
                        }}
                        data-testid={`dedupe-select-all-${g.canonical.id}`}
                        className="h-3.5 w-3.5 rounded border-outline"
                      />
                      Select all
                    </label>
                  </div>
                  <ul className="space-y-1.5">
                    {g.candidates.map((c) => {
                      const checked = acceptedCandidates.includes(c.id)
                      return (
                        <li
                          key={c.id}
                          className="flex items-start gap-2 text-sm"
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={dedupeApplying}
                            onChange={(e) => {
                              setAcceptedCandidates((prev) =>
                                e.target.checked
                                  ? [...prev, c.id]
                                  : prev.filter((x) => x !== c.id),
                              )
                            }}
                            data-testid={`dedupe-candidate-${c.id}`}
                            className="h-4 w-4 mt-0.5 rounded border-outline"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-mono text-primary">
                                {c.keyword}
                              </span>
                              <span
                                className="inline-flex items-center px-2 py-0.5
                                           rounded-full text-[10px] font-bold
                                           uppercase tracking-wider text-white"
                                style={{
                                  backgroundColor:
                                    c.method === 'substring'
                                      ? '#64748b'
                                      : '#f97316',
                                }}
                                title={
                                  c.method === 'substring'
                                    ? 'Found by the deterministic substring scan (L1).'
                                    : 'Found by the LLM semantic pass (L2).'
                                }
                              >
                                {c.method === 'substring' ? 'L1' : 'L2'}
                              </span>
                              <span className="text-xs text-tertiary">
                                {Math.round(c.confidence * 100)}%
                              </span>
                            </div>
                            {c.rationale && (
                              <p className="text-xs text-secondary mt-0.5">
                                {c.rationale}
                              </p>
                            )}
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                </li>
              ))}
            </ul>
          )}

          {dedupeResult && dedupeResult.groups.length === 0 && !dedupeLoading && (
            <div
              className="text-sm text-secondary p-4 border border-dashed rounded-lg"
              data-testid="dedupe-no-results"
            >
              No duplicate groups detected. Your rules are clean.
            </div>
          )}

          {dedupeApplyResult && (
            <div
              className="text-sm p-3 border border-[var(--success-200)] bg-[var(--success-50)] rounded-lg"
              data-testid="dedupe-apply-result"
            >
              <strong>Done.</strong> Archived {dedupeApplyResult.archived}{' '}
              rule{dedupeApplyResult.archived === 1 ? '' : 's'}
              {dedupeApplyResult.skipped > 0 &&
                ` (${dedupeApplyResult.skipped} already archived or missing).`}
            </div>
          )}
        </div>
      </Modal>
    </PageLayout>
  )
}
