# Atlas Project Status

> Generated from `PROJECT_STATUS.json`; regenerate with `python3 scripts/atlas_project_status.py render`.

- Current phase: **phase-1 — Forecast persistence** (complete)
- Overall status: **complete**
- Current objective: Phase 1 certified at commit 08f6f811da7c325da8a3d60adae9f2d9c2d210e8 (annotated tag phase-1-complete resolves on remote to certified main SHA). External multi-user production enablement is BLOCKED pending retention and user-deletion policy approval. No Phase 2 work begins per the user mandate.
- Last updated: 2026-07-30T22:55:00Z

## Active work
- None

## Blockers
- {'id': 'external-multi-user-retention-deletion-blocker', 'description': 'External multi-user production enablement is BLOCKED until an approved retention and user-deletion policy exists for immutable forecast history.', 'related': 'ADR-006, issue #3, PR #4', 'status': 'open', 'owner': 'product-security'}

## Phase progress
- phase-0 — Projection foundation and Atlas baseline: complete (4/4 exit criteria)
- phase-1 — Forecast persistence: complete (5/5 exit criteria)
- phase-2 — Forecast UI migration: not_started (0/1 exit criteria)
- phase-3 — Goal-linked recommendations: not_started (0/1 exit criteria)
- phase-4 — Decision journal: not_started (0/1 exit criteria)

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
- work-p1-forecast-generation-service: Implement trusted forecast generation application service — commit a44aeaf4, PR 11
- work-p1-versioned-schemas: Phase 1 Slice C: Decimal-safe versioned API schemas — commit 17632b5, PR 12
- work-p1-versioned-read-routes: Phase 1 Slice D: Authenticated versioned read routes — commit 8b576830edb069f009550b6891750c91e0e8b0bf, PR 13
- work-p1-cert-rollup: Phase 1 PR #20 cert rollup (cycle-1 corrections + cycle-5 scoped test) — commit 02bbd58f62e32c13362680c9a31dc9710c132d1c, PR n/a
- work-p1-final-cert: Phase 1 final cert + migration downgrade corrective squash-merge to main — commit 08f6f811da7c325da8a3d60adae9f2d9c2d210e8, PR n/a

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
- Test test-p0-rules: Rules Service — 579 passed, 10 skipped, 1 xfailed
- Test test-p0-finlynq: Finlynq — 93 passed
- Test test-p0-frontend: Frontend — 496 passed
- Test test-p0-typescript: TypeScript check — passed
- Test test-p1-planning-status: Phase 1 planning governance — 5 passed; status, deterministic render, and trusted generation-boundary documentation checks passed
- Test test-p1-slice-d-routes: Slice D focused + broader regression on isolated SQLite DB — PASS
- Test test-p1-slice-d-post-mapper-sub-pr: Phase 1 Slice D-post mapper sub-PR (PR #14 commit 175ac8c) on isolated SQLite DB — 37/37 test_forecast_mapper.py + 226/226 broader regression + APPROVE_FOR_MERGE from fresh independent code-reviewer-minimax-m3
- Test test-p1-cert: Phase 1 final certification matrix on clean main @ 08f6f811 — Rules Service 930 passed, 10 skipped, 1 xfailed, 726 warnings in 11.19s; Finlynq 106 passed, 38 warnings in 1.16s; cross-service (repo-root tests/) 29 passed in 6.42s; tracker (tests/test_atlas_project_status.py) 9 passed in 0.97s; privacy + observability (test_observability.py + test_shadow_validate.py) 74 passed in 0.10s; UI 'npm run typecheck' (tsc --noEmit) exit 0; UI 'npm test --silent -- --run' (vitest non-watch) exit 0; alembic upgrade head -> current -> downgrade base -> re-upgrade head clean on disposable SQLite; alembic heads single S7a1b2c3d4e5; test_forecast_migration.py 7 passed in 0.42s

## Next bounded task
- work-p1-flags-observability-shadow-validation: Phase 1 Slice E: Flags, observability, and bounded shadow validation. Blocked until Slice D-post (mapper + handler PRs) merges AND retention / user-deletion policy is approved.

Do not begin the next phase or task automatically.
