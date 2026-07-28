# ADR-005: Atlas Vertical-Slice Foundation

- **Status:** Accepted
- **Date:** 2026-07-26
- **Scope:** Phase 0 of the first Atlas vertical slice

## Context

Atlas requires financial projections, recommendations, explanations, and
decisions to be reproducible, explainable, and historically attributable.
Finance Copilot currently calculates goal projections in the browser with
JavaScript numbers, stores recommendation reasoning and lifecycle state in one
mutable row, and scopes records directly to the local user.

Phase 0 establishes calculation and migration boundaries without adding
forecast persistence, recommendation models, decision-journal tables, or UI
changes.

## Decision

### Projection authority and arithmetic

The rules-service is authoritative for financial projections. The UI may retain
temporary comparison or display calculations during migration, but it must not
be treated as the source of financial truth.

Material financial calculations use Python `Decimal`, never binary floating
point. The first release supports USD while requiring an explicit `currency`
field in calculation inputs and outputs. Unsupported or missing currencies are
rejected rather than inferred.

Calculations use monthly periods. Contributions occur at the end of each month
unless a goal explicitly specifies another supported contribution timing.
Stored monetary outputs will be rounded to the currency precision using
round-half-even. Intermediate calculations remain unrounded until an output
crosses a persistence or API boundary.

### Projection interpretation

The first projection release produces conservative, base, and optimistic
scenario bands from explicit assumptions. These bands are deterministic
scenarios and must not be described as statistical probabilities.

Monte Carlo probability is deferred until Atlas specifies its distributions,
correlations, taxes and cash-flow behavior, validation fixtures, calibration
requirements, and acceptable error bounds.

### Forecast identity and history

A forecast will have a stable identity and immutable versions. Each forecast
version will record:

- normalized inputs;
- explicit assumptions;
- calculation/model version;
- source-data freshness;
- unambiguous currency and timing conventions; and
- structured outputs and drivers.

Forecast persistence is not introduced in Phase 0.

### Recommendations and decisions

Recommendations may link to multiple goals through an explicit join model.
Recommendation reasoning will be immutable and versioned separately from its
current lifecycle state.

Accepting, rejecting, or deferring a recommendation will create a Decision and
an append-only decision event. That behavior and its schema are deferred to a
later reviewed phase.

The existing `recommendation_logs` table remains operational throughout the
migration and must not be dropped. Existing unversioned APIs also remain
operational until versioned replacements have reached parity and have a
documented rollback path.

### Tenancy migration

Phase 0 remains user-scoped. `user_id` is a transitional ownership key, not the
permanent Atlas tenancy model. Future migrations will add household identity
and membership-based authorization, backfill each existing user into an
explicit household, dual-read and validate ownership, then enforce household
scope. Existing rows must never be silently reinterpreted as household-scoped.

### Service boundary

Finlynq remains the ingestion and canonical financial-state source.
Rules-service owns Atlas calculations and, in later phases, forecasts,
recommendations, and decisions.

The current shared database is a migration constraint, not a license to expand
cross-service table ownership. New Atlas calculation code consumes explicit
canonical-state inputs. It does not query or mutate Finlynq-owned tables
directly. Later persistence must use service-owned repositories and documented
contracts so the shared-database coupling can be reduced.

## Consequences

- Phase 0 needs no Alembic migration.
- The backend projection module is pure and has no database, HTTP, or model
  dependencies.
- Shared JSON fixtures become the cross-language calculation contract.
- The existing UI, recommendation behavior, default-goal behavior, and
  unversioned routes are unchanged in this phase.
- Monthly end-of-period math intentionally differs from the existing annual
  contribution approximation.

## Deferred decisions

- Forecast and forecast-version schemas and APIs. ADR-006 proposes the Phase 1
  resolution; it remains deferred until ADR-006 is accepted.
- Supported non-USD currencies and currency metadata source.
- Additional contribution timings and irregular cash-flow schedules.
- Monte Carlo assumptions and calibration.
- Household schema and authorization policy.
- Recommendation, decision, and append-only audit schemas.
