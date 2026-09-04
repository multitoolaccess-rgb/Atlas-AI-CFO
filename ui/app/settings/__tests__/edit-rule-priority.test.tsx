/**
 * Regression — editing a high-priority system rule.
 *
 * The system seed assigns ``priority = 10 * position`` across ~166
 * rules, so the last ones land ABOVE 999 (e.g. LOWES at 1660). The
 * edit-rule modal used to hard-cap priority at 999, which made those
 * rules literally un-editable ("Please select a value that is no more
 * than 999."). The backend accepts any positive integer, so the FE
 * cap was removed. This test locks the fix: a rule at priority 1660
 * opens in the modal and saves without a validation error.
 */
import React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('@/lib/api', () => {
  const getProfile = vi.fn()
  const getReadiness = vi.fn()
  const listFamilyMembers = vi.fn()
  const listMerchantRules = vi.fn()
  const listCategories = vi.fn()
  const updateMerchantRule = vi.fn()
  return {
    rulesService: {
      getProfile,
      getReadiness,
      listFamilyMembers,
      listMerchantRules,
      listCategories,
      updateMerchantRule,
    },
    RELATIONSHIP_OPTIONS: [
      { value: 'Self', label: 'Self' },
      { value: 'Spouse', label: 'Spouse' },
      { value: 'Child', label: 'Child' },
      { value: 'Parent', label: 'Parent' },
      { value: 'Sibling', label: 'Sibling' },
      { value: 'Other', label: 'Other' },
    ],
    MERCHANT_RULE_SOURCE_OPTIONS: [
      { value: 'system', label: 'System seed (fizzy)' },
      { value: 'manual', label: 'Manual (Settings)' },
      { value: 'tag-rule', label: 'Tag rule (Activity)' },
      { value: 'llm', label: 'LLM-suggested' },
      { value: 'imported', label: 'Imported (CSV)' },
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

vi.mock('@/lib/dataRefresh', () => ({
  fireDataRefresh: vi.fn(),
}))

// The Modal component is portal-based; stub it as a div that renders
// BOTH children AND footer (the Save button lives in the footer).
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
      <div data-testid="edit-rule-modal-stub">
        <div data-testid="edit-rule-modal-body">{children}</div>
        <div data-testid="edit-rule-modal-footer">{footer}</div>
      </div>
    )
  },
}))

// Preserve value/onChange so the form fields actually drive state.
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
  Input: ({
    label,
    value,
    onChange,
    min,
    step,
    ...rest
  }: React.InputHTMLAttributes<HTMLInputElement> & { label?: string }) => (
    <input
      aria-label={label}
      value={value}
      onChange={onChange}
      min={min}
      step={step}
      {...rest}
    />
  ),
  Select: ({
    label,
    value,
    onChange,
    options,
  }: {
    label?: string
    value?: string
    onChange?: (e: React.ChangeEvent<HTMLSelectElement>) => void
    options?: Array<{ value: string; label: string }>
  }) => (
    <select aria-label={label} value={value} onChange={onChange}>
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}))

vi.mock('@/components/ui/ErrorBanner', () => ({
  default: ({ title, message }: { title: string; message: string }) => (
    <div data-testid="error-banner">
      {title} {message}
    </div>
  ),
}))

import SettingsPage from '@/app/settings/page'

const HIGH_PRIORITY_RULE = {
  id: 1660,
  category_id: 1,
  category_name: 'Shopping',
  keyword: 'LOWES',
  priority: 1660,
  is_archived: false,
  source: 'system' as const,
}

describe('Settings — edit merchant rule priority', () => {
  beforeEach(() => {
    vi.mocked(rulesService.getProfile).mockResolvedValue({
      id: 1,
      email: 'test@example.com',
      full_name: 'Test',
      currency_preference: 'USD',
    })
    vi.mocked(rulesService.getReadiness).mockResolvedValue({
      schema_version: 'atlas-readiness/v1',
      overall_state: 'ready_with_blocked_optional_capabilities',
      checked_at: '2026-08-15T00:00:00Z',
      checks: [],
      feature_flags: {},
      credentials: {},
      prohibited_capabilities: {},
    })
    vi.mocked(rulesService.listFamilyMembers).mockResolvedValue([])
    vi.mocked(rulesService.listMerchantRules).mockResolvedValue([
      HIGH_PRIORITY_RULE,
    ])
    vi.mocked(rulesService.listCategories).mockResolvedValue([
      { id: 1, name: 'Shopping', group: 'Expenses' },
    ])
    vi.mocked(rulesService.updateMerchantRule).mockResolvedValue(
      HIGH_PRIORITY_RULE,
    )
  })

  it('opens the edit modal for a priority-1660 rule without a validation error', async () => {
    render(<SettingsPage />)

    const editButton = await screen.findByTestId('merchant-rule-edit-1660')
    fireEvent.click(editButton)

    // The priority field pre-fills with the real (high) value.
    const priorityInput = await screen.findByTestId('edit-rule-priority')
    expect((priorityInput as HTMLInputElement).value).toBe('1660')
    // No "no more than 999" validation error is shown.
    expect(screen.queryByText(/no more than 999/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Priority must be/i)).not.toBeInTheDocument()
  })

  it('saves the rule keeping its high priority intact', async () => {
    render(<SettingsPage />)

    const editButton = await screen.findByTestId('merchant-rule-edit-1660')
    fireEvent.click(editButton)

    const keywordInput = await screen.findByTestId('edit-rule-keyword')
    fireEvent.change(keywordInput, { target: { value: 'LOWES HOME' } })

    // Submit through the form (the Save button is a submit button).
    fireEvent.submit(screen.getByTestId('edit-merchant-rule-form'))

    await waitFor(() => {
      expect(rulesService.updateMerchantRule).toHaveBeenCalledWith(1660, {
        category_id: 1,
        keyword: 'LOWES HOME',
        priority: 1660,
      })
    })
  })
})
