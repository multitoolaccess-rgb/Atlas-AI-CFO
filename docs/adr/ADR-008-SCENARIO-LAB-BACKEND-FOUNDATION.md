# ADR-008: Scenario Lab Backend Foundation

- **Status:** Accepted for Phase 6 Slice 1 only
- **Date:** 2026-08-12
- **Scope:** Authoritative owner-scoped Scenario Lab backend; no UI
- **Related:** ADR-005, ADR-006, Phase 6 Scenario Lab plan

## Decision

Atlas extends the existing immutable forecast vertical with a deterministic
Scenario Lab. It does not create a competing projection engine. Rules Service
remains the calculation authority, consumes the existing Finlynq-owned
`CanonicalProjectionState`, constructs the existing `ProjectionRequest`, and
invokes the unchanged Phase 0 Decimal projection engine.

The MVP is one authenticated transitional owner, one owned goal, USD-only,
deterministic, server-authoritative, default-off, and read/analyze/recommend
only. A scenario is not a decision, approval, execution, trade, money movement,
action evidence, guarantee, or probability estimate.

## Supported controls

A strict scenario request may contain one or more of:

1. `monthly_contribution_delta`: a canonical unrounded Decimal string.
2. `contribution_start_date`: ISO date-only boundary for the explicit delta.
3. `contribution_stop_date`: ISO date-only boundary; the delta stops at the
   first monthly boundary on or after this date.
4. `one_time_outflow`: one positive canonical Decimal amount and one date.

The baseline contribution remains in force outside a dated delta window. This
prevents a date on a contribution change from silently inventing a contribution
holiday. A negative adjusted contribution is rejected. Values are bounded by
the canonical Decimal and horizon contracts; no hard-coded dashboard preset is
financial input.

## Monthly boundary and outflow semantics

The projection creates the same eligible month-end sequence as Phase 0. A date
maps to the first eligible month-end on or after that date and must map within
the horizon. For each band and month, the existing projection engine runs for
one month. Its unrounded ending balance becomes the next month's input.

At the selected outflow boundary, the order is:

1. apply the month-end return and scheduled contribution;
2. subtract the one-time outflow exactly once;
3. carry the unrounded remainder forward.

If the outflow exceeds available post-contribution liquidity, generation fails
closed. Atlas does not infer debt, financing, taxes, appreciation, or resale
value. Only the final output boundary uses `ROUND_HALF_EVEN` to cents.

## Baseline compatibility and provenance

Generation loads the latest immutable forecast for the authenticated owned goal.
The trusted adapter reloads canonical state and the service verifies its
canonical state hash against the state embedded in the baseline forecast input
snapshot. A stale, mixed, unknown, unsupported, unreconciled, or missing state
fails closed. The saved version records baseline forecast identity/version,
the baseline input-state hash, scenario input hash, schema/model/calculation
versions, USD, source freshness, canonical scenario inputs, complete result,
and baseline comparison.

The server owns return, inflation, timing, freshness, canonical state,
provenance, hashes, results, and calculation versions. Browser sliders and
legacy JavaScript projection math remain presentation-only and are not changed
in this slice.

## Persistence and APIs

`scenarios` is a stable owner/goal identity with active/archived lifecycle and a
latest-version pointer. `scenario_versions` is append-only and immutable at the
database boundary. UUIDs and lowercase SHA-256 hashes are constrained;
foreign keys are restrictive; ownership consistency is enforced by SQLite and
PostgreSQL triggers. Downgrade refuses while history exists.

The versioned owner APIs generate/persist, list, read latest, read a specific
version, compare one baseline, compare up to three compatible saved scenarios,
and archive without deleting history. Writes require `Idempotency-Key`; strict
bodies use `extra="forbid"`; cross-owner resources return indistinguishable
404s; responses are sanitized and bounded.

An optional recommendation reference is stored as a nullable server field but
this slice does not create or accept a new recommendation type. Existing
review-only recommendation and decision contracts remain authoritative.

## Non-goals and preserved risks

No Scenario Lab UI, Monte Carlo/probability, taxes, business valuation,
portfolio optimization, multi-goal optimization, execution, brokerage,
cloud LLM, paid data, household/advisor sharing, or external multi-user rollout
is included. Immutable-history retention/deletion policy remains an external
rollout blocker. The transitional user scope and legacy Goal Float precision
risk remain explicit.
