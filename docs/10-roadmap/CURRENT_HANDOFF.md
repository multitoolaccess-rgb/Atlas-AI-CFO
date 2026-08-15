# Atlas Current Handoff

> Generated from canonical project status. Verify live Git state before editing.

## Current objective

- Phase: phase-6 — Scenario Lab
- Phase status: complete
- Overall status: complete
- Objective: Waves 3–5 Product Stabilization is in progress after Phase 6 certification. Preserve server-owned financial authority, do not begin Wave 6 certification, and do not begin Phase 7.
- Phase exit criteria: 2/2 complete
- Tracker updated: 2026-08-15T21:28:28Z

## Active work

- work-waves-3-5-product-stabilization: Combined Waves 3–5 product stabilization [in_progress/medium]
  - Objective: Stabilize delivered Phase 0–6 integration, discoverability, dead paths, accessibility, reliability, and local personal-use readiness without changing financial authority or beginning Wave 6/Phase 7.
  - Branch: codex/waves-3-5-product-stabilization
  - Paths: ui, services/rules-service/app, services/rules-service/tests, docs

## Blockers

- external-multi-user-retention-deletion-blocker [open]: External multi-user production enablement is BLOCKED until an approved retention and user-deletion policy exists for immutable forecast history.

## Open risks

- risk-frontend-lint-debt [medium/high]: Repository-wide frontend lint debt remains outside Phase 0 scope.
- risk-monte-carlo-deferred [medium/medium]: Monte Carlo probability model is intentionally deferred.
- risk-transitional-tenancy [high/medium]: User-scoped tenancy remains transitional.
- risk-legacy-product-names [low/high]: Legacy Finance Copilot, WealthIQ, CashFlix, and Finlynq names remain.
- risk-fixture-compatibility-names [low/medium]: Synthetic fixture directories retain compatibility-oriented names.
- risk-service-dependency-separation [high/high]: Rules Service and Finlynq require separate FastAPI-pinned environments.
- risk-p1-legacy-goal-float [high/medium]: The existing Goal.target_amount Float can lose source precision before Phase 1 snapshot normalization.
- risk-p1-dialect-parity [high/medium]: SQLite and PostgreSQL differ in exact numeric storage and concurrency semantics for immutable forecast versions.
- risk-p1-retention-rollout-gate [high/medium]: No approved retention or user-deletion policy exists for immutable forecast history.
- risk-p1-trusted-generation-boundary [high/medium]: An untrusted generation request could forge canonical financial state or provenance if the trusted adapter boundary regresses.
- risk-p1-external-provider-local-config [high/medium]: Ignored local configuration has Market Intelligence read/generation/external-provider flags enabled and provider credentials present; no provider call was made in this task, but the local state is not safe to treat as fully disabled.
- risk-p1-local-backup-recovery [high/low]: WAL-safe local backup, disposable restore, and backup-first personal activation have passed; in-place restore remains intentionally unsupported and requires a future separately authorized recovery task.

## Recently completed

- work-wave-2a-authoritative-account-currency: Implement Wave 2A authoritative account-currency evidence — commit a438df9233cb197827a5affda0c24ee4d7ec0a97, PR not recorded
- work-wave-2b-local-backup-recovery: Implement WAL-safe local backup and recovery — commit 423f87a, PR not recorded
- work-wave-2c-personal-activation-acceptance: Execute backup-first personal activation and restart acceptance — commit e877247, PR not recorded
- work-wave-2c-authoritative-balance-amount: Establish exact-cent legacy balance authority — commit 50d7d198de5b28d0d37e9aa596c8e2d90b27452f, PR 58
- work-wave-2c-six-account-activation: Complete six-account personal activation and restart acceptance — commit 9fbe20d, PR 60

## Next bounded task

- work-waves-3-5-product-stabilization: Plan and obtain separate authorization for the combined Waves 3–5 Product Stabilization Wave; do not begin automatically.

Do not begin the next task automatically.
