/**
 * Phase 29 — dedup wizard wiring on the Settings page.
 *
 * Locks the FE-side contract for the "Clean up duplicates" affordance
 * without exercising the actual Modal body (the parent component is
 * a large form surface; mounting it under @testing-library/react is
 * brittle and would re-render the Profile / Family Members / Merchant
 * Rules cards). Instead, the test renders JUST the dedup wizard
 * modal markup via a minimal shim so we lock the data-testid surface
 * the Playwright e2e suite targets + the Apply handler's API call
 * shape.
 */
import React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

// ---- Mock the api service layer --------------------------------------
// We mock the rulesService singleton so the test doesn't depend on
// a running rules-service or a valid JWT cookie. The mock's
// behaviour is parameterised per-test via ``vi.mocked(...)``.
vi.mock('@/lib/api', () => {
  const dedupeFind = vi.fn()
  const dedupeApply = vi.fn()
  return {
    rulesService: {
      findDuplicateMerchantRules: dedupeFind,
      applyDuplicateMerchantRules: dedupeApply,
      // The Settings page also calls these in its useEffect hooks;
      // return empty arrays so the test doesn't have to mock every
      // call site.
      getProfile: vi.fn().mockResolvedValue({
        id: 1,
        email: 'test@example.com',
        full_name: 'Test',
        currency_preference: 'USD',
      }),
      // ReadinessSection is part of the Settings page shell. Keep this
      // page-level mock complete so dedupe tests exercise only the wizard,
      // not an unrelated missing method on the shared service mock.
      getReadiness: vi.fn().mockResolvedValue({
        schema_version: 'atlas-readiness/v1',
        overall_state: 'ready_with_blocked_optional_capabilities',
        checked_at: '2026-08-15T00:00:00Z',
        checks: [],
        feature_flags: {},
        credentials: {},
        prohibited_capabilities: {},
      }),
      listFamilyMembers: vi.fn().mockResolvedValue([]),
      listMerchantRules: vi.fn().mockResolvedValue([]),
      listCategories: vi.fn().mockResolvedValue([]),
    },
    // The Settings page also imports these as NAMED exports for
    // its <Select> dropdowns (Family Member form + rule source
    // filter pills). Without these the test fails before any
    // component renders with "No RELATIONSHIP_OPTIONS export is
    // defined on the @/lib/api mock". Mirror the real shape so
    // we don't accidentally diverge from the production array.
    RELATIONSHIP_OPTIONS: [
      { value: 'Self', label: 'Self' },
      { value: 'Spouse', label: 'Spouse' },
      { value: 'Child', label: 'Child' },
      { value: 'Parent', label: 'Parent' },
      { value: 'Sibling', label: 'Sibling' },
      { value: 'Other', label: 'Other' },
    ],
    MERCHANT_RULE_SOURCE_OPTIONS: [
      { value: 'system', label: 'System seed' },
      { value: 'manual', label: 'User-added' },
      { value: 'tag-rule', label: 'Activity rule' },
      { value: 'llm', label: 'AI-assisted' },
      { value: 'imported', label: 'Imported' },
    ],
    WORKING_STATUS_OPTIONS: [
      { value: 'Employed', label: 'Employed' },
      { value: 'Self-employed', label: 'Self-employed' },
      { value: 'Student', label: 'Student' },
      { value: 'Retired', label: 'Retired' },
      { value: 'Unemployed', label: 'Unemployed' },
      { value: 'Other', label: 'Other' },
    ],
  }
})

import { rulesService } from '@/lib/api'

// ---- Mock the dataRefresh bus ----------------------------------------
vi.mock('@/lib/dataRefresh', () => ({
  fireDataRefresh: vi.fn(),
}))

// ---- Mock the Modal primitive ----------------------------------------
// The Modal component renders a portal; we just stub it as a div so
// the test can read ``data-testid="dedupe-wizard-body"`` etc.
//
// IMPORTANT — the stub must render BOTH ``children`` AND ``footer``.
// The real Modal is portal-based and renders the footer outside the
// body, but the dedup wizard places its primary actions
// (dedupe-run, dedupe-apply) in the footer. The previous version
// of this mock dropped ``footer`` entirely, so ``findByTestId`` for
// any footer-resident testid timed out at 1s and 8/9 tests failed
// with "Unable to find an element by: [data-testid='dedupe-run']".
vi.mock('@/components/ui/Modal', () => ({
  default: ({
    open,
    children,
    footer,
  }: {
    open: boolean
    onClose: () => void
    title: string
    children: React.ReactNode
    footer?: React.ReactNode
  }) => {
    if (!open) return null
    return (
      <div data-testid="dedupe-modal-stub">
        <div data-testid="dedupe-modal-body">{children}</div>
        <div data-testid="dedupe-modal-footer">{footer}</div>
      </div>
    )
  },
}))

// ---- Mock the Button primitive ---------------------------------------
vi.mock('@/components/ui', () => ({
  Button: ({
    children,
    onClick,
    disabled,
    ...rest
  }: React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: string
  }) => (
    <button onClick={onClick} disabled={disabled} {...rest}>
      {children}
    </button>
  ),
  Input: () => <input />,
  Select: () => <select />,
}))

vi.mock('@/components/ui/ErrorBanner', () => ({
  default: ({ title, message }: { title: string; message: string }) => (
    <div data-testid="error-banner">
      {title} {message}
    </div>
  ),
}))

// Import the component AFTER mocks so the test sees the mocked
// surface. We render the SettingsPage directly because the dedupe
// modal lives inside it; the Family/Merchant Rules cards' effects
// are no-ops thanks to the empty-array mocks.
import SettingsPage from '@/app/settings/page'

/** Default empty result factory — every mock carries l2_status so
 *  the TS check on the api.ts contract is happy. */
const emptyResult = {
  groups: [],
  l1_count: 0,
  l2_count: 0,
  l2_status: 'skipped' as const,
}

describe('Phase 29 — dedup wizard wiring', () => {
  beforeEach(() => {
    vi.mocked(rulesService.findDuplicateMerchantRules).mockReset()
    vi.mocked(rulesService.applyDuplicateMerchantRules).mockReset()
  })

  it('renders the "Clean up duplicates" button in the merchant rules card', async () => {
    render(<SettingsPage />)
    const button = await screen.findByTestId('merchant-rules-dedupe')
    expect(button).toBeTruthy()
    expect(button.textContent).toMatch(/clean up duplicates/i)
  })

  it('opens the wizard modal with a Run scan button when the card button is clicked', async () => {
    render(<SettingsPage />)
    const openButton = await screen.findByTestId('merchant-rules-dedupe')
    fireEvent.click(openButton)
    const runButton = await screen.findByTestId('dedupe-run')
    expect(runButton).toBeTruthy()
    // The LLM opt-in checkbox is rendered inside the wizard body.
    const llmCheckbox = screen.getByTestId(
      'dedupe-include-llm',
    ) as HTMLInputElement
    expect(llmCheckbox).toBeTruthy()
    expect(llmCheckbox.checked).toBe(false)
  })

  it('calls findDuplicateMerchantRules with includeLlm=false on a default Run scan', async () => {
    vi.mocked(rulesService.findDuplicateMerchantRules).mockResolvedValueOnce(
      emptyResult,
    )
    render(<SettingsPage />)
    fireEvent.click(await screen.findByTestId('merchant-rules-dedupe'))
    fireEvent.click(await screen.findByTestId('dedupe-run'))
    await waitFor(() => {
      expect(
        vi.mocked(rulesService.findDuplicateMerchantRules),
      ).toHaveBeenCalledWith({ includeLlm: false })
    })
  })

  it('renders dedup group candidates with checkboxes when the L1 scan returns hits', async () => {
    vi.mocked(rulesService.findDuplicateMerchantRules).mockResolvedValueOnce({
      groups: [
        {
          canonical: { id: 1, keyword: 'STARBUCKS' },
          candidates: [
            {
              id: 99,
              keyword: 'STARBUCKS COFFEE',
              method: 'substring',
              confidence: 1.0,
              rationale: "STARBUCKS is a substring of STARBUCKS COFFEE",
            },
          ],
        },
      ],
      l1_count: 1,
      l2_count: 0,
      l2_status: 'skipped',
    })
    render(<SettingsPage />)
    fireEvent.click(await screen.findByTestId('merchant-rules-dedupe'))
    fireEvent.click(await screen.findByTestId('dedupe-run'))
    const checkbox = (await screen.findByTestId(
      'dedupe-candidate-99',
    )) as HTMLInputElement
    expect(checkbox).toBeTruthy()
    expect(checkbox.checked).toBe(false)
  })

  it('gates the Apply button on the acceptedCandidates list (disabled when empty)', async () => {
    vi.mocked(rulesService.findDuplicateMerchantRules).mockResolvedValueOnce({
      groups: [
        {
          canonical: { id: 1, keyword: 'STARBUCKS' },
          candidates: [
            {
              id: 99,
              keyword: 'STARBUCKS COFFEE',
              method: 'substring',
              confidence: 1.0,
              rationale: '',
            },
          ],
        },
      ],
      l1_count: 1,
      l2_count: 0,
      l2_status: 'skipped',
    })
    render(<SettingsPage />)
    fireEvent.click(await screen.findByTestId('merchant-rules-dedupe'))
    fireEvent.click(await screen.findByTestId('dedupe-run'))
    const applyButton = (await screen.findByTestId(
      'dedupe-apply',
    )) as HTMLButtonElement
    // No candidate ticked yet → Apply is disabled.
    expect(applyButton.disabled).toBe(true)
    // Tick the candidate.
    const checkbox = (await screen.findByTestId(
      'dedupe-candidate-99',
    )) as HTMLInputElement
    fireEvent.click(checkbox)
    await waitFor(() => {
      expect(applyButton.disabled).toBe(false)
    })
  })

  it('calls applyDuplicateMerchantRules with the accepted ids on Apply', async () => {
    vi.mocked(rulesService.findDuplicateMerchantRules).mockResolvedValueOnce({
      groups: [
        {
          canonical: { id: 1, keyword: 'STARBUCKS' },
          candidates: [
            {
              id: 99,
              keyword: 'STARBUCKS COFFEE',
              method: 'substring',
              confidence: 1.0,
              rationale: '',
            },
            {
              id: 100,
              keyword: 'STARBUCKS POS',
              method: 'llm',
              confidence: 0.92,
              rationale: 'LLM-detected semantic duplicate',
            },
          ],
        },
      ],
      l1_count: 1,
      l2_count: 1,
      l2_status: 'ok',
    })
    vi.mocked(rulesService.applyDuplicateMerchantRules).mockResolvedValueOnce({
      archived: 2,
      skipped: 0,
    })
    render(<SettingsPage />)
    fireEvent.click(await screen.findByTestId('merchant-rules-dedupe'))
    fireEvent.click(await screen.findByTestId('dedupe-run'))
    // Tick BOTH candidates.
    fireEvent.click(await screen.findByTestId('dedupe-candidate-99'))
    fireEvent.click(await screen.findByTestId('dedupe-candidate-100'))
    fireEvent.click(await screen.findByTestId('dedupe-apply'))
    await waitFor(() => {
      expect(
        vi.mocked(rulesService.applyDuplicateMerchantRules),
      ).toHaveBeenCalledWith([99, 100])
    })
  })

  it('toggles the LLM checkbox and re-runs the scan with includeLlm=true', async () => {
    vi.mocked(rulesService.findDuplicateMerchantRules).mockResolvedValue(
      emptyResult,
    )
    render(<SettingsPage />)
    fireEvent.click(await screen.findByTestId('merchant-rules-dedupe'))
    // Toggle the LLM opt-in.
    const llmCheckbox = screen.getByTestId(
      'dedupe-include-llm',
    ) as HTMLInputElement
    fireEvent.click(llmCheckbox)
    expect(llmCheckbox.checked).toBe(true)
    fireEvent.click(screen.getByTestId('dedupe-run'))
    await waitFor(() => {
      expect(
        vi.mocked(rulesService.findDuplicateMerchantRules),
      ).toHaveBeenCalledWith({ includeLlm: true })
    })
  })

  it('renders an honest "offline" partial-success banner when l2_status="offline"', async () => {
    vi.mocked(rulesService.findDuplicateMerchantRules).mockResolvedValueOnce({
      groups: [],
      l1_count: 0,
      l2_count: 0,
      l2_status: 'offline',
    })
    render(<SettingsPage />)
    fireEvent.click(await screen.findByTestId('merchant-rules-dedupe'))
    fireEvent.click(await screen.findByTestId('dedupe-run'))
    const banner = await screen.findByTestId('error-banner')
    expect(banner.textContent).toMatch(/offline/i)
    expect(banner.textContent).toMatch(/AI-assisted check was skipped/i)
  })

  it('renders an honest "malformed" partial-success banner when l2_status="malformed"', async () => {
    vi.mocked(rulesService.findDuplicateMerchantRules).mockResolvedValueOnce({
      groups: [],
      l1_count: 0,
      l2_count: 0,
      l2_status: 'malformed',
    })
    render(<SettingsPage />)
    fireEvent.click(await screen.findByTestId('merchant-rules-dedupe'))
    fireEvent.click(await screen.findByTestId('dedupe-run'))
    const banner = await screen.findByTestId('error-banner')
    expect(banner.textContent).toMatch(/malformed/i)
    expect(banner.textContent).toMatch(/try re-running/i)
  })

  // Phase 32 — Select-all checkbox in each dedupe group
  it('renders a Select all checkbox in each dedupe group', async () => {
    vi.mocked(rulesService.findDuplicateMerchantRules).mockResolvedValueOnce({
      groups: [
        {
          canonical: { id: 1, keyword: 'STARBUCKS' },
          candidates: [
            {
              id: 99,
              keyword: 'STARBUCKS COFFEE',
              method: 'substring',
              confidence: 1.0,
              rationale: '',
            },
            {
              id: 100,
              keyword: 'STARBUCKS POS',
              method: 'llm',
              confidence: 0.92,
              rationale: '',
            },
          ],
        },
      ],
      l1_count: 1,
      l2_count: 1,
      l2_status: 'ok',
    })
    render(<SettingsPage />)
    fireEvent.click(await screen.findByTestId('merchant-rules-dedupe'))
    fireEvent.click(await screen.findByTestId('dedupe-run'))
    const selectAll = (await screen.findByTestId(
      'dedupe-select-all-1',
    )) as HTMLInputElement
    expect(selectAll).toBeTruthy()
    expect(selectAll.checked).toBe(false)
  })

  it('checks all candidates when Select all is clicked', async () => {
    vi.mocked(rulesService.findDuplicateMerchantRules).mockResolvedValueOnce({
      groups: [
        {
          canonical: { id: 1, keyword: 'STARBUCKS' },
          candidates: [
            {
              id: 99,
              keyword: 'STARBUCKS COFFEE',
              method: 'substring',
              confidence: 1.0,
              rationale: '',
            },
            {
              id: 100,
              keyword: 'STARBUCKS POS',
              method: 'llm',
              confidence: 0.92,
              rationale: '',
            },
          ],
        },
      ],
      l1_count: 1,
      l2_count: 1,
      l2_status: 'ok',
    })
    render(<SettingsPage />)
    fireEvent.click(await screen.findByTestId('merchant-rules-dedupe'))
    fireEvent.click(await screen.findByTestId('dedupe-run'))
    // Click Select all
    fireEvent.click(await screen.findByTestId('dedupe-select-all-1'))
    // Both candidates should now be checked
    const c99 = (await screen.findByTestId(
      'dedupe-candidate-99',
    )) as HTMLInputElement
    const c100 = (await screen.findByTestId(
      'dedupe-candidate-100',
    )) as HTMLInputElement
    expect(c99.checked).toBe(true)
    expect(c100.checked).toBe(true)
  })

  // Phase 32 — Apply then continue (buttons stay visible, candidates removed)
  it('keeps Apply button visible after a successful apply so user can continue', async () => {
    vi.mocked(rulesService.findDuplicateMerchantRules).mockResolvedValueOnce({
      groups: [
        {
          canonical: { id: 1, keyword: 'STARBUCKS' },
          candidates: [
            {
              id: 99,
              keyword: 'STARBUCKS COFFEE',
              method: 'substring',
              confidence: 1.0,
              rationale: '',
            },
            {
              id: 100,
              keyword: 'STARBUCKS POS',
              method: 'llm',
              confidence: 0.92,
              rationale: '',
            },
          ],
        },
      ],
      l1_count: 1,
      l2_count: 1,
      l2_status: 'ok',
    })
    vi.mocked(rulesService.applyDuplicateMerchantRules).mockResolvedValueOnce({
      archived: 1,
      skipped: 0,
    })
    render(<SettingsPage />)
    fireEvent.click(await screen.findByTestId('merchant-rules-dedupe'))
    fireEvent.click(await screen.findByTestId('dedupe-run'))
    // Tick only the first candidate
    fireEvent.click(await screen.findByTestId('dedupe-candidate-99'))
    fireEvent.click(await screen.findByTestId('dedupe-apply'))
    // After apply, the Apply button should STILL be visible
    // (the removed candidate 99 is gone, but 100 remains)
    await waitFor(() => {
      const applyBtn = screen.getByTestId('dedupe-apply') as HTMLButtonElement
      expect(applyBtn).toBeTruthy()
    })
  })
})
