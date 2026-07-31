# Completed Atlas Phases

This append-only record is updated only by `complete-phase` after all exit
criteria are complete.

## Phase 0 — Projection foundation and safe Atlas baseline

- Completion date: 2026-07-26
- Final commit: `d001e646c6e2cf0b91b5b6866d047ed1271f6c70`
- Merged PRs: #1 synthetic financial fixtures and clean-runner CI
- Test evidence: hosted CI green; Rules Service `579 passed, 10 skipped, 1
  xfailed`; Finlynq `93 passed`; frontend `496 passed`; TypeScript check
  passed.
- ADRs: ADR-005
- Known limitations: repository-wide frontend lint debt, deferred Monte Carlo
  model, transitional tenancy, and legacy product terminology remain tracked.
- Authorized next phase: Phase 1 planning only after explicit review.

## Phase 1 — Forecast persistence

- Completion date: 2026-07-30
- Final commit: `08f6f811da7c325da8a3d60adae9f2d9c2d210e8`
- Annotated tag: `phase-1-complete` pinned to the final commit SHA above.
- Audit trace (each commit below is verifiable on `main`):
  - `feeb14171cfed45c8a575627a1759d5a414e5e51` -- PR #20 cycle-1 cert corrections (Class A observability + Class B dashboard half-open interval + new regression tests + `docs/10-roadmap/phase-1-evidence/alembic-round-trip-evidence.md`).
  - `efe972d41a8290647280405b9b09ab938673f23e` -- PR #20 cycle-5 mirror function-scoped autouse `_observability_isolation` fixture in `services/rules-service/tests/test_observability.py` plus an identical mirror in `services/rules-service/tests/test_shadow_validate.py`.
  - `02bbd58f62e32c13362680c9a31dc9710c132d1c` -- PR #20 squash on `main` with audit-clear amended subject ("fix(phase1): PR #20 cert rollup (cycle-1 corrections + cycle-5 scoped test)").
  - `1032ec9998b96046030b700e3f84a73b3797a776` -- PR #20-followup migration downgrade corrective: drops the deprecated `if_exists=True` kwarg from `batch_op.drop_index(...)` inside `downgrade()` of `services/rules-service/alembic/versions/e9f0a1b2c3d4_add_family_members_and_backfill.py`.
  - `08f6f811da7c325da8a3d60adae9f2d9c2d210e8` -- final certified `main` SHA: the corrective-PR squash-merge onto `main` ("fix(db): correct Phase 1 finlynq-compatible alembic downgrade path").
- Test evidence (final certification matrix on clean `main`):
  - Rules Service: `930 passed, 10 skipped, 1 xfailed, 726 warnings in 11.19s`.
  - Finlynq: `106 passed, 38 warnings in 1.16s`.
  - Cross-service (repo-root `tests/`): `29 passed in 6.42s`.
  - Tracker (`tests/test_atlas_project_status.py`): `9 passed in 0.97s`.
  - Privacy + observability tests (`test_observability.py` + `test_shadow_validate.py`): `74 passed in 0.10s`.
  - UI TypeScript via canonical `cd ui && npm run typecheck` (executes `tsc --noEmit`): exit 0, 0 errors.
  - UI Vitest via canonical `cd ui && npm test --silent -- --run`: exit 0.
  - Migration round-trip on disposable SQLite (`alembic upgrade head -> current -> downgrade base -> upgrade head`, with single head `S7a1b2c3d4e5` verified via `alembic heads`): CLEAN.
  - `services/rules-service/tests/test_forecast_migration.py`: `7 passed in 0.42s`.
- ADRs: ADR-006 (immutable forecast persistence).
- Known limitations (preserved as open risks in `RISK_REGISTER.md`):
  - Forecast persistence gate (`atlas_forecast_persistence_enabled`) and read API gate (`atlas_forecast_read_api_enabled`) remain default-off at the application layer; default-off behavior is exercised in the full Rules Service suite per the cycle-1 cert corrections.
  - Real-account currency confirmation (`risk-p1-account-currency-authority`) NOT applied to real accounts.
- Authorized next phase: BLOCKED. External multi-user production enablement is blocked until an approved retention and user-deletion policy exists for immutable forecast history (`risk-p1-retention-rollout-gate` remains `open`). No Phase 2 work begins per the user mandate.
