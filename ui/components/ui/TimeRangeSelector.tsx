'use client'

import { useCallback } from 'react'

export type TimeRangePreset = '7D' | '30D' | '90D' | 'MTD' | 'QTD' | 'YTD' | '1Y' | 'ALL'

interface TimeRangeSelectorProps {
  value: TimeRangePreset
  onChange: (preset: TimeRangePreset) => void
  className?: string
}

const PRESETS: { value: TimeRangePreset; label: string }[] = [
  { value: '7D', label: '7D' },
  { value: '30D', label: '30D' },
  { value: '90D', label: '90D' },
  { value: 'MTD', label: 'MTD' },
  { value: 'QTD', label: 'QTD' },
  { value: 'YTD', label: 'YTD' },
  { value: '1Y', label: '1Y' },
  { value: 'ALL', label: 'All' },
]

export default function TimeRangeSelector({ value, onChange, className = '' }: TimeRangeSelectorProps) {
  return (
    <div
      className={`inline-flex items-center gap-0.5 p-0.5 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border-color)] overflow-x-auto max-w-full ${className}`}
      role="radiogroup"
      aria-label="Time range"
    >
      {PRESETS.map((preset) => (
        <button
          key={preset.value}
          role="radio"
          aria-checked={value === preset.value}
          onClick={() => onChange(preset.value)}
          className={`
            px-2.5 py-1 rounded-md text-xs font-semibold tracking-wide
            transition-all duration-200 ease-out select-none
            focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--primary-500)]
            ${
              value === preset.value
                ? 'bg-[var(--bg-primary)] text-[var(--text-primary)] border border-[var(--border-color)] shadow-none'
                : 'text-[var(--text-tertiary)] hover:text-[var(--text-primary)] border border-transparent'
            }
          `}
        >
          {preset.label}
        </button>
      ))}
    </div>
  )
}

/** Compute from/to date strings for a given preset. */
export function getTimeRangeDates(preset: TimeRangePreset): { from: string; to: string } {
  const now = new Date()
  const to = now.toISOString().slice(0, 10)

  switch (preset) {
    case '7D': {
      const d = new Date(now); d.setDate(d.getDate() - 7)
      return { from: d.toISOString().slice(0, 10), to }
    }
    case '30D': {
      const d = new Date(now); d.setDate(d.getDate() - 30)
      return { from: d.toISOString().slice(0, 10), to }
    }
    case '90D': {
      const d = new Date(now); d.setDate(d.getDate() - 90)
      return { from: d.toISOString().slice(0, 10), to }
    }
    case 'MTD': {
      return { from: new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10), to }
    }
    case 'QTD': {
      const q = Math.floor(now.getMonth() / 3) * 3
      return { from: new Date(now.getFullYear(), q, 1).toISOString().slice(0, 10), to }
    }
    case 'YTD': {
      return { from: new Date(now.getFullYear(), 0, 1).toISOString().slice(0, 10), to }
    }
    case '1Y': {
      const d = new Date(now); d.setFullYear(d.getFullYear() - 1)
      return { from: d.toISOString().slice(0, 10), to }
    }
    case 'ALL': {
      return { from: '2000-01-01', to }
    }
  }
}
