# Atlas Current Handoff

> Generated from canonical project status. Verify live Git state before editing.

## Current objective

- Phase: phase-6 — Scenario Lab
- Phase status: in_progress
- Overall status: in_progress
- Objective: Phase 6 remains in progress after completion of Slice 2 Scenario Lab UI; preserve server-owned financial authority and prepare the separate clean-main certification boundary.
- Phase exit criteria: 1/1 complete
- Tracker updated: 2026-08-15T09:45:00Z

## Active work

- work-p6-clean-main-certification: Clean-main Phase 6 certification [in_progress/medium]
  - Objective: Reconcile the documented Phase 6 clean-main browser blockers, then rerun the complete certification matrix and create the completion tag only after every exit criterion passes.
  - Branch: main
  - Paths: ui, docs/10-roadmap

## Blockers

- external-multi-user-retention-deletion-blocker [open]: External multi-user production enablement is BLOCKED until an approved retention and user-deletion policy exists for immutable forecast history.
- phase-6-clean-main-certification-blocker [open]: Local clean-main Phase 6 certification passes after PR #57: Rules Service 1,298 passed/10 skipped/1 expected xfail, Finlynq 106 passed, cross-service 33 passed, frontend 630 passed, TypeScript/lint/build passed, canonical Playwright 108 passed/1 skipped, and affected Scenario Lab journeys passed. The required hosted manual certification workflow cannot start because GitHub reports failed account payments or an exhausted spending limit; phase-6-complete remains prohibited until hosted certification is available and green.
- github-actions-certification-billing-blocker [open]: Hosted clean-main certification cannot start because GitHub Actions reports failed account payments or an exhausted spending limit before any workflow step runs.

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

- work-p6-clean-main-certification-remediation: Restore hosted clean-main certification availability, then rerun the required hosted Phase 6 workflow and create phase-6-complete only if every documented exit criterion passes; local certification evidence is recorded and no Phase 7 work may begin.

Do not begin the next task automatically.
