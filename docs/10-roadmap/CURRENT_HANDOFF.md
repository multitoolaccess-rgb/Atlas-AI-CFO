# Atlas Current Handoff

> Generated from canonical project status. Verify live Git state before editing.

## Current objective

- Phase: phase-6 — Scenario Lab
- Phase status: complete
- Overall status: complete
- Objective: Phase 6 is certified; Wave 2C exact-cent balance authority is complete on the disposable clone, but personal activation is blocked by a live precondition mismatch: the configured personal database has six active accounts and only four have currency evidence while the authorized validation scope covered four. Preserve server-owned financial authority and do not begin Wave 3 or Phase 7.
- Phase exit criteria: 2/2 complete
- Tracker updated: 2026-08-15T20:46:03Z

## Active work

- None

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
- risk-p1-account-currency-authority [high/medium]: The exact-cent balance-authority contract and disposable clone journey pass, but the complete enabled personal journey remains unproven because the configured personal database has six active accounts while the authorized validation scope covered four and only four have currency evidence.
- risk-p1-local-backup-recovery [high/low]: End-to-end personal recovery/activation is not complete, although verified non-destructive backup and disposable restore tooling exists.
- risk-p1-personal-account-scope-mismatch [high/high]: The configured Atlas-owned personal SQLite database currently contains six active accounts, while the authorized Wave 2C assumptions and prior clone evidence cover four; only four active accounts have currency evidence, so personal mutation must stop until the active-account scope is reconciled.

## Recently completed

- work-personal-use-activation-readiness-wave-1a: Implement personal-use readiness and synthetic acceptance — commit 9847f1a, PR not recorded
- work-wave-2a-authoritative-account-currency: Implement Wave 2A authoritative account-currency evidence — commit a438df9233cb197827a5affda0c24ee4d7ec0a97, PR not recorded
- work-wave-2b-local-backup-recovery: Implement WAL-safe local backup and recovery — commit 423f87a, PR not recorded
- work-wave-2c-personal-activation-acceptance: Execute backup-first personal activation and restart acceptance — commit e877247, PR not recorded
- work-wave-2c-authoritative-balance-amount: Establish exact-cent legacy balance authority — commit 50d7d198de5b28d0d37e9aa596c8e2d90b27452f, PR 58

## Next bounded task

- work-wave-2c-personal-scope-reconciliation: Reconcile the configured personal database active-account scope with the authorized four-account validation scope without writing personal financial state; then obtain explicit bounded authorization before rerunning backup-first Wave 2C activation.

Do not begin the next task automatically.
