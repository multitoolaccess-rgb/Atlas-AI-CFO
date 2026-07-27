'use client'

import { useEffect, useState } from 'react'
import {
  Upload,
  Loader2,
  FileText,
  FileSpreadsheet,
  Receipt,
  CheckCircle2,
  Eye,
  RefreshCw,
  Trash2,
  X,
  HelpCircle,
} from 'lucide-react'
import { Button, Select, ErrorBanner } from '@/components/ui'
import { useNotifications } from '@/components/providers/NotificationContext'
import {
  rulesService,
  type Account,
  type ImportBatch,
  type ImportResult,
  type Transaction,
} from '@/lib/api'

// =================================================================
// Phase 7 next.js port — replaces the legacy Vite
// `frontend/src/components/Onboarding/ImportStatementUpload.tsx`.
// Differences from the legacy:
//   • no `apiUrl` prop (uses the singleton `rulesService` -> axios baseURL)
//   • accounts injected as a prop (parent `/accounts` already has them)
//   • auth token + 401-retry already handled by `rulesService`'s
//     response interceptor; we only render user-facing error text.
//   • client-side size + extension guards mirror the server's
//     `_validate_upload_shape` (`services/rules-service/app/routes/imports.py`)
//     so we never POST a request the server will reject.
//   • renders Lucide-react icons instead of plain labels.
//   • available in 2 paths:
//       • cover `/accounts` (`Statement` tab)
//       • any future page (e.g. `/imports`) with a different account list
// =================================================================

interface ImportStatementUploadProps {
  accounts: Account[]
  onImportComplete?: () => void
}

const ACCEPTED_EXTENSIONS = ['.csv', '.pdf', '.ofx', '.qfx', '.xlsx', '.xls'] as const
const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(',')

// Mirror services/rules-service/app/routes/imports.py:MAX_TEXT_BYTES / MAX_PDF_BYTES.
const MAX_TEXT_BYTES = 10 * 1024 * 1024  // 10MB — CSV + OFX/QFX
const MAX_PDF_BYTES = 50 * 1024 * 1024   // 50MB — PDF

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function fileIcon(filename: string) {
  const ext = filename.toLowerCase().split('.').pop()
  if (ext === 'csv' || ext === 'xlsx' || ext === 'xls') return FileSpreadsheet
  if (ext === 'pdf') return FileText
  return Receipt // ofx, qfx
}

function validateFile(f: File): string | null {
  const name = f.name.toLowerCase()
  const ext = ACCEPTED_EXTENSIONS.find((e) => name.endsWith(e))
  if (!ext) {
    return `Unsupported file type. Accepted: ${ACCEPTED_EXTENSIONS.join(', ')}.`
  }
  const cap = ext === '.pdf' ? MAX_PDF_BYTES : MAX_TEXT_BYTES
  // Excel files (.xlsx/.xls) are binary but treated under the text-file
  // size cap (10MB) — sufficient for even large bank statements.
  if (f.size > cap) {
    return `File too large: ${formatBytes(f.size)} exceeds the ${formatBytes(cap)} limit for ${ext.slice(1).toUpperCase()}.`
  }
  return null
}

// Account type options for the type-selection prompt when auto-detect fails.
// Mirrors services/rules-service/app/account_types.py ACCOUNT_TYPES.
const ACCOUNT_TYPE_OPTIONS = [
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
] as const

export default function ImportStatementUpload({
  accounts,
  onImportComplete,
}: ImportStatementUploadProps) {
  const [file, setFile] = useState<File | null>(null)
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
  // When true, the user chose "Auto-detect from statement" — the backend
  // will auto-create accounts from multi-account PDFs (Fidelity Investment
  // Reports) or fall back to the first active / "Imported Statements" account.
  const [autoDetectAccount, setAutoDetectAccount] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const [preview, setPreview] = useState<ImportResult | null>(null)
  const [importWarnings, setImportWarnings] = useState<string[]>([])
  // Phase 54+ — dismiss state for inline banners
  const [dismissed, setDismissed] = useState(false)

  // Phase 54+ — account type selection prompt state.
  // When the backend can't detect the account type during auto-detect,
  // we prompt the user to select one before finalizing the import.
  const [typePromptVisible, setTypePromptVisible] = useState(false)
  const [typePromptAccountId, setTypePromptAccountId] = useState<number | null>(null)
  const [typePromptValue, setTypePromptValue] = useState('checking')
  const [typePromptSubmitting, setTypePromptSubmitting] = useState(false)
  const [pendingImportResult, setPendingImportResult] = useState<ImportResult | null>(null)

  const { addNotification } = useNotifications()

  // Import history
  const [batches, setBatches] = useState<ImportBatch[]>([])
  const [loadingBatches, setLoadingBatches] = useState(false)
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null)
  const [batchTransactions, setBatchTransactions] = useState<Transaction[] | null>(null)
  const [loadingBatchTxns, setLoadingBatchTxns] = useState(false)

  // Two-step delete UX — ``confirmDeleteId`` is set when the user
  // clicks "Delete" on a row; the row renders an inline Confirm +
  // Cancel pair instead of the normal View/Delete buttons. The
  // explicit state (vs a window.confirm()) keeps destructive
  // interactions on the same visual rhythm as the rest of the
  // history table — no jarring native modal mid-scroll, no
  // console-blocking dialog for headless tests.
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const [deletingBatchId, setDeletingBatchId] = useState<number | null>(null)

  // Keep the selected account in sync with the parent's account list (e.g.
  // user adds a new account in the Accounts tab, then switches here).
  // When auto-detect is selected, don't override it with the first account.
  useEffect(() => {
    if (autoDetectAccount) return
    if (selectedAccountId === null && accounts.length > 0) {
      setSelectedAccountId(accounts[0].id)
    }
    if (
      selectedAccountId !== null &&
      !accounts.some((a) => a.id === selectedAccountId) &&
      accounts.length > 0
    ) {
      setSelectedAccountId(accounts[0].id)
    }
  }, [accounts, selectedAccountId])

  // Load import history on mount.
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoadingBatches(true)
      try {
        const list = await rulesService.listBatches()
        if (!cancelled) setBatches(list)
      } catch (err: any) {
        if (!cancelled) {
          setError(
            err?.response?.data?.detail ??
              err?.message ??
              'Failed to load import history.',
          )
        }
      } finally {
        if (!cancelled) setLoadingBatches(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  const onFileChange = (next: File | null) => {
    setError(null)
    setStatus(null)
    setPreview(null)
    setImportWarnings([])
    setDismissed(false)
    setTypePromptVisible(false)
    setPendingImportResult(null)
    if (!next) {
      setFile(null)
      return
    }
    const validationError = validateFile(next)
    if (validationError) {
      setError(validationError)
      setFile(null)
      return
    }
    setFile(next)
  }

  const onReloadBatches = async () => {
    setLoadingBatches(true)
    // Reset any in-flight inline confirm — the row the user was
    // confirming might not survive the reload (a parallel delete
    // from another browser tab, or a manual rm in the DB). Carrying
    // the confirm state across a reload would let the user click
    // "Confirm" on a stale ``Delete N transactions?`` count where
    // N is the pre-reload number but the row is the post-reload row.
    setConfirmDeleteId(null)
    try {
      const list = await rulesService.listBatches()
      setBatches(list)
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ??
          err?.message ??
          'Failed to reload import history.',
      )
    } finally {
      setLoadingBatches(false)
    }
  }

  const onSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError(null)
    setStatus(null)
    setPreview(null)
    setImportWarnings([])
    if (!file) {
      setError('Please choose a file to upload.')
      return
    }
    setUploading(true)
    try {
      const result = await rulesService.uploadStatement(
        file,
        autoDetectAccount ? undefined : (selectedAccountId ?? undefined),
      )

      // Phase 54+ — account type detection prompt.
      // If the backend couldn't detect the account type during auto-detect
      // (suggested_account_type is null) and the import created a new account,
      // prompt the user to select the correct type before finalizing.
      if (
        autoDetectAccount &&
        !result.suggested_account_type &&
        result.account_id &&
        result.saved_transactions > 0
      ) {
        setPendingImportResult(result)
        setTypePromptAccountId(result.account_id)
        setTypePromptValue('checking')
        setTypePromptVisible(true)
        setUploading(false)
        return
      }
      // Finalize the import result. This handles the three-tier status
      // messaging, auto-categorize sub-line, and warnings.
      finalizeImportResult(result)
      // Refresh history and notify the parent so it can re-fetch the dashboard.
      const list = await rulesService.listBatches()
      setBatches(list)
      onImportComplete?.()
    } catch (err: any) {
      setImportWarnings([])
      setError(
        err?.response?.data?.detail ?? err?.message ?? 'Upload failed.',
      )
    } finally {
      setUploading(false)
    }
  }

  const onSelectBatch = async (batchId: number) => {
    setSelectedBatchId(batchId)
    setBatchTransactions(null)
    setLoadingBatchTxns(true)
    try {
      const txns = await rulesService.listBatchTransactions(batchId)
      setBatchTransactions(txns)
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ??
          err?.message ??
          'Failed to load batch transactions.',
      )
    } finally {
      setLoadingBatchTxns(false)
    }
  }

  const onConfirmDeleteBatch = async (batchId: number) => {
    setDeletingBatchId(batchId)
    setConfirmDeleteId(null)
    try {
      await rulesService.deleteBatch(batchId)
      // If the user had the deleted batch's transactions panel open,
      // collapse it — otherwise it would render an empty section
      // that hits the 404 on its next fetch.
      if (selectedBatchId === batchId) {
        setSelectedBatchId(null)
        setBatchTransactions(null)
      }
      setBatches((prev) => prev.filter((b) => b.id !== batchId))
      setStatus(`Deleted import batch #${batchId}.`)
      // Refresh the parent dashboard's aggregates (``import_batches_count``,
      // ``last_import_at``) — a delete changes those numbers the same
      // way an upload does, so we re-use the same upstream callback
      // contract rather than introducing a second one.
      onImportComplete?.()
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ??
          err?.message ??
          'Failed to delete import batch.',
      )
    } finally {
      setDeletingBatchId(null)
    }
  }

  // Phase 54+ — handle account type prompt submission.
  // Updates the account type and finalizes the import result.
  const handleTypePromptSubmit = async () => {
    if (!typePromptAccountId || !pendingImportResult) return
    setTypePromptSubmitting(true)
    try {
      await rulesService.updateAccount(typePromptAccountId, {
        account_type: typePromptValue,
      })
      // Push a notification to the bell icon
      addNotification({
        title: 'Account type updated',
        message: `Account set to ${ACCOUNT_TYPE_OPTIONS.find((o) => o.value === typePromptValue)?.label ?? typePromptValue}.`,
        variant: 'success',
      })
    } catch (err: any) {
      addNotification({
        title: 'Could not update account type',
        message: err?.response?.data?.detail ?? err?.message ?? 'Unknown error',
        variant: 'warning',
      })
    } finally {
      // Always finalize + refresh regardless of whether the type
      // update succeeded — the import data was already saved by the
      // backend before the prompt was shown.
      finalizeImportResult(pendingImportResult)
      const list = await rulesService.listBatches()
      setBatches(list)
      onImportComplete?.()
      setTypePromptSubmitting(false)
      setTypePromptVisible(false)
      setPendingImportResult(null)
    }
  }

  const handleTypePromptSkip = async () => {
    if (pendingImportResult) {
      finalizeImportResult(pendingImportResult)
      // Refresh import history and notify parent so they pick up the new data.
      const list = await rulesService.listBatches()
      setBatches(list)
      onImportComplete?.()
    }
    setTypePromptVisible(false)
    setPendingImportResult(null)
  }

  // Extracted finalization logic so it can be called from both the
  // normal upload path and the type-prompt path.
  const finalizeImportResult = (result: ImportResult) => {
    const saved = result.saved_transactions
    const detected = result.record_count
    const expected = result.expected_row_count
    const warnings = result.warnings ?? []
    if (saved > 0) {
      const multiAccts = result.multi_account_ids ?? null
      const multiCount = multiAccts ? multiAccts.length : 0
      const targetStr = multiCount > 1
        ? `${multiCount} accounts`
        : accountLabel(result.account_id)
      let msg = `Imported ${saved} transaction${saved === 1 ? '' : 's'} from ${result.filename} into ${targetStr}.`
      if (
        result.auto_categorize_total != null &&
        result.auto_categorize_total > 0
      ) {
        const tagged = result.auto_categorized ?? 0
        const total = result.auto_categorize_total
        const noMatch = result.auto_categorize_no_match ?? total - tagged
        msg += ` Auto-tagged ${tagged} of ${total}.`
        if (noMatch > 0) msg += ` ${noMatch} need a manual pick.`
      }
      if (expected != null && expected > saved) {
        const dropped = expected - saved
        msg += ` ⚠️ ${dropped} row${dropped === 1 ? '' : 's'} dropped (see warnings below).`
      }
      setStatus(msg)
      setDismissed(false)
      if (warnings.length > 0) {
        setError(null)
        setImportWarnings(warnings)
        // Push warnings to the notification bell
        addNotification({
          title: 'Import warnings',
          message: `${warnings.length} warning${warnings.length === 1 ? '' : 's'} for ${result.filename}`,
          variant: 'warning',
        })
      } else {
        setImportWarnings([])
      }
      // Push success notification to bell (only when no warnings;
      // warnings already have their own notification above)
      if (warnings.length === 0) {
        addNotification({
          title: 'Import complete',
          message: `Imported ${saved} transaction${saved === 1 ? '' : 's'} from ${result.filename}.`,
          variant: 'success',
        })
      }
    } else if (detected > 0) {
      setStatus(
        `Preview recorded for ${result.filename} into ${accountLabel(result.account_id)} — ${detected} text line${
          detected === 1 ? '' : 's'
        } extracted, but no structured transactions were saved (PDF/OCR is preview-only today). For line-item imports, upload a CSV or OFX/QFX text export from Fidelity if your plan provides one.`,
      )
      setDismissed(false)
    } else {
      const ft = (result.file_type ?? '').toLowerCase()
      const zeroRecordMessage: Record<string, string> = {
        csv: `Couldn't import any rows from ${result.filename}. The CSV needs columns for the transaction Date, Description, and Amount.`,
        xlsx: `Couldn't import any rows from ${result.filename}. The Excel file needs columns for the transaction Date, Description, and Amount.`,
        pdf: `Couldn't extract any text from ${result.filename} — the PDF may be image-only. Try uploading a CSV or OFX/QFX text export.`,
        ofx: `Couldn't parse any transactions from ${result.filename}. The OFX/QFX file may be malformed — try exporting again as CSV.`,
        qfx: `Couldn't parse any transactions from ${result.filename}. The OFX/QFX file may be malformed — try exporting again as CSV.`,
      }
      setError(
        zeroRecordMessage[ft] ?? `Couldn't extract any text from ${result.filename}. The file may be malformed.`,
      )
      addNotification({
        title: 'Import failed',
        message: `No transactions imported from ${result.filename}.`,
        variant: 'danger',
      })
      setFile(null)
      return
    }
    setPreview(result)
    setFile(null)
  }

  // Helper: look up the human-readable account label from the accounts
  // list by id. Falls back to "#{id}" if the account was deleted or
  // the list hasn't loaded yet.
  const accountLabel = (id: number | null | undefined): string => {
    if (id == null) return '—'
    const acct = accounts.find((a) => a.id === id)
    return acct ? `${acct.account_name} · ${acct.account_type}` : `Account #${id}`
  }

  return (
    <div className="space-y-6">
      {/* Upload */}
      <form
        onSubmit={onSubmit}
        className="card p-6 space-y-4"
        data-testid="import-form"
        aria-label="Upload statement"
      >
        <div>
          <h2 className="headline-md text-primary mb-1">Upload statement</h2>
          <p className="body-sm text-secondary">
            CSV and Excel (.xlsx/.xls) files are persisted as transactions.
            PDF/OFX/QFX return a preview alongside the batch record (OFX/QFX
            is a free Plaid alternative; PDFs with no text layer fall back to
            OCR server-side).
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label
              htmlFor="import-file"
              className="label-md text-secondary"
            >
              Statement file{' '}
              <span className="text-tertiary">
                (.csv, .pdf, .ofx, .qfx, .xlsx, .xls · up to 50MB)
              </span>
            </label>
            <input
              id="import-file"
              type="file"
              accept={ACCEPT_ATTR}
              onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
              className="
                block w-full text-sm
                file:mr-3 file:py-2 file:px-4
                file:rounded-[var(--radius-md)] file:border-0
                file:bg-[var(--primary-500)] file:text-[var(--text-on-brand)]
                file:font-[var(--label-md-weight)]
                hover:file:bg-[var(--primary-600)]
                cursor-pointer
                text-[var(--text-secondary)]
              "
              data-testid="import-file-input"
            />
            {file && (
              <div className="flex items-center gap-2 mt-2 label-sm text-tertiary">
                {(() => {
                  const Icon = fileIcon(file.name)
                  return <Icon className="w-4 h-4" aria-hidden="true" />
                })()}
                <span className="truncate max-w-[16rem]" title={file.name}>
                  {file.name}
                </span>
                <span>·</span>
                <span>{formatBytes(file.size)}</span>
                <button
                  type="button"
                  onClick={() => onFileChange(null)}
                  aria-label="Clear file"
                  className="
                    ml-auto text-[var(--text-tertiary)]
                    hover:text-[var(--text-primary)]
                    focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--primary-500)]
                    rounded-[var(--radius-sm)]
                  "
                >
                  <Trash2 className="w-4 h-4" aria-hidden="true" />
                </button>
              </div>
            )}
          </div>

          <Select
            label="Target account"
            value={
              autoDetectAccount
                ? '__auto__'
                : selectedAccountId === null
                  ? ''
                  : String(selectedAccountId)
            }
            onChange={(e) => {
              const val = e.target.value
              if (val === '__auto__') {
                setAutoDetectAccount(true)
                setSelectedAccountId(null)
              } else if (val === '') {
                setAutoDetectAccount(false)
                setSelectedAccountId(null)
              } else {
                setAutoDetectAccount(false)
                setSelectedAccountId(Number(val))
              }
            }}
            options={[
              {
                value: '__auto__',
                label: 'Auto-detect from statement (create accounts as needed)',
              },
              ...accounts.map((a) => ({
                value: String(a.id),
                label: `${a.account_name} · ${a.account_type}`,
              })),
            ]}
            disabled={false}
          />
        </div>

        {error && (
          <ErrorBanner
            title="Upload error:"
            message={error}
            onDismiss={() => setError(null)}
          />
        )}

        {status && !dismissed && (
          <div
            className="
              flex items-start gap-3
              p-3 rounded-[var(--radius-md)]
              bg-[var(--success-50)] text-[var(--success-700)]
              border border-[var(--success-200)]
            "
            role="status"
          >
            <CheckCircle2
              className="w-5 h-5 mt-0.5 flex-shrink-0"
              aria-hidden="true"
            />
            <p className="text-sm flex-1">{status}</p>
            <button
              type="button"
              onClick={() => setDismissed(true)}
              aria-label="Dismiss"
              className="p-1 rounded-[var(--radius-sm)] text-current opacity-60 hover:opacity-100 transition-opacity"
              data-testid="import-status-dismiss"
            >
              <X className="w-4 h-4" aria-hidden="true" />
            </button>
          </div>
        )}

        {importWarnings.length > 0 && (
          <div
            className="
              flex items-start gap-3
              p-3 rounded-[var(--radius-md)]
              bg-[var(--warning-50)] text-[var(--warning-700)]
              border border-[var(--warning-200)]
            "
            role="alert"
          >
            <span className="text-lg flex-shrink-0" aria-hidden="true">⚠️</span>
            <div className="text-sm flex-1">
              <p className="font-semibold mb-1">Import warnings:</p>
              <ul className="list-disc pl-4 space-y-0.5">
                {importWarnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
            <button
              type="button"
              onClick={() => setImportWarnings([])}
              aria-label="Dismiss warnings"
              className="p-1 rounded-[var(--radius-sm)] text-current opacity-60 hover:opacity-100 transition-opacity"
              data-testid="import-warnings-dismiss"
            >
              <X className="w-4 h-4" aria-hidden="true" />
            </button>
          </div>
        )}

        {/* Phase 54+ — account type selection prompt. Shown when
            auto-detect couldn't determine the account type. */}
        {typePromptVisible && (
          <div
            className="
              p-4 rounded-[var(--radius-md)]
              bg-[var(--primary-50)] text-[var(--primary-700)]
              border border-[var(--primary-200)]
            "
            role="alert"
            data-testid="import-type-prompt"
          >
            <div className="flex items-start gap-3">
              <HelpCircle className="w-5 h-5 mt-0.5 shrink-0" aria-hidden="true" />
              <div className="flex-1">
                <p className="font-semibold text-sm mb-1">
                  What type of account is this?
                </p>
                <p className="text-xs opacity-80 mb-3">
                  We couldn't auto-detect the account type from the statement.
                  Please select the correct type so transactions are categorized correctly.
                </p>
                <div className="flex items-end gap-3 flex-wrap">
                  <Select
                    label="Account type"
                    value={typePromptValue}
                    onChange={(e) => setTypePromptValue(e.target.value)}
                    options={ACCOUNT_TYPE_OPTIONS.map((o) => ({
                      value: o.value,
                      label: o.label,
                    }))}
                  />
                  <div className="flex items-center gap-2 pb-0.5">
                    <Button
                      type="button"
                      variant="primary"
                      size="sm"
                      onClick={handleTypePromptSubmit}
                      disabled={typePromptSubmitting}
                      data-testid="import-type-prompt-confirm"
                    >
                      {typePromptSubmitting ? 'Updating…' : 'Confirm type'}
                    </Button>
                    <button
                      type="button"
                      onClick={handleTypePromptSkip}
                      className="label-sm text-tertiary hover:text-primary underline-offset-2 hover:underline"
                      data-testid="import-type-prompt-skip"
                    >
                      Skip (keep as Checking)
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <Button
            type="submit"
            variant="primary"
            disabled={uploading || !file}
            data-testid="import-submit"
            icon={
              uploading ? (
                <Loader2
                  className="w-4 h-4 animate-spin"
                  aria-hidden="true"
                />
              ) : (
                <Upload className="w-4 h-4" aria-hidden="true" />
              )
            }
          >
            {uploading ? 'Uploading…' : 'Upload statement'}
          </Button>
        </div>
      </form>

      {/* Last-import preview (CSV rows or PDF/OFX lines) */}
      {preview && <PreviewSection preview={preview} accountLabel={accountLabel} />}

      {/* History */}
      <HistorySection
        batches={batches}
        loading={loadingBatches}
        selectedBatchId={selectedBatchId}
        confirmDeleteId={confirmDeleteId}
        deletingBatchId={deletingBatchId}
        accountLabel={accountLabel}
        onSelectBatch={onSelectBatch}
        onReload={onReloadBatches}
        onAskDelete={(id) => setConfirmDeleteId(id)}
        onCancelDelete={() => setConfirmDeleteId(null)}
        onConfirmDelete={onConfirmDeleteBatch}
      />

      {/* Selected batch transactions */}
      {selectedBatchId !== null && (
        <>
          <TransactionsSection
            batchId={selectedBatchId}
            transactions={batchTransactions}
            loading={loadingBatchTxns}
          />
          <BatchPreviewSection
            batchId={selectedBatchId}
            batches={batches}
          />
        </>
      )}
    </div>
  )
}

// -----------------------------------------------------------------
// Sub-sections
// -----------------------------------------------------------------

function PreviewSection({
  preview,
  accountLabel,
}: {
  preview: ImportResult
  accountLabel: (id: number | null | undefined) => string
}) {
  return (
    <section
      className="card p-6 space-y-4"
      data-testid="import-preview"
      aria-label="Import preview"
    >
      <div>
        <h3 className="headline-md text-primary mb-1">Import preview</h3>
        <p className="body-sm text-secondary">
          {preview.file_type === 'csv' || preview.file_type === 'xlsx'
            ? `First 5 rows the server detected in the ${preview.file_type.toUpperCase()} file.`
            : `First lines previewed from the ${preview.file_type.toUpperCase()} file.`}
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Batch id" value={`#${preview.batch_id}`} />
        <Stat
          label="Target account"
          value={
            preview.multi_account_ids && preview.multi_account_ids.length > 1
              ? `${preview.multi_account_ids.length} accounts`
              : accountLabel(preview.account_id)
          }
        />
        <Stat
          label="Transactions saved"
          value={`${preview.saved_transactions} txn${
            preview.saved_transactions === 1 ? '' : 's'
          }`}
        />
        <Stat
          label="Records detected"
          value={`${preview.record_count} record${
            preview.record_count === 1 ? '' : 's'
          }`}
        />
      </div>

      {preview.file_type === 'csv' || preview.file_type === 'xlsx' ? (
        <CsvPreviewTable rows={preview.preview} />
      ) : (
        <TextPreviewList lines={preview.preview} />
      )}
    </section>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="card p-3 bg-[var(--bg-tertiary)]">
      <div className="label-sm text-tertiary uppercase tracking-wider">
        {label}
      </div>
      <div className="text-base font-semibold text-primary mt-1">{value}</div>
    </div>
  )
}

function CsvPreviewTable({ rows }: { rows: any[] }) {
  if (!rows || rows.length === 0) {
    return (
      <p className="text-sm text-tertiary">No preview rows returned.</p>
    )
  }
  const headers = Object.keys(rows[0])
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid="import-preview-table">
        <thead>
          <tr className="border-b border-[var(--border-color)]">
            {headers.map((h) => (
              <th
                key={h}
                className="text-left py-2 pr-4 label-sm uppercase text-tertiary"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className="border-b border-[var(--border-subtle)] hover:bg-[var(--bg-tertiary)]"
            >
              {headers.map((h) => (
                <td
                  key={h}
                  className="py-2 pr-4 text-primary whitespace-nowrap"
                >
                  {String(row?.[h] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TextPreviewList({ lines }: { lines: string[] }) {
  if (!lines || lines.length === 0) {
    return (
      <p className="text-sm text-tertiary">
        No text could be extracted (image-only PDF? Server should have
        attempted OCR fallback for the PDF case).
      </p>
    )
  }
  return (
    <ol className="list-decimal pl-6 space-y-1 max-h-96 overflow-y-auto">
      {lines.map((line, i) => (
        <li key={i} className="text-sm text-secondary font-mono">
          {line}
        </li>
      ))}
    </ol>
  )
}

interface HistorySectionProps {
  batches: ImportBatch[]
  loading: boolean
  selectedBatchId: number | null
  confirmDeleteId: number | null
  deletingBatchId: number | null
  accountLabel: (id: number | null | undefined) => string
  onSelectBatch: (id: number) => void
  onReload: () => Promise<void> | void
  onAskDelete: (id: number) => void
  onCancelDelete: () => void
  onConfirmDelete: (id: number) => Promise<void>
}

function HistorySection({
  batches,
  loading,
  selectedBatchId,
  confirmDeleteId,
  deletingBatchId,
  accountLabel,
  onSelectBatch,
  onReload,
  onAskDelete,
  onCancelDelete,
  onConfirmDelete,
}: HistorySectionProps) {
  return (
    <section
      className="card p-6 space-y-3"
      data-testid="import-history"
      aria-label="Import history"
    >
      <div className="flex items-center justify-between gap-3">
        <h3 className="headline-md text-primary">Import history</h3>
        <Button
          variant="tertiary"
          size="sm"
          onClick={onReload}
          icon={<RefreshCw className="w-4 h-4" aria-hidden="true" />}
        >
          Refresh
        </Button>
      </div>

      {loading ? (
        <p className="text-sm text-secondary">Loading import history…</p>
      ) : batches.length === 0 ? (
        <p className="text-sm text-tertiary">
          No imports yet. Upload a CSV/PDF/OFX/QFX file above to start tracking.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table
            className="w-full text-sm"
            data-testid="import-history-table"
          >
            <thead>
              <tr className="border-b border-[var(--border-color)]">
                <th className="text-left py-2 pr-4 label-sm uppercase text-tertiary">
                  File
                </th>
                <th className="text-left py-2 pr-4 label-sm uppercase text-tertiary">
                  Type
                </th>
                <th className="text-left py-2 pr-4 label-sm uppercase text-tertiary">
                  Account
                </th>
                <th className="text-right py-2 pr-4 label-sm uppercase text-tertiary">
                  Saved
                </th>
                <th className="text-right py-2 pr-4 label-sm uppercase text-tertiary">
                  Records
                </th>
                <th className="text-left py-2 pr-4 label-sm uppercase text-tertiary">
                  Imported
                </th>
                <th />
              </tr>
            </thead>
            <tbody>
              {batches.map((b) => {
                const isSelected = b.id === selectedBatchId
                const when = b.created_at ?? b.processed_at
                return (
                  <tr
                    key={b.id}
                    className={`border-b border-[var(--border-subtle)] ${
                      isSelected ? 'bg-[var(--primary-50)]' : ''
                    }`}
                    data-testid={`import-history-row-${b.id}`}
                  >
                    <td className="py-2 pr-4 text-primary truncate max-w-[18rem]">
                      {b.filename}
                    </td>
                    <td className="py-2 pr-4">
                      <span className="badge-neutral label-sm">
                        {b.file_type.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-secondary">
                      {b.multi_account_ids && b.multi_account_ids.length > 1
                        ? `${b.multi_account_ids.length} accounts`
                        : accountLabel(b.account_id)}
                    </td>
                    <td className="py-2 pr-4 text-secondary text-right">
                      {b.saved_transactions}
                    </td>
                    <td className="py-2 pr-4 text-secondary text-right">
                      {b.record_count}
                    </td>
                    <td className="py-2 pr-4 text-tertiary text-xs whitespace-nowrap">
                      {when ? new Date(when).toLocaleString() : '—'}
                    </td>
                    <td className="py-2 pr-4 text-right">
                      {confirmDeleteId === b.id ? (
                        // Inline confirm — replaces the normal
                        // View/Delete button pair with Cancel +
                        // Confirm. The transactional count is repeated
                        // in the prompt so the user sees the exact
                        // blast radius before they click.
                        <div
                          className="flex items-center justify-end gap-2"
                          data-testid={`import-history-confirm-${b.id}`}
                        >
                          <span
                            className="label-sm text-[var(--danger-700)] whitespace-nowrap"
                            role="status"
                          >
                            Delete {b.saved_transactions} transaction
                            {b.saved_transactions === 1 ? '' : 's'}?
                          </span>
                          <Button
                            variant="tertiary"
                            size="sm"
                            onClick={onCancelDelete}
                          >
                            Cancel
                          </Button>
                          <Button
                            variant="danger"
                            size="sm"
                            disabled={deletingBatchId === b.id}
                            onClick={() => onConfirmDelete(b.id)}
                            icon={
                              deletingBatchId === b.id ? (
                                <Loader2
                                  className="w-4 h-4 animate-spin"
                                  aria-hidden="true"
                                />
                              ) : (
                                <Trash2
                                  className="w-4 h-4"
                                  aria-hidden="true"
                                />
                              )
                            }
                            data-testid={`import-history-confirm-delete-${b.id}`}
                          >
                            {deletingBatchId === b.id
                              ? 'Deleting…'
                              : 'Confirm'}
                          </Button>
                        </div>
                      ) : (
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            variant="tertiary"
                            size="sm"
                            onClick={() => onSelectBatch(b.id)}
                            icon={
                              <Eye
                                className="w-4 h-4"
                                aria-hidden="true"
                              />
                            }
                          >
                            View
                          </Button>
                          <Button
                            variant="tertiary"
                            size="sm"
                            onClick={() => onAskDelete(b.id)}
                            icon={
                              <Trash2
                                className="w-4 h-4 text-[var(--danger-500)]"
                                aria-hidden="true"
                              />
                            }
                            data-testid={`import-history-delete-${b.id}`}
                            ariaLabel={`Delete batch ${b.id}`}
                          >
                            Delete
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

interface TransactionsSectionProps {
  batchId: number
  transactions: Transaction[] | null
  loading: boolean
}

/**
 * Phase 11 — surface the persisted parser preview lines for the
 * selected historical batch. Reads from the in-memory ``batches``
 * list (the same one populated by ``/api/imports/batches``) so we
 * don't fire an extra GET. Picks up where the immediate
 * `preview: ImportResult.preview` ends:
 *
 * - `preview: ImportResult.preview` only exists at upload time.
 *   After a reload the user had no way to see what the parser saw.
 * - `batches[i].preview_lines` is the BE-persisted equivalent
 *   (capped at 50 lines so a 200-page PDF doesn't bloat the column).
 * - For SaaS-shape fidelity, the section renders BOTH the parsed
 *   CSV rows (when ``file_type === 'csv'|'xlsx'``) AND the raw
 *   text lines (otherwise). The Activity page uses the same
 *   fallback pattern on its post-import banner.
 */
function BatchPreviewSection({
  batchId,
  batches,
}: {
  batchId: number
  batches: ImportBatch[]
}) {
  const batch = batches.find((b) => b.id === batchId)
  const lines = batch?.preview_lines ?? []
  if (!batch || lines.length === 0) return null
  const isTabular =
    batch.file_type === 'csv' || batch.file_type === 'xlsx'
  return (
    <section
      className="card p-6 space-y-3"
      data-testid="import-batch-preview"
      aria-label={`Preview for batch ${batchId}`}
    >
      <div className="flex items-center justify-between gap-3">
        <h3 className="headline-md text-primary">
          Preview for batch #{batchId}
        </h3>
        <span className="label-sm text-tertiary">
          {lines.length} line{lines.length === 1 ? '' : 's'}
        </span>
      </div>
      <p className="label-sm text-tertiary">
        What the parser saw when this import was processed. CSV/Excel
        rows below are the structured preview; PDF/OFX/OCR lines are
        the raw text the parser matched against.
      </p>
      {isTabular ? (
        <BatchPreviewTable rows={lines as any[]} />
      ) : (
        <BatchPreviewText lines={lines as string[]} />
      )}
    </section>
  )
}

function BatchPreviewTable({ rows }: { rows: any[] }) {
  if (!Array.isArray(rows) || rows.length === 0) return null
  const headers = Object.keys(rows[0] ?? {})
  if (headers.length === 0) return null
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--border-color)]">
            {headers.map((h) => (
              <th
                key={h}
                className="text-left py-2 pr-4 label-sm uppercase text-tertiary"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className="border-b border-[var(--border-subtle)] hover:bg-[var(--bg-tertiary)]"
            >
              {headers.map((h) => (
                <td
                  key={h}
                  className="py-2 pr-4 text-primary whitespace-nowrap"
                >
                  {String(row?.[h] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BatchPreviewText({ lines }: { lines: string[] }) {
  return (
    <ol
      className="list-decimal pl-6 space-y-1 max-h-72 overflow-y-auto"
      data-testid="import-batch-preview-text"
    >
      {lines.map((line, i) => (
        <li key={i} className="text-sm text-secondary font-mono">
          {String(line)}
        </li>
      ))}
    </ol>
  )
}

function TransactionsSection({
  batchId,
  transactions,
  loading,
}: TransactionsSectionProps) {
  return (
    <section
      className="card p-6 space-y-3"
      data-testid="import-batch-transactions"
      aria-label={`Transactions for batch ${batchId}`}
    >
      <div className="flex items-center justify-between gap-3">
        <h3 className="headline-md text-primary">
          Transactions for batch #{batchId}
        </h3>
        <span className="label-sm text-tertiary">
          {transactions ? `${transactions.length} total` : ''}
        </span>
      </div>

      {loading ? (
        <p className="text-sm text-secondary">Loading transactions…</p>
      ) : transactions && transactions.length > 0 ? (
        <p className="label-sm text-tertiary" data-testid="import-batch-transactions-loaded">
          {transactions.length} structured transaction
          {transactions.length === 1 ? '' : 's'} imported from this batch.
        </p>
      ) : null}

      {loading ? null : transactions && transactions.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border-color)]">
                <th className="text-left py-2 pr-4 label-sm uppercase text-tertiary">
                  Date
                </th>
                <th className="text-left py-2 pr-4 label-sm uppercase text-tertiary">
                  Description
                </th>
                <th className="text-left py-2 pr-4 label-sm uppercase text-tertiary">
                  Merchant
                </th>
                <th className="text-right py-2 pr-4 label-sm uppercase text-tertiary">
                  Amount
                </th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((t) => (
                <tr
                  key={t.id}
                  className="border-b border-[var(--border-subtle)] hover:bg-[var(--bg-tertiary)]"
                >
                  <td className="py-2 pr-4 text-secondary whitespace-nowrap">
                    {new Date(t.transaction_date).toLocaleDateString()}
                  </td>
                  <td className="py-2 pr-4 text-primary">{t.description}</td>
                  <td className="py-2 pr-4 text-secondary">
                    {t.merchant_name ?? '—'}
                  </td>
                  <td
                    className={`py-2 pr-4 text-right font-semibold ${
                      t.amount >= 0
                        ? 'text-[var(--success-700)]'
                        : 'text-[var(--danger-700)]'
                    }`}
                  >
                    {t.amount.toLocaleString('en-US', {
                      style: 'currency',
                      currency: 'USD',
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        // Phase 11 — empty state now distinguishes "PDF/OCR preview
        // only" (where we DO have the captured text lines to show)
        // from "true zero results" (encoder failure, wrong file).
        // Without this split, the user clicked "View" on a Fidelity
        // NetBenefits import and saw a single blank line — their
        // "nothing loads" report.
        <p
          className="text-sm text-tertiary"
          data-testid="import-batch-transactions-empty"
        >
          No structured transactions were saved for this batch.
          For CSV / Excel imports this typically means the file
          didn't parse cleanly; for PDF / OFX / QFX imports this is
          expected (those formats persist as a preview envelope
          only). The Preview tab below shows what was captured.
        </p>
      )}
    </section>
  )
}
