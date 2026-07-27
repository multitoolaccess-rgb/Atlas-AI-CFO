import { describe, it, expect } from 'vitest'
import { getTimeRangeDates } from '@/components/ui/TimeRangeSelector'

describe('getTimeRangeDates', () => {
  it('returns valid from/to date strings for every preset', () => {
    const presets = ['7D', '30D', '90D', 'MTD', 'QTD', 'YTD', '1Y', 'ALL'] as const
    for (const preset of presets) {
      const { from, to } = getTimeRangeDates(preset)
      // Must be valid ISO date strings (YYYY-MM-DD)
      expect(from).toMatch(/^\d{4}-\d{2}-\d{2}$/)
      expect(to).toMatch(/^\d{4}-\d{2}-\d{2}$/)
      // from must be before or equal to to
      expect(new Date(from).getTime()).toBeLessThanOrEqual(new Date(to).getTime())
    }
  })

  it('ALL preset starts from 2000-01-01', () => {
    const { from } = getTimeRangeDates('ALL')
    expect(from).toBe('2000-01-01')
  })

  it('MTD preset starts from the first day of the current month', () => {
    const { from, to } = getTimeRangeDates('MTD')
    const now = new Date()
    const expectedFrom = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10)
    expect(from).toBe(expectedFrom)
    // to should be today
    const expectedTo = now.toISOString().slice(0, 10)
    expect(to).toBe(expectedTo)
  })

  it('YTD preset starts from January 1 of the current year', () => {
    const { from } = getTimeRangeDates('YTD')
    const year = new Date().getFullYear()
    expect(from).toBe(`${year}-01-01`)
  })

  it('7D preset covers approximately 7 days', () => {
    const { from, to } = getTimeRangeDates('7D')
    const diffMs = new Date(to).getTime() - new Date(from).getTime()
    const diffDays = diffMs / (1000 * 60 * 60 * 24)
    expect(diffDays).toBeGreaterThanOrEqual(6)
    expect(diffDays).toBeLessThanOrEqual(8)
  })

  it('30D preset covers approximately 30 days', () => {
    const { from, to } = getTimeRangeDates('30D')
    const diffMs = new Date(to).getTime() - new Date(from).getTime()
    const diffDays = diffMs / (1000 * 60 * 60 * 24)
    expect(diffDays).toBeGreaterThanOrEqual(29)
    expect(diffDays).toBeLessThanOrEqual(31)
  })

  it('90D preset covers approximately 90 days', () => {
    const { from, to } = getTimeRangeDates('90D')
    const diffMs = new Date(to).getTime() - new Date(from).getTime()
    const diffDays = diffMs / (1000 * 60 * 60 * 24)
    expect(diffDays).toBeGreaterThanOrEqual(89)
    expect(diffDays).toBeLessThanOrEqual(91)
  })

  it('1Y preset covers approximately 1 year', () => {
    const { from, to } = getTimeRangeDates('1Y')
    const diffMs = new Date(to).getTime() - new Date(from).getTime()
    const diffDays = diffMs / (1000 * 60 * 60 * 24)
    // Allow leap year variance
    expect(diffDays).toBeGreaterThanOrEqual(364)
    expect(diffDays).toBeLessThanOrEqual(366)
  })
})
