# Atlas Current Handoff

> Generated from canonical project status. Verify live Git state before editing.

## Current objective

- Phase: phase-6 — Scenario Lab
- Phase status: complete
- Overall status: complete
- Objective: Phase 6 is certified; Wave 2B is complete and Wave 2C remains blocked on projection baseline/configuration and local service lifecycle acceptance. Preserve server-owned financial authority and do not begin Wave 3 or Phase 7.
- Phase exit criteria: 2/2 complete
- Tracker updated: 2026-08-15T19:18:14Z

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
- risk-p1-account-currency-authority [high/medium]: Active account balances now have current operator-confirmed USD evidence after backup-first authorization, but the complete enabled personal forecast journey remains unproven because projection configuration/baseline is absent.
- risk-p1-local-backup-recovery [high/low]: End-to-end personal recovery/activation is not complete, although verified non-destructive backup and disposable restore tooling exists.

## Recently completed

- work-p6-clean-main-certification: Clean-main Phase 6 certification — commit 9c9b554, PR not recorded
- work-personal-use-activation-readiness-wave-1a: Implement personal-use readiness and synthetic acceptance — commit 9847f1a, PR not recorded
- work-wave-2a-authoritative-account-currency: Implement Wave 2A authoritative account-currency evidence — commit a438df9233cb197827a5affda0c24ee4d7ec0a97, PR not recorded
- work-wave-2b-local-backup-recovery: Implement WAL-safe local backup and recovery — commit 423f87a, PR not recorded
- work-wave-2c-personal-activation-acceptance: Execute backup-first personal activation and restart acceptance — commit d769870ed98212d92b06e92424e8b6fcc4ccf7ea, PR not recorded

## Next bounded task

- work-wave-2c-activation-recovery: Repair and prove the disposable Wave 2C projection baseline/configuration and local service lifecycle, then rerun approved personal readiness acceptance; do not begin Wave 3 or Phase 7.

Do not begin the next task automatically.
