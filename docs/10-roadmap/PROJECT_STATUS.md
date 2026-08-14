# Atlas Project Status

> Generated from `PROJECT_STATUS.json`; regenerate with `python3 scripts/atlas_project_status.py render`.

- Current phase: **phase-6 — Scenario Lab** (in_progress)
- Overall status: **in_progress**
- Current objective: Phase 6 remains in progress after completion of Slice 1; implement the newly authorized cohesive Atlas Visual System v2 while preserving all financial semantics and application behavior.
- Last updated: 2026-08-14T18:21:42Z

## Active work
- work-ui-information-architecture-step-3: Activate Wealth information architecture migration (in_progress, high)

## Blockers
- {'description': 'External multi-user production enablement is BLOCKED until an approved retention and user-deletion policy exists for immutable forecast history.', 'id': 'external-multi-user-retention-deletion-blocker', 'owner': 'product-security', 'related': 'ADR-006, issue #3, PR #4', 'status': 'open'}

## Phase progress
- phase-0 — Projection foundation and Atlas baseline: complete (4/4 exit criteria)
- phase-1 — Forecast persistence: complete (5/5 exit criteria)
- phase-2 — Forecast UI migration: complete (1/1 exit criteria)
- phase-3 — Goal-linked recommendations: complete (1/1 exit criteria)
- phase-4 — Decision journal: complete (1/1 exit criteria)
- phase-5 — Market Intelligence Brief: complete (1/1 exit criteria)
- phase-6 — Scenario Lab: in_progress (1/1 exit criteria)

## Current risks
- risk-frontend-lint-debt [medium/high, open]: Repository-wide frontend lint debt remains outside Phase 0 scope.
- risk-monte-carlo-deferred [medium/medium, open]: Monte Carlo probability model is intentionally deferred.
- risk-transitional-tenancy [high/medium, open]: User-scoped tenancy remains transitional.
- risk-legacy-product-names [low/high, open]: Legacy Finance Copilot, WealthIQ, CashFlix, and Finlynq names remain.
- risk-fixture-compatibility-names [low/medium, open]: Synthetic fixture directories retain compatibility-oriented names.
- risk-service-dependency-separation [high/high, mitigated]: Rules Service and Finlynq require separate FastAPI-pinned environments.
- risk-p1-legacy-goal-float [high/medium, open]: The existing Goal.target_amount Float can lose source precision before Phase 1 snapshot normalization.
- risk-p1-dialect-parity [high/medium, open]: SQLite and PostgreSQL differ in exact numeric storage and concurrency semantics for immutable forecast versions.
- risk-p1-retention-rollout-gate [high/medium, open]: No approved retention or user-deletion policy exists for immutable forecast history.
- risk-p1-trusted-generation-boundary [high/medium, open]: An untrusted generation request could forge canonical financial state or provenance if the trusted adapter boundary regresses.
- risk-p1-account-currency-authority [high/high, open]: Finlynq active account balances have no authoritative currency attribute; a user preference/default cannot prove balances are USD for atlas-projection-state/v1.
- risk-p1-migration-downgrade-patched [medium/low, resolved]: Alembic 1.13.x's ApplyBatchImpl.drop_index rejects the deprecated if_exists keyword argument; the Phase 1 final cert matrix surfaced this as a full upgrade -> downgrade base failure on the e9f0a1b2c3d4 migration.

## Recently completed work
- work-analyst-coverage-clarity: Clarify partial analyst coverage states — commit 00cc0879af7bf9dfd396e64e47755d7be9a28a7f, PR 45
- work-holdings-type-fix: Fix Fidelity import type mislabeling and repair affected portfolio data — commit 2603d5c9af7bf9dfd396e64e47755d7be9a28a7f, PR 46
- work-market-intelligence-v2: Market Intelligence v2 (post-certification enhancement): reliable per-holding evidence, market pulse, and command-center UI — commit 4f27b6d058f26c8d89d518cc5a25258fc6d0ffa9, PR 47
- work-ui-information-architecture-step-1: Information architecture migration Step 1 foundations — commit d7e5cde, PR 48
- work-ui-information-architecture-step-2: Activate Money information architecture migration — commit 54974b8, PR 49

## Evidence
- c0f5287: Atlas baseline initialization from the validated Finance Copilot foundation
- 8baa1c2: Service environment isolation
- d001e64: Merged synthetic fixture restoration #1
- b987147: Phase 1 immutable forecast persistence planning #4
- 6e485ea: Resolved Phase 1 canonical-envelope, validation, and retention planning decisions #4
- a818665: Enforced the trusted adapter-only forecast generation boundary #4
- d85255f: Added immutable forecast persistence models and additive migration from Q5h1i2j3k4l5
- 40517d2: Hardened forecast persistence UUID, SHA-256, and required-version database constraints #8
- 57b8cb5: Prevented rollback from deleting persisted forecast identities and restricted version labels to printable ASCII #8
- a44e15d: Hardened canonical Decimal bounds and sanitized contract validation errors #6
- f91de80: Detached raw validation exception state and bounded caller-facing contract-error locations #6
- 734d35e: Made dashboard date-only ranges inclusive through a half-open next-day bound #7
- 694ec81: Restored bounded open-ended dashboard date ranges while retaining the half-open upper bound #7
- e2ebbb2: Rejected dashboard date ranges whose exclusive next-day bound is unrepresentable #7
- 8b576830edb069f009550b6891750c91e0e8b0bf:  13
- 175ac8c6da24a81125741ba336a56fc8cba3f777: Bounded mapper-only correction on top of mapper rewrite (a6adb17). Fix A: _assumption_goal_pairs enforces the Phase 0 XOR invariant (target_amount required + exactly one of (horizon_years, target_date)) with `_NULL_SENTINEL` now documented as a deliberate bounded wire placeholder rather than a missing field — both-None and both-present reject via sanitized ForecastMapperError. Fix B: _coerce_drivers_data_as_of accepts ONLY YYYY-MM-DD (10-char) OR RFC 3339 (T-separator + Z-suffix); timezone offsets, space separators, garbage, empty, non-string, and >64-char inputs reject with sanitized ForecastMapperError. Mapper remains route-free and adapter-free (AST isolation test still passes). Route WIP preserved untracked in stash@{0} (message: wip-route-handler-pre-pr14-merge) for the next bounded handler PR. 14
- feeb14171cfed45c8a575627a1759d5a414e5e51: PR #20 cycle-1 cert corrections: Class A observability + Class B dashboard half-open interval + new regression tests + docs/10-roadmap/phase-1-evidence/alembic-round-trip-evidence.md
- efe972d41a8290647280405b9b09ab938673f23e: PR #20 cycle-5 mirror: function-scoped autouse _observability_isolation fixture in test_observability.py + identical mirror in test_shadow_validate.py
- 02bbd58f62e32c13362680c9a31dc9710c132d1c: PR #20 squash on main with audit-clear amended subject: 'fix(phase1): PR #20 cert rollup (cycle-1 corrections + cycle-5 scoped test)'
- 1032ec9998b96046030b700e3f84a73b3797a776: PR #20-followup migration downgrade corrective: drops deprecated if_exists=True kwarg from batch_op.drop_index(...) inside downgrade() of services/rules-service/alembic/versions/e9f0a1b2c3d4_add_family_members_and_backfill.py
- 08f6f811da7c325da8a3d60adae9f2d9c2d210e8: Final certified main SHA: 'fix(db): correct Phase 1 finlynq-compatible alembic downgrade path' (annotated tag phase-1-complete resolves to this SHA on remote)
- 642b3d488af16cd737e28ceca63c576a1238d2e1: Phase 2 Slice 1 backend cohesive PR -- four bounded commits (commit-1 schemas, commit-2 models+migration+parity, commit-3 service+engine+repo, commit-4 routes+flags+integration) accepted by user across the slice. PR opened as cohesive package; code-reviewer-minimax-m3 returned VERDICT: GREEN against PR #21 head 642b3d4 with full 13-item plan section 3/4/5/8 matrix (determinism, append-only journal, ownership-before-disclosure, default-off flags, currency fail-closed, Decimal preservation, ETags/cursors, strict bodies, real app wiring, privacy, schema_version convention, RecommendationNotFound envelope, test_decision_journal_parity): zero HIGH findings, no residual LOW items. status CI gate PASSED in 9s. Branch squash-merged to main as 3ce7fe5706530d0ec68e743fff0882c76b3434cf; local + remote branches cleaned; local main fast-forward synced. 21
- 8955e40a74926d76bed7cd93f5fb31a8508d40c9: Phase 3 Slice 1: replace the unsafe String(512) authoritative_evidence_reference from closed PR #30 with a privacy-safe bounded evidence-source contract — allowlisted evidence_source_kind (forecast_projection / account_balance_delta / transaction_pattern) + server-derived hash-only evidence_reference_hash (64-char lowercase SHA-256). Raw evidence references are never accepted, persisted, logged, echoed, or exposed in errors. Append-only outcome_evaluations table + migration U9a1b2c3d4e5, lifecycle evidence contract, idempotent replay, sanitized OutcomeConflictError, ownership-before-existence, UNIQUE-collision race recovery, row-count-guarded downgrade. Squash-merged to main; heavy CI skipped (no-UI backend slice). 32
- Test test-p0-rules: Rules Service — 579 passed, 10 skipped, 1 xfailed
- Test test-p0-finlynq: Finlynq — 93 passed
- Test test-p0-frontend: Frontend — 496 passed
- Test test-p0-typescript: TypeScript check — passed
- Test test-p1-planning-status: Phase 1 planning governance — 5 passed; status, deterministic render, and trusted generation-boundary documentation checks passed
- Test test-p1-slice-d-routes: Slice D focused + broader regression on isolated SQLite DB — PASS
- Test test-p1-slice-d-post-mapper-sub-pr: Phase 1 Slice D-post mapper sub-PR (PR #14 commit 175ac8c) on isolated SQLite DB — 37/37 test_forecast_mapper.py + 226/226 broader regression + APPROVE_FOR_MERGE from fresh independent code-reviewer-minimax-m3
- Test test-p1-cert: Phase 1 final certification matrix on clean main @ 08f6f811 — Rules Service 930 passed, 10 skipped, 1 xfailed, 726 warnings in 11.19s; Finlynq 106 passed, 38 warnings in 1.16s; cross-service (repo-root tests/) 29 passed in 6.42s; tracker (tests/test_atlas_project_status.py) 9 passed in 0.97s; privacy + observability (test_observability.py + test_shadow_validate.py) 74 passed in 0.10s; UI 'npm run typecheck' (tsc --noEmit) exit 0; UI 'npm test --silent -- --run' (vitest non-watch) exit 0; alembic upgrade head -> current -> downgrade base -> re-upgrade head clean on disposable SQLite; alembic heads single S7a1b2c3d4e5; test_forecast_migration.py 7 passed in 0.42s

## Next bounded task
- work-ui-information-architecture-step-3: Step 3 - migrate Wealth atomically: Wealth Overview, Assets, Debts, Universe, Portfolio, Goals, and compatibility redirects.

Do not begin the next phase or task automatically.
