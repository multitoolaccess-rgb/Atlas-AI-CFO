# Phase 6 Scenario Lab Plan

## Authorization

Phase 6 Slice 1 is explicitly authorized as one cohesive high-risk backend
change. This plan does not authorize the Scenario Lab UI or Phase 7.

## Slice 1 outcome

Provide a deterministic, Decimal-safe, goal-scoped Scenario Lab backend by
extending the existing immutable forecast authority. A user can generate,
save, reopen, archive, and compare bounded scenarios against an owned immutable
baseline forecast.

### Included

- Strict explicit contribution delta/start/stop and one-time outflow contract.
- Server-owned canonical state, freshness, currency, return, inflation, target,
  provenance, hashes, and versions.
- Monthly-boundary transformation around the unchanged Phase 0 engine.
- Immutable scenario identity/version models and additive migration.
- SQLite/PostgreSQL ownership and immutability enforcement.
- Required idempotency, bounded pagination, ETags, sanitized errors, and 404
  cross-owner behavior.
- Generate/list/latest/version/compare/compare-set/archive APIs.
- Synthetic first-party tests for math, hashing, persistence, concurrency,
  owner isolation, redaction, migration, and regression suites.
- ADR, contract, API/schema documentation, tracker and handoff evidence.

### Excluded

No UI bytes, browser route, JavaScript slider authority, probability, Monte
Carlo, tax, debt, financing, appreciation, resale, execution, brokerage,
money movement, multi-goal optimization, collaboration, paid data, cloud LLM,
or Phase 7 work.

## Acceptance gates

1. `ScenarioInput` rejects unknown/prohibited client fields and all values are
   bounded; canonical Decimal and hash ordering are deterministic.
2. Contribution boundary and one-time outflow behavior are fixture-tested;
   outflow consumes liquidity once and fails closed if it would create debt.
3. Existing Phase 0 projections remain unchanged and scenario calculations are
   independent of the ambient Decimal context.
4. Baseline compatibility rejects stale/mixed/unknown/non-USD/unreconciled
   canonical state before persistence.
5. Scenario versions are immutable, monotonic, owner/goal consistent, and
   archive preserves history. Idempotent replay and divergent-key conflict are
   deterministic under concurrent generation.
6. API bodies are strict, owner IDs and financial authority are server-derived,
   pagination/compare limits are bounded, cross-owner resources are 404, and
   default-off behavior is server-owned.
7. SQLite and PostgreSQL migration paths are additive with restrictive keys,
   database immutability triggers, safe downgrade refusal, and round-trip
   evidence.
8. Complete relevant Rules Service, Finlynq, cross-service, tracker/render,
   and Phase 0–5 regression evidence is recorded.

## Slice 2 UI vertical slice

Slice 2 is a separate medium-risk frontend boundary authorized after Slice 1.
The authoritative route remains `/scenario-lab`; the UI consumes only the
server-owned list, envelope, comparison-set, version, and archive responses.

### Slice 2 included

- Bookmarkable `view`, goal, scenario, and bounded comparison URL state.
- Baseline readiness, disabled, missing-baseline, stale/conflict, loading,
  empty, unavailable, and sanitized error states.
- Strict bounded builder for contribution delta/start/stop and one dated outflow.
- Typed Decimal-string result presentation with deterministic band comparison,
  timing, freshness, assumptions, warnings, limitations, and provenance.
- Explicit one-to-three scenario comparison selection and incompatible recovery.
- Immutable archive history and persisted-detail reload behavior.
- Stable intent-scoped idempotency keys for generation and archive retries.
- Route-mocked browser coverage that does not start Rules Service, Finlynq, OCR,
  or the live stack.
- Legacy local simulation calculators removed from Mission Control rendering and
  retained only as quarantined compatibility code; they are not Scenario Lab
  authority.

### Slice 2 excluded

No backend changes, forecast-generation action, client-side financial engine,
trajectory/timeline reconstruction, probability, Monte Carlo, tax, debt,
financing, optimization, execution, brokerage, money movement, collaboration,
provider, or Phase 7 work.

Slice 2 implementation is complete when focused UI/API tests, TypeScript, lint,
route-mocked journeys, tracker/render validation, handoff validation, and
applicable medium-risk review evidence are green. Phase 6 certification remains
a separate clean-main task and is not implied by Slice 2 completion.

## Next authorized boundary

After Slice 2 is merged, a separate clean-main Phase 6 certification task is
required before any phase-completion tag. The UI must consume server results and
must not become financial authority.
