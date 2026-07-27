# Atlas Projection Parity: Phase 0

## Purpose

Phase 0 introduces an authoritative backend projection calculation while
leaving the production UI unchanged. Both Python and TypeScript tests read
`tests/fixtures/atlas_projection_cases.json`.

The fixture values are decimal strings so parsing the contract does not first
pass monetary values through a JSON binary floating-point representation.
The shared `positive-contribution-with-inflation` case exercises the Fisher
real-rate conversion with 2% annual inflation.

## Authoritative formula

For each deterministic scenario:

```text
real annual rate = ((1 + annual return) / (1 + annual inflation)) - 1
monthly rate = real annual rate / 12

FV = PV × (1 + monthly rate)^months
   + PMT × (((1 + monthly rate)^months - 1) / monthly rate)
```

When the monthly rate is zero:

```text
FV = PV + PMT × months
```

`PMT` is applied at the end of every month. Python `Decimal` intermediates use
50 digits of precision. Monetary results are rounded to USD cents with
round-half-even only at the output boundary.

## Exact parity

The existing TypeScript calculation uses annual periods and converts a monthly
contribution to one annual contribution. It exactly matches the new
authoritative calculation for the shared `zero-return` case because no
compounding-timing difference exists:

```text
$1,000 + ($100 × 12 months) = $2,200.00
```

The parity test selects exact-match cases using the explicit `legacy-parity`
fixture tag. It does not imply that all existing UI projections match the new
calculation.

## Intentional differences

| Concern | Existing TypeScript | Authoritative Python |
|---|---|---|
| Numeric representation | JavaScript binary `number` | Python `Decimal` |
| Period | Annual | Monthly |
| Contributions | Monthly amount multiplied by 12 and applied as an annual annuity payment | Applied at each month end |
| Return conversion | Annual real rate compounded annually | Annual real rate divided into 12 monthly periods |
| Output rounding | Returns an unrounded JavaScript number | USD cents, round-half-even |
| Scenarios | One caller-selected rate | Conservative, base, optimistic |
| Interpretation | Point projection | Three deterministic scenario bands, not probabilities |
| Validation | Finite values, rate and horizon bounds | Currency, financial inputs, dates, freshness, timing, assumptions, and scenario ordering |

At non-zero returns, even a zero-contribution projection differs because
`(1 + annual_rate / 12)^12` is not equal to `1 + annual_rate`. With
contributions, end-of-month deposits also receive different amounts of growth
than one annualized deposit.

These differences are expected. Phase 0 does not replace the production UI
calculation. A later reviewed phase will consume backend forecast resources and
remove the legacy calculation only after comparison telemetry and rollback
criteria are defined.
