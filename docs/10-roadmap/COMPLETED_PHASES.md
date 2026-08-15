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

## phase-2 — Forecast UI migration

- Completion date: 2026-08-02
- Final commit: `c62b1ac9f34ade417aa4a0b50e4c6c4d3b956278`
- Merged PRs: 28
- Test evidence: Clean-main Phase 2 certification matrix passed: migration/parity, service suites, cross-service, focused recommendation and decision-journal privacy/observability coverage, frontend checks, dedicated journey, canonical Playwright 85 passed / 2 fixture-gated skips, tracker validation.
- ADRs: ADR-005-ATLAS-VERTICAL-SLICE-FOUNDATION.md; ADR-006-IMMUTABLE-FORECAST-PERSISTENCE.md
- Known limitations: External multi-user rollout remains blocked by retention/deletion policy; account currency authority remains fail-closed; Phase 3 remains not started.
- Authorized next phase: Phase 3 planning only: define a separately authorized bounded plan; do not implement automatically.

## phase-3 — Goal-linked recommendations

- Completion date: 2026-08-09
- Final commit: `3586e2b4f74c1476e454af4bb49bf3c994240471`
- Merged PRs: 33
- Test evidence: PR #33 final head: governance/status and cheap CI passed; heavy/browser skipped under the established backend-only policy.; Focused tracker tests: 12 passed; approved implementation tests: 181 focused passed and Rules Service suite 1179 passed, 10 skipped, 1 xfailed.
- ADRs: ADR-003-PROGRESSIVE-AUTONOMY.md, ADR-004-EVENTED-HISTORY.md
- Known limitations: External multi-user rollout remains blocked pending retention and user-deletion policy.; Currency authority remains fail-closed pending authoritative active-account currency.
- Authorized next phase: Phase 4 decision journal (ec-p4-decision-history) requires explicit authorization; do not begin automatically.

## phase-4 — Decision journal

- Completion date: 2026-08-10
- Final commit: `8463db1`
- Merged PRs: 35
- Test evidence: Phase 4 certification: Rules 1190 passed/10 skipped/1 xfailed; Finlynq 106 passed; root 22 passed; frontend Vitest 542 passed; TypeScript/lint passed; dedicated decision-history Playwright passed; canonical Playwright 85 passed/2 policy skips; final isolation-safe CI heavy and cheap passed in run 31457091205 for `8463db1`.
- ADRs: ADR-004-EVENTED-HISTORY.md
- Known limitations: External multi-user rollout remains blocked by retention/user-deletion and authoritative currency-policy decisions; no Phase 5 work is authorized or started.
- Authorized next phase: Phase 4 certified complete. Do not begin Phase 5 without explicit authorization.

## phase-5 — Market Intelligence Brief

- Completion date: 2026-08-11
- Final commit: `7832d6016d91f123fea1e27fb724dd64781aa5e7`
- Merged PRs: 36, 37, 38, 39
- Test evidence: Hosted CI 31505665961: cheap + heavy passed; Playwright 86 passed, 1 skipped; coverage artifacts uploaded; Clean-main local full matrix: scripts/test.sh passed; provider/briefing/delivery/scheduler, Rules Service, Finlynq/cross-service, Vitest/typecheck, and browser coverage exercised using synthetic/fake data
- ADRs: ADR-007-MARKET-INTELLIGENCE-ZERO-DOLLAR-BOUNDARY
- Known limitations: External multi-user rollout remains blocked by retention/user-deletion policy; Google Fonts DNS prevented local next build; hosted heavy production build passed
- Authorized next phase: Phase 6 is not started and requires separate explicit authorization.

## phase-5 — Market Intelligence Brief

- Completion date: 2026-08-11
- Final commit: `ef2a150b47b2c81159abe7494b0c7ba446fa124e`
- Merged PRs: 40
- Test evidence: Hosted run 31558931309: cheap and heavy (full + Playwright) succeeded for merge commit ef2a150; local complete Rules/Finlynq/frontend and isolated synthetic Market Brief journey passed.
- ADRs: ADR-007-MARKET-INTELLIGENCE-ZERO-DOLLAR-BOUNDARY.md
- Known limitations: All market-brief read/generation/provider/email/scheduler/local-summarization flags remain default-off; generation requires reviewed local Finnhub key and SEC User-Agent; no authoritative holding-to-CIK mapping exists, so SEC filing events are omitted with a data-quality warning; no real provider/email/personal database was used for correction validation.
- Authorized next phase: Phase 6 Scenario Lab remains unstarted and requires separate explicit authorization using docs/10-roadmap/PHASE6_SCENARIO_LAB_CAPABILITY_AUDIT_AND_PLAN.md.

## phase-6 — Scenario Lab

- Completion date: 2026-08-15
- Certification baseline: `9c9b554` (local-only governance adoption; final evidence commit contains this record)
- Merged PRs: 41, 55, 57
- Test evidence: Rules Service `1,298 passed, 10 skipped, 1 xfailed`; Finlynq `106 passed`; root cross-service/governance `37 passed`; Scenario/persistence/migration/parity/ownership/idempotency/comparison/archive focus `72 passed, 3 skipped`; frontend Vitest `630 passed` across 70 files; TypeScript, ESLint, and production build passed with only known backend-unavailable static-generation diagnostics; canonical Playwright `108 passed, 1 skipped` of 109; Scenario Lab route-mocked journeys `4 passed`; tracker tests `16 passed`; status/render, handoff, workflow YAML, shell, diff, and sensitive-artifact checks passed.
- ADRs: ADR-008-SCENARIO-LAB-BACKEND-FOUNDATION.md, ADR-009-LOCAL-VALIDATION-GOVERNANCE.md
- Known limitations: GitHub Actions is intentionally disabled and no hosted workflow was required; external multi-user rollout remains blocked by the retention/user-deletion policy; deterministic Scenario Lab bands are not probabilities and no Phase 7 capability is authorized.
- Authorized next phase: Run the separately authorized Phases 0–6 Personal-Use Acceptance and System Health Audit; do not begin Phase 7.
