# Atlas Current Handoff

> Generated from canonical project status. Verify live Git state before editing.

## Current objective

- Phase: phase-6 — Scenario Lab
- Phase status: in_progress
- Overall status: in_progress
- Objective: Phase 6 remains in progress after completion of Slice 1; implement the newly authorized cohesive Atlas Visual System v2 while preserving all financial semantics and application behavior.
- Phase exit criteria: 1/1 complete
- Tracker updated: 2026-08-14T18:21:12Z

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

- work-analyst-coverage-clarity: Clarify partial analyst coverage states — commit 00cc0879af7bf9dfd396e64e47755d7be9a28a7f, PR 45
- work-holdings-type-fix: Fix Fidelity import type mislabeling and repair affected portfolio data — commit 2603d5c9af7bf9dfd396e64e47755d7be9a28a7f, PR 46
- work-market-intelligence-v2: Market Intelligence v2 (post-certification enhancement): reliable per-holding evidence, market pulse, and command-center UI — commit 4f27b6d058f26c8d89d518cc5a25258fc6d0ffa9, PR 47
- work-ui-information-architecture-step-1: Information architecture migration Step 1 foundations — commit d7e5cde, PR 48
- work-ui-information-architecture-step-2: Activate Money information architecture migration — commit 54974b8, PR 49

## Next bounded task

- work-ui-information-architecture-step-3: Step 3 - migrate Wealth atomically: Wealth Overview, Assets, Debts, Universe, Portfolio, Goals, and compatibility redirects.

Do not begin the next task automatically.
