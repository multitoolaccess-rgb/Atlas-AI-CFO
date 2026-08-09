# Atlas Current Handoff

> Generated from canonical project status. Verify live Git state before editing.

## Current objective

- Phase: phase-3 — Goal-linked recommendations
- Phase status: in_progress
- Overall status: in_progress
- Objective: Phase 3 Slice 1 OUTCOME-EVALUATION SUBSTRATE COMPLETE. PR #32 (head e4ab0bd) squash-merged to main at 8955e40 with an independent code-reviewer review of the PR head (zero CRITICAL/HIGH findings; two MEDIUM items — privacy-contract docstring scope overclaim and race-recovery fallback for cross-row UNIQUE collisions — both addressed in the review-fix commit e4ab0bd, with a regression test) and status + cheap CI checks green on the fix commit (heavy correctly skipped: no-UI backend slice). The substrate delivers: immutable append-only outcome_evaluations ORM + migration (U9a1b2c3d4e5) with SQLite + PostgreSQL UPDATE/DELETE triggers, allowlisted evidence_source_kind enum (forecast_projection / account_balance_delta / transaction_pattern), server-derived hash-only evidence_reference_hash (64-char lowercase SHA-256) so no raw URLs, filenames, account IDs, or transaction identifiers are ever accepted from end-user requests, persisted, logged, echoed, or exposed in errors, lifecycle states (pending / not_yet_measurable / measured) with the measured evidence contract enforced by CHECK constraints, deterministic PK + (user, recommendation, decision, idempotency-key) idempotent replay, sanitized OutcomeConflictError carrying only the current etag, ownership-before-existence verification, UNIQUE-collision race recovery with cross-row idempotency-key fallback, and a row-count-guarded migration downgrade that refuses to destroy immutable outcome history. Phase 3 exit criterion ec-p3-recommendation-contract remains open: recommendations still need the goals/evidence/risks/confidence/approvals linkage. External multi-user production enablement remains BLOCKED pending retention and user-deletion policy (risk-p1-retention-rollout-gate open). Currency uncertainty continues to fail closed (risk-p1-account-currency-authority open). The next bounded task continues Phase 3 goal-linked recommendations.
- Phase exit criteria: 0/1 complete
- Tracker updated: 2026-08-03T05:07:33Z

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

- work-p2-decision-journal-substrate: Phase 2 Slice 1: Backend deterministic recommendation + append-only decision journal substrate — commit 3ce7fe5706530d0ec68e743fff0882c76b3434cf, PR 21
- work-p2-dashboard-auth-error-classification: Dashboard/auth error classification correction — commit 1aaaeb9, PR 26
- work-p2-merchant-rule-priority-correction: Merchant-rule priority omission correction — commit 2a3ac51, PR 27
- work-p2-repository-health-stabilization: Phase 2 repository-health stabilization — commit c62b1ac9f34ade417aa4a0b50e4c6c4d3b956278, PR 28
- work-p3-outcome-evidence-reference-replacement: Phase 3 Slice 1: Privacy-safe outcome-evaluation substrate (evidence reference replacement) — commit 8955e40a74926d76bed7cd93f5fb31a8508d40c9, PR 32

## Next bounded task

- work-p3-recommendation-linkage-and-approvals: Continue Phase 3 goal-linked recommendations. Slice 1 (privacy-safe outcome-evaluation substrate) is complete and merged via PR #32 at 8955e40. The next bounded slice closes the remaining ec-p3-recommendation-contract scope: wire recommendations to goals, evidence, risks, confidence, and approvals — extend the Phase 2 deterministic recommendation + append-only decision-journal substrate (PR #21) so accepted decisions surface their supporting goal/evidence/risk/confidence linkage and the outcome evaluations recorded by the Phase 3 Slice 1 substrate. Do not begin until the user explicitly authorizes the next slice. External multi-user rollout remains blocked by retention/user-deletion policy and authoritative currency policy.

Do not begin the next task automatically.
