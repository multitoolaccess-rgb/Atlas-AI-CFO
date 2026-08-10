# Atlas Current Handoff

> Generated from canonical project status. Verify live Git state before editing.

## Current objective

- Phase: phase-4 — Decision journal
- Phase status: in_progress
- Overall status: in_progress
- Objective: Phase 4 Slice 1 is in progress: implement the owner-scoped, append-only decision-history substrate for alternatives, rationale, audit events, correction recovery, and bounded default-off APIs. Phase 3 remains complete. External multi-user rollout remains blocked by retention/user-deletion policy and authoritative currency policy.
- Phase exit criteria: 0/1 complete
- Tracker updated: 2026-08-10T07:55:35Z

## Active work

- work-p4-decision-history-substrate: Phase 4 Slice 1 decision-history substrate [blocked/high]
  - Objective: Implement append-only, owner-scoped decision history, alternatives, audit, correction recovery, and bounded API behind a default-off rollout flag.
  - Branch: work-p4-decision-history-substrate
  - Paths: services/rules-service/app/models,services/rules-service/app/forecasts,services/rules-service/app/routes,services/rules-service/alembic/versions,services/rules-service/tests

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

- work-p2-dashboard-auth-error-classification: Dashboard/auth error classification correction — commit 1aaaeb9, PR 26
- work-p2-merchant-rule-priority-correction: Merchant-rule priority omission correction — commit 2a3ac51, PR 27
- work-p2-repository-health-stabilization: Phase 2 repository-health stabilization — commit c62b1ac9f34ade417aa4a0b50e4c6c4d3b956278, PR 28
- work-p3-outcome-evidence-reference-replacement: Phase 3 Slice 1: Privacy-safe outcome-evaluation substrate (evidence reference replacement) — commit 8955e40a74926d76bed7cd93f5fb31a8508d40c9, PR 32
- work-p3-recommendation-linkage-and-approvals: Phase 3: Recommendation linkage and approvals — commit 86ea65fc8c27224ec209249218fb6ccbe74b4178, PR 33

## Next bounded task

- ec-p4-decision-history: Active authorized work is work-p4-decision-history-substrate. It is the first bounded contribution to ec-p4-decision-history; do not mark the criterion complete until the planned UI, accessibility, end-to-end, and final certification evidence also exist.

Do not begin the next task automatically.
