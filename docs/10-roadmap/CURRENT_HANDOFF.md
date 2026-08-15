# Atlas Current Handoff

> Generated from canonical project status. Verify live Git state before editing.

## Current objective

- Phase: phase-6 — Scenario Lab
- Phase status: in_progress
- Overall status: in_progress
- Objective: Phase 6 remains in progress after completion of Slice 2 Scenario Lab UI; preserve server-owned financial authority and prepare the separate clean-main certification boundary.
- Phase exit criteria: 1/1 complete
- Tracker updated: 2026-08-15T06:22:51Z

## Active work

- work-p6-clean-main-certification: Clean-main Phase 6 certification [blocked/medium]
  - Objective: Run the documented full Phase 6 certification matrix from clean main and create the completion tag only after every exit criterion passes.
  - Branch: main
  - Paths: docs/10-roadmap

## Blockers

- external-multi-user-retention-deletion-blocker [open]: External multi-user production enablement is BLOCKED until an approved retention and user-deletion policy exists for immutable forecast history.
- phase-6-clean-main-certification-blocker [open]: Phase 6 clean-main certification is blocked by canonical Playwright failures on baseline IA/default-off behavior; local bash scripts/test-e2e.sh recorded 93 passed, 14 failed, 1 skipped, and hosted manual heavy run 31868205933 failed after 4/5 steps passed with Playwright timing out at 900 seconds. Do not create phase-6-complete until stale pre-IA browser expectations and expected default-off 503 console handling are separately reconciled without weakening authority or default-off criteria.

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
- work-p6-s2-scenario-lab-ui: Phase 6 Slice 2 Scenario Lab UI — commit 85761ce08d2d8761aa7c71e8ae00887e4b59e16a, PR 55

## Next bounded task

- work-p6-clean-main-certification-remediation: Reconcile the documented clean-main Phase 6 certification blockers (stale pre-IA browser expectations and expected default-off 503 console handling), rerun the complete certification matrix, and create phase-6-complete only if every documented exit criterion passes.

Do not begin the next task automatically.
