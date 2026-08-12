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

## Next authorized boundary

After Slice 1 is merged and certified, a separate explicit prompt is required
before any Scenario Lab UI migration. The UI must consume server results and
must not become financial authority.
