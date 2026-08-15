# Atlas Current Handoff

> Generated from canonical project status. Verify live Git state before editing.

## Current objective

- Phase: phase-6 — Scenario Lab
- Phase status: in_progress
- Overall status: in_progress
- Objective: Phase 6 remains in progress after completion of Slice 1; implement the newly authorized cohesive Atlas Visual System v2 while preserving all financial semantics and application behavior.
- Phase exit criteria: 1/1 complete
- Tracker updated: 2026-08-15T05:38:23Z

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
- risk-p1-account-currency-authority [high/high]: Finlynq active account balances have no authoritative currency attribute; a user preference/default cannot prove balances are USD for atlas-projection-state/v1.

## Recently completed

- work-ui-information-architecture-step-2: Activate Money information architecture migration — commit 54974b8, PR 49
- work-ui-information-architecture-step-3: Activate Wealth information architecture migration — commit a8e1d5b009175a27c91a521f2a156d0c4179c094, PR 50
- work-ui-information-architecture-step-4: Activate Intelligence information architecture migration — commit dfd07e60a5b8512ae3c8e5a8bb72ab1a171862f0, PR 51
- work-ui-information-architecture-step-5: Activate System information architecture migration — commit 5f79932f69e44c255793dde817b6d4a84b3764e3, PR 53
- work-p6-s2-scenario-lab-ui: Phase 6 Slice 2 Scenario Lab UI — commit 0e8516a, PR not recorded

## Next bounded task

- work-p6-s2-scenario-lab-certification: Run a separate clean-main Phase 6 certification matrix for Scenario Lab Slice 2 only when phase certification is authorized; do not add a completion tag without all documented exit evidence.

Do not begin the next task automatically.
