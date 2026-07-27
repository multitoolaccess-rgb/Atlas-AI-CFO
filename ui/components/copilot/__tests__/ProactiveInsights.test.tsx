import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ProactiveInsights, {
  deriveProactiveInsights,
} from '@/components/copilot/ProactiveInsights'
import type { InsightItem } from '@/lib/api'

describe('ProactiveInsights', () => {
  it('renders empty state when no insights', () => {
    render(<ProactiveInsights insights={[]} />)
    expect(screen.getByTestId('copilot-insights-empty')).toBeTruthy()
  })

  it('renders up to maxItems cards', () => {
    const insights: ProactiveInsight[] = [
      'Save $720 by canceling subscriptions',
      'Mortgage could accelerate by 14 months',
      'Crossed $500k net worth',
      'Dining trend up 18%',
    ].map((headline, i) => ({
      category: ['opportunity', 'warning', 'achievement', 'opportunity'][i] as 'opportunity',
      headline,
    }))
    render(<ProactiveInsights insights={insights} maxItems={2} />)
    expect(screen.getAllByTestId(/^copilot-insight-/)).toHaveLength(2)
  })

  it('renders the Ask Scout button when onAsk + askQuery are provided', () => {
    const onAsk = () => {}
    render(
      <ProactiveInsights
        insights={[
          {
            category: 'opportunity',
            headline: 'Save $720 by canceling subscriptions',
            askQuery: 'Where can I cut subscriptions?',
          },
        ]}
        onAsk={onAsk}
      />,
    )
    expect(screen.getByTestId('copilot-insight-ask-0')).toBeTruthy()
  })

  it('deriveProactiveInsights maps warning type to warning category', () => {
    const raw: InsightItem[] = [
      {
        category: 'Dining',
        current: 750,
        previous: 600,
        change_pct: 25,
        type: 'warning',
        message: 'Dining spending up 25% this month',
      },
    ]
    const out = deriveProactiveInsights(raw)
    expect(out[0].category).toBe('warning')
    expect(out[0].metric).toBe('+25%')
    expect(out[0].askQuery).toMatch(/dining/i)
  })

  it('deriveProactiveInsights maps success type to achievement category', () => {
    const raw: InsightItem[] = [
      {
        category: 'Savings',
        current: 1000,
        previous: 600,
        change_pct: 66,
        type: 'success',
        message: 'Savings up 66% month-over-month',
      },
    ]
    const out = deriveProactiveInsights(raw)
    expect(out[0].category).toBe('achievement')
  })

  it('deriveProactiveInsights maps info/other type to opportunity category', () => {
    const raw: InsightItem[] = [
      {
        category: 'Income',
        current: 5000,
        previous: 4800,
        change_pct: 4,
        type: 'info',
        message: 'Income steady',
      },
    ]
    const out = deriveProactiveInsights(raw)
    expect(out[0].category).toBe('opportunity')
  })
})

// Local alias for the test fixture
type ProactiveInsight = {
  category: 'opportunity' | 'warning' | 'achievement' | 'info'
  headline: string
  detail?: string
  metric?: string
  askQuery?: string
}
