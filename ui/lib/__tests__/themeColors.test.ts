import { describe, expect, it } from 'vitest'
import { DASHBOARD_COLORS, resolveGroupColor } from '../themeColors'

describe('resolveGroupColor', () => {
  const dark = DASHBOARD_COLORS.dark
  const light = DASHBOARD_COLORS.light

  it('maps known budget groups to their canonical palette colors', () => {
    expect(resolveGroupColor('flexible', dark)).toBe(dark.flexible)
    expect(resolveGroupColor('fixed', dark)).toBe(dark.essential)
    expect(resolveGroupColor('essential', dark)).toBe(dark.essential)
    expect(resolveGroupColor('savings', dark)).toBe(dark.savings)
    expect(resolveGroupColor('debt', dark)).toBe(dark.debt)
    expect(resolveGroupColor('investments', dark)).toBe(dark.invest)
    expect(resolveGroupColor('income', dark)).toBe(dark.income_accent)
    // Case/whitespace tolerant.
    expect(resolveGroupColor('  Flexible ', dark)).toBe(dark.flexible)
  })

  it('keeps the transfer role neutral grey', () => {
    expect(resolveGroupColor('transfer', dark)).toBe(dark.transfer)
  })

  it('renders catch-all buckets (other/uncategorized/empty) in a real hue, not grey', () => {
    // Regression: these buckets used to map to the grey `transfer` color,
    // so "Other" and "Uncategorized" slices were slate in every chart.
    for (const key of ['other', 'uncategorized', '']) {
      const color = resolveGroupColor(key, dark)
      expect(color).toMatch(/^#[0-9a-fA-F]{6}$/)
      expect(color.toLowerCase()).not.toBe(dark.transfer.toLowerCase())
    }
  })

  it('is deterministic — the same key always resolves to the same color', () => {
    const a = resolveGroupColor('other', dark)
    const b = resolveGroupColor('other', dark)
    expect(a).toBe(b)
  })

  it('works the same in light mode', () => {
    expect(resolveGroupColor('flexible', light)).toBe(light.flexible)
    const other = resolveGroupColor('other', light)
    expect(other.toLowerCase()).not.toBe(light.transfer.toLowerCase())
    expect(other).toMatch(/^#[0-9a-fA-F]{6}$/)
  })
})