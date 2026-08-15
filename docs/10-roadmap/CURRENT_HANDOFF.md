# Atlas Current Handoff

> Generated from canonical project status. Verify live Git state before editing.

## Current objective

- Phase: phase-6 — Scenario Lab
- Phase status: complete
- Overall status: complete
- Objective: Phases 0–6 are certified and the Personal-Use Acceptance and System Health Audit is complete; preserve server-owned financial authority and do not begin Phase 7.
- Phase exit criteria: 2/2 complete
- Tracker updated: 2026-08-15T18:46:54Z

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
- risk-p1-account-currency-authority [high/high]: Active account balances still require explicit source-backed currency evidence; Wave 2A now enforces the lifecycle, but the personal database has not been inspected and complete current evidence remains unproven.
- risk-p1-local-backup-recovery [high/medium]: No supported non-destructive backup, WAL-safe restore, pre-restore safety copy, or migration-compatible recovery drill exists for Atlas local SQLite data.

## Recently completed

- work-ui-information-architecture-step-5: Activate System information architecture migration — commit 5f79932f69e44c255793dde817b6d4a84b3764e3, PR 53
- work-p6-s2-scenario-lab-ui: Phase 6 Slice 2 Scenario Lab UI — commit 85761ce08d2d8761aa7c71e8ae00887e4b59e16a, PR 55
- work-p6-clean-main-certification: Clean-main Phase 6 certification — commit 9c9b554, PR not recorded
- work-personal-use-activation-readiness-wave-1a: Implement personal-use readiness and synthetic acceptance — commit 9847f1a, PR not recorded
- work-wave-2a-authoritative-account-currency: Implement Wave 2A authoritative account-currency evidence — commit a438df9233cb197827a5affda0c24ee4d7ec0a97, PR not recorded

## Next bounded task

- work-wave-2b-local-backup-recovery: Implement WAL-safe non-destructive local backup and recovery only; do not access personal data or begin Wave 2C or Phase 7.

Do not begin the next task automatically.
