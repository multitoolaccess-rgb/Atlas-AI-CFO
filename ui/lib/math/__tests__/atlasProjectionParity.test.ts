import { describe, expect, it } from 'vitest'
import goldenFixture from '../../../../tests/fixtures/atlas_projection_cases.json'
import { projectDashboardTrajectory } from '../projection'

type ScenarioName = 'conservative' | 'base' | 'optimistic'

type ProjectionCase = {
  id: string
  tags: string[]
  input: {
    currency?: string
    current_balance?: string
    monthly_contribution?: string
    horizon_months?: number
    annual_inflation_rate?: string
    annual_return_rates?: Record<ScenarioName, string>
  }
  expected?: {
    scenario_ending_balances: Record<ScenarioName, string>
  }
}

const SCENARIOS: ScenarioName[] = ['conservative', 'base', 'optimistic']

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function requireDecimalString(value: unknown, label: string): string {
  if (typeof value !== 'string') {
    throw new Error(`${label} must be a decimal string`)
  }
  return value
}

function parseCases(value: unknown): ProjectionCase[] {
  if (!Array.isArray(value)) throw new Error('fixture cases must be an array')

  return value.map((rawCase, index) => {
    if (
      !isRecord(rawCase)
      || typeof rawCase.id !== 'string'
      || !Array.isArray(rawCase.tags)
      || !rawCase.tags.every((tag) => typeof tag === 'string')
      || !isRecord(rawCase.input)
    ) {
      throw new Error(`fixture case ${index} has an invalid shape`)
    }

    const input = rawCase.input
    for (const field of [
      'current_balance',
      'monthly_contribution',
      'annual_inflation_rate',
    ] as const) {
      if (input[field] !== undefined) {
        requireDecimalString(input[field], `${rawCase.id}.${field}`)
      }
    }
    if (input.annual_return_rates !== undefined) {
      if (!isRecord(input.annual_return_rates)) {
        throw new Error(`${rawCase.id}.annual_return_rates must be an object`)
      }
      for (const scenario of SCENARIOS) {
        requireDecimalString(
          input.annual_return_rates[scenario],
          `${rawCase.id}.annual_return_rates.${scenario}`,
        )
      }
    }
    if (rawCase.expected !== undefined) {
      if (
        !isRecord(rawCase.expected)
        || !isRecord(rawCase.expected.scenario_ending_balances)
      ) {
        throw new Error(`${rawCase.id}.expected scenario balances are required`)
      }
      for (const scenario of SCENARIOS) {
        requireDecimalString(
          rawCase.expected.scenario_ending_balances[scenario],
          `${rawCase.id}.expected.${scenario}`,
        )
      }
    }

    return rawCase as ProjectionCase
  })
}

const cases = parseCases(goldenFixture.cases)
const legacyParityCases = cases.filter((testCase) =>
  testCase.tags.includes('legacy-parity'),
)

describe('Atlas shared projection fixture parity', () => {
  it('loads the same versioned JSON contract used by backend tests', () => {
    expect(goldenFixture.schema_version).toBe('atlas-projection-fixtures/v1')
    expect(goldenFixture.model_version).toBe('atlas-monthly-scenarios/v1')
    expect(goldenFixture.money).toEqual({
      currency: 'USD',
      precision: '0.01',
      rounding: 'ROUND_HALF_EVEN',
    })
    expect(
      cases.some((testCase) => testCase.tags.includes('nonzero-inflation')),
    ).toBe(true)
  })

  it('defines the required exact legacy parity contract explicitly', () => {
    expect(legacyParityCases.map((testCase) => testCase.id)).toEqual([
      'zero-return',
    ])
  })

  it.each(legacyParityCases)(
    'matches the authoritative result for explicitly compatible case $id',
    (testCase) => {
      const input = testCase.input
      const expected = testCase.expected
      if (
        input.current_balance === undefined
        || input.monthly_contribution === undefined
        || input.horizon_months === undefined
        || input.annual_return_rates === undefined
        || expected === undefined
      ) {
        throw new Error(`Incomplete legacy parity fixture: ${testCase.id}`)
      }

      for (const scenario of SCENARIOS) {
        const legacyResult = projectDashboardTrajectory({
          netWorth: Number(input.current_balance),
          monthlyContribution: Number(input.monthly_contribution),
          annualReturnRate: Number(input.annual_return_rates[scenario]),
          years: input.horizon_months / 12,
          annualInflationRate: Number(input.annual_inflation_rate ?? '0'),
        })

        expect(legacyResult).toBeCloseTo(
          Number(expected.scenario_ending_balances[scenario]),
          8,
        )
      }
    },
  )

  it('pins the known annual-versus-monthly timing difference', () => {
    const positiveContribution = cases.find(
      (testCase) => testCase.id === 'positive-monthly-contribution',
    )
    if (
      !positiveContribution?.input.current_balance
      || !positiveContribution.input.monthly_contribution
      || !positiveContribution.input.horizon_months
      || !positiveContribution.input.annual_return_rates
      || !positiveContribution.expected
    ) {
      throw new Error('Missing positive contribution comparison fixture')
    }

    const expectedLegacyResults: Record<ScenarioName, number> = {
      conservative: 16_200,
      base: 16_500,
      optimistic: 16_800,
    }
    for (const scenario of SCENARIOS) {
      const legacyResult = projectDashboardTrajectory({
        netWorth: Number(positiveContribution.input.current_balance),
        monthlyContribution: Number(
          positiveContribution.input.monthly_contribution,
        ),
        annualReturnRate: Number(
          positiveContribution.input.annual_return_rates[scenario],
        ),
        years: positiveContribution.input.horizon_months / 12,
        annualInflationRate: Number(
          positiveContribution.input.annual_inflation_rate ?? '0',
        ),
      })
      const authoritativeMonthlyResult = Number(
        positiveContribution.expected.scenario_ending_balances[scenario],
      )

      expect(legacyResult).toBeCloseTo(expectedLegacyResults[scenario], 8)
      expect(legacyResult).not.toBeCloseTo(authoritativeMonthlyResult, 2)
    }
  })
})
