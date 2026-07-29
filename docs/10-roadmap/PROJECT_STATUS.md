# Atlas Project Status

> Generated from `PROJECT_STATUS.json`; regenerate with `python3 scripts/atlas_project_status.py render`.

- Current phase: **phase-1 — Forecast persistence** (in_progress)
- Overall status: **in_progress**
- Current objective: Phase 1 forecast models and additive migration are complete; repository transactions remain the next bounded slice and require separate authorization.
- Last updated: 2026-07-29T05:52:24Z

## Active work
- work-p1-forecast-repository: Implement immutable forecast repository transactions (in_progress, high)

## Blockers
- None

## Phase progress
- phase-0 — Projection foundation and Atlas baseline: complete (4/4 exit criteria)
- phase-1 — Forecast persistence: in_progress (0/5 exit criteria)
- phase-2 — Forecast UI migration: not_started (0/1 exit criteria)
- phase-3 — Goal-linked recommendations: not_started (0/1 exit criteria)
- phase-4 — Decision journal: not_started (0/1 exit criteria)

## Current risks
- risk-frontend-lint-debt [medium/high, open]: Repository-wide frontend lint debt remains outside Phase 0 scope.
- risk-monte-carlo-deferred [medium/medium, open]: Monte Carlo probability model is intentionally deferred.
- risk-transitional-tenancy [high/medium, open]: User-scoped tenancy remains transitional.
- risk-legacy-product-names [low/high, open]: Legacy Finance Copilot, WealthIQ, CashFlix, and Finlynq names remain.
- risk-fixture-compatibility-names [low/medium, open]: Synthetic fixture directories retain compatibility-oriented names.
- risk-service-dependency-separation [high/high, mitigated]: Rules Service and Finlynq require separate FastAPI-pinned environments.
- risk-p1-legacy-goal-float [high/medium, open]: The existing Goal.target_amount Float can lose source precision before Phase 1 snapshot normalization.
- risk-p1-dialect-parity [high/medium, open]: SQLite and PostgreSQL differ in exact numeric storage and concurrency semantics for immutable forecast versions.
- risk-p1-retention-rollout-gate [high/medium, open]: No approved retention or user-deletion policy exists for immutable forecast history.
- risk-p1-trusted-generation-boundary [high/medium, open]: An untrusted generation request could forge canonical financial state or provenance if the trusted adapter boundary regresses.

## Recently completed work
- work-p0-synthetic-fixtures: Approved synthetic financial fixtures — commit d001e64, PR #1
- work-p1-forecast-persistence-planning: Plan immutable forecast persistence and versioned read APIs — commit a818665, PR #4
- work-dashboard-inclusive-date-upper-bound: Fix inclusive date-only dashboard upper bound — commit e2ebbb2, PR #7
- work-p1-canonical-state-contract: Implement canonical projection-state contract test slice — commit f91de80, PR #6
- work-p1-forecast-persistence-models: Implement immutable forecast persistence models and migration — commit 59b3baa, PR #8

## Evidence
- c0f5287: Atlas baseline initialization from the validated Finance Copilot foundation
- 8baa1c2: Service environment isolation
- d001e64: Merged synthetic fixture restoration #1
- b987147: Phase 1 immutable forecast persistence planning #4
- 6e485ea: Resolved Phase 1 canonical-envelope, validation, and retention planning decisions #4
- a818665: Enforced the trusted adapter-only forecast generation boundary #4
- d85255f: Added immutable forecast persistence models and additive migration from Q5h1i2j3k4l5
- 40517d2: Hardened forecast persistence UUID, SHA-256, and required-version database constraints #8
- 57b8cb5: Prevented rollback from deleting persisted forecast identities and restricted version labels to printable ASCII #8
- a44e15d: Hardened canonical Decimal bounds and sanitized contract validation errors #6
- f91de80: Detached raw validation exception state and bounded caller-facing contract-error locations #6
- 734d35e: Made dashboard date-only ranges inclusive through a half-open next-day bound #7
- 694ec81: Restored bounded open-ended dashboard date ranges while retaining the half-open upper bound #7
- e2ebbb2: Rejected dashboard date ranges whose exclusive next-day bound is unrepresentable #7
- Test test-p0-rules: Rules Service — 579 passed, 10 skipped, 1 xfailed
- Test test-p0-finlynq: Finlynq — 93 passed
- Test test-p0-frontend: Frontend — 496 passed
- Test test-p0-typescript: TypeScript check — passed
- Test test-p1-planning-status: Phase 1 planning governance — 5 passed; status, deterministic render, and trusted generation-boundary documentation checks passed

## Next bounded task
- next-p1-forecast-repository-transactions: Authorize the next bounded Phase 1 slice: repository transactions for immutable forecast versions; do not begin automatically.

Do not begin the next phase or task automatically.
