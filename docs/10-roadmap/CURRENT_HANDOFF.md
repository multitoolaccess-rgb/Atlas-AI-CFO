# Atlas Current Handoff

> Generated from canonical project status. Verify live Git state before editing.

## Current objective

- Phase: phase-4 — Decision journal
- Phase status: in_progress
- Overall status: in_progress
- Objective: Phase 4 Slice 1 COMPLETE: PR #34 squash-merged at 13da914, providing owner-scoped append-only decision history, bounded alternatives and rationale, audited outcome linkage, correction recovery, default-off APIs, and cross-dialect safeguards. Phase 4 Slice 2 UI/accessibility/end-to-end integration is the next bounded task and has not started. External multi-user rollout remains blocked by retention/user-deletion policy and authoritative currency policy.
- Phase exit criteria: 0/1 complete
- Tracker updated: 2026-08-10T15:24:07Z

## Active work

- work-p4-decision-history-ui: Phase 4 Slice 2 decision-history UI [in_progress/high]
  - Objective: Integrate the default-off owner-scoped decision-history API into the existing goals recommendation UI with accessible, privacy-safe chronological history and complete mocked browser coverage.
  - Branch: codex/phase-4-decision-history-ui
  - Paths: ui/app/goals/page.tsx, ui/components, ui/lib, ui/__tests__

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

- work-p2-merchant-rule-priority-correction: Merchant-rule priority omission correction — commit 2a3ac51, PR 27
- work-p2-repository-health-stabilization: Phase 2 repository-health stabilization — commit c62b1ac9f34ade417aa4a0b50e4c6c4d3b956278, PR 28
- work-p3-outcome-evidence-reference-replacement: Phase 3 Slice 1: Privacy-safe outcome-evaluation substrate (evidence reference replacement) — commit 8955e40a74926d76bed7cd93f5fb31a8508d40c9, PR 32
- work-p3-recommendation-linkage-and-approvals: Phase 3: Recommendation linkage and approvals — commit 86ea65fc8c27224ec209249218fb6ccbe74b4178, PR 33
- work-p4-decision-history-substrate: Phase 4 Slice 1 decision-history substrate — commit 13da914cf1db78d02219eb72c9f4f5b0aca9e86f, PR 34

## Next bounded task

- work-p4-decision-history-ui: Phase 4 Slice 2: integrate the merged owner-scoped decision-history API into the existing goals recommendation surface with typed client coverage, accessible chronological history and correction flow, privacy-safe outcome lifecycle display, and mocked end-to-end coverage. Do not begin without explicit authorization.

Do not begin the next task automatically.
