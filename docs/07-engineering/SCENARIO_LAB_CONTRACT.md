# Scenario Lab Contract — Phase 6 Slice 1

## Runtime boundary

Rules Service is authoritative. It receives a trusted `CanonicalProjectionState`
from the Finlynq adapter, derives the owned goal and latest immutable baseline
forecast, creates a `ProjectionRequest`, and delegates all monthly return,
inflation, target, and deterministic-band arithmetic to the unchanged Phase 0
engine. The client supplies no owner IDs, balances, holdings, canonical state,
provenance, result snapshots, hashes, or calculation versions.

Feature flag: `ATLAS_SCENARIO_LAB_ENABLED`, server-owned and default `false`.

## Request

`POST /api/v1/goals/{goal_id}/scenarios`

Headers:

- `Authorization` or authenticated session cookie, resolved server-side.
- Required `Idempotency-Key`: 1–255 visible ASCII characters; only its SHA-256
  digest is persisted.

Strict JSON body (`extra="forbid"`):

```json
{
  "scenario_id": "optional lowercase UUID for a new immutable version",
  "monthly_contribution_delta": "optional canonical Decimal",
  "contribution_start_date": "optional YYYY-MM-DD",
  "contribution_stop_date": "optional YYYY-MM-DD",
  "one_time_outflow": {
    "date": "YYYY-MM-DD",
    "amount": "positive canonical Decimal"
  }
}
```

At least one supported change is required. Monetary strings are finite,
unrounded, non-exponent canonical Decimal values, bounded to the canonical
financial input limits and absolute amount bound. Dates are date-only, bounded
to the projection horizon, and start cannot follow stop. One outflow only.

## Exact timing

The baseline contribution remains active outside a dated contribution-delta
window. The delta becomes active at the first eligible month-end on or after
`contribution_start_date`; it becomes inactive at the first eligible month-end
on or after `contribution_stop_date`. Without either date, the delta applies to
every eligible month.

A one-time outflow maps to the first eligible month-end on or after its date.
That boundary runs the existing monthly projection first, adds the scheduled
baseline/delta contribution, then subtracts the outflow once. Liquidity is
measured immediately after that month-end projection. If insufficient, the
request fails closed; no debt is inferred.

All bands carry unrounded Decimal balances between month calls. Final money is
quantized to USD cents using `ROUND_HALF_EVEN`. No probability, confidence,
financing, tax, appreciation, resale, or execution semantics exist.

## Saved version

Each saved version contains or references:

- stable scenario UUID and immutable positive version number;
- transitional owner and goal;
- baseline forecast UUID/version and baseline canonical input-state hash;
- canonical scenario input hash;
- `atlas-scenario-lab/v1`, model, and calculation versions;
- `USD` and source freshness;
- canonical scenario inputs;
- complete deterministic conservative/base/optimistic result snapshot;
- baseline comparison snapshot;
- creation timestamp, lifecycle state through the identity row; and
- nullable optional recommendation reference.

Version rows cannot be updated or deleted by application or database trigger.
Archive changes only the identity lifecycle and preserves every version.

## Comparison response

The base comparison returns ending net worth, difference from baseline, target
amount/gap/reached state, contribution difference, one-time liquidity consumed,
deterministic conservative/base/optimistic bands, mapped timing impact,
server-owned assumptions, source freshness, warnings, and limitations. Band
labels are deterministic assumptions, never probabilities.

## Error and authorization contract

- Missing/cross-owner goals and scenarios are sanitized 404s.
- Missing baseline, stale baseline, incompatible comparison, idempotency
  divergence, unsupported currency, stale/unreconciled canonical state, and
  invalid required inputs fail closed with stable codes.
- Error bodies contain bounded locations/categories only and never rejected
  values, secrets, raw financial payloads, or client field-name echoes.
- List pagination is bounded (`limit` 1–50); compare accepts 1–3 compatible
  saved scenarios.
- API is unavailable while the server feature flag is off.

## Explicit non-goals

Scenario Lab UI migration, legacy dashboard preset replacement, Monte Carlo,
taxes, withdrawals, business scenarios, portfolio optimization, multiple goals,
execution, money movement, brokerage, cloud LLMs, paid-data providers,
household/advisor collaboration, and Phase 7 work.
