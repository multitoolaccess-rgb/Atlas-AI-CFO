# Atlas Personal-Use Remediation Backlog

- **Audit date:** 2026-08-15
- **Audited commit:** `ff85ad7bc39680a2beb13533795478e515cda931`
- **Source:** [Personal-Use Readiness Report](../07-engineering/PERSONAL_USE_READINESS_REPORT.md) and [System Health Audit](../07-engineering/SYSTEM_HEALTH_AUDIT.md).
- **Status:** Wave 1A, Wave 2A, Wave 2B, and Wave 2C are complete. Six-account personal activation passed the backup-first, disposable-clone, projection, baseline, restart, and readiness gates. External provider configuration remains a separate open safety risk.

## Priority definitions

- **P0:** financial integrity, privacy, authorization, or data-loss risk.
- **P1:** blocks a safe personal-use journey or launch-critical recovery.
- **P2:** broken or inconsistent feature with a safe workaround.
- **P3:** maintainability, dead code, duplication, polish, or optimization.

## Wave 1 — Personal-use blockers and activation

**Risk:** Medium, with high-risk gates for currency or flag changes.
**Priority:** P1.

### Wave 1A completed

- Implemented `scripts/atlas_doctor.py` with redacted text/JSON output and deterministic exit codes.
- Implemented authenticated `GET /api/system/readiness` and Settings → Readiness.
- Added `scripts/synthetic_personal_acceptance.py` with disposable SQLite and test-scoped flags.
- Added activation/recovery commands and explicit default-off boundaries to the Personal Mode proposal.

### Include

- Define a supported local Personal Mode profile and ordered startup/readiness checks.
- Add a design-approved Atlas Doctor command and System → Readiness screen proposal, without exposing secrets.
- Require authoritative currency proof before forecast/scenario activation.
- Document safe synthetic acceptance for forecast → recommendation → decision → history/outcome → scenario.
- Clarify which default-off flags can be explicitly enabled by a local operator and the required dependencies.

### Exclude

- No automatic flag enablement, real provider activation, email, scheduler, cloud LLM, trading, brokerage, money movement, tenancy, or Phase 7 work.

**Likely files:** `start.sh`, `scripts/`, `services/rules-service/app/config.py` only if a bounded readiness surface is authorized, System/Help docs, tests, and `docs/07-engineering/PERSONAL_MODE_PROPOSAL.md`.
**Validation:** governance tests; focused config/readiness tests; isolated synthetic route-mocked and live-stack journey; no personal DB.
**Rollback:** revert readiness/runbook changes; keep all server-owned defaults unchanged.
**Completion criteria:** one repeatable local command reports prerequisites without leaking secrets; enabled/disabled states are both tested; currency and ownership gates remain fail-closed. Wave 1A satisfies the diagnostics, readiness, and disposable synthetic-command portions; currency authority and backup/recovery remain open.

## Wave 2 — Financial and data correctness

**Status:** Wave 2A, Wave 2B, and Wave 2C complete for the authorized single-user local scope; external provider safety and multi-user retention remain open constraints.
**Risk:** High.
**Priority:** P0/P1.
**Plan:** [WAVE2_CURRENCY_BACKUP_RECOVERY_PLAN.md](./WAVE2_CURRENCY_BACKUP_RECOVERY_PLAN.md) and [ADR-010](../adr/ADR-010-ACCOUNT-CURRENCY-AND-LOCAL-RECOVERY.md).

Wave 2 is deliberately split into three bounded slices. Do not combine them
into one change or begin the next slice automatically.

### Wave 2A — Authoritative account currency — complete

- Added the append-only `account_currency_evidence` lifecycle and additive
  `X7a1b2c3d4e5` migration with no backfill, ownership guards, idempotency, and
  immutable update/delete rejection.
- Mapped only explicit structured-provider and structured-statement evidence;
  Plaid IDs, symbols, locale, preferences, and account names remain
  non-authoritative.
- Gated projection, forecast, and Scenario Lab state on complete fresh USD
  evidence for every included active account, with stable blocked reason codes.
- Hardened the dry-run-first operator confirmation with owner isolation,
  idempotency, correction, revocation, and sanitized Doctor/readiness
  integration.
- No personal database access, flag enablement, backup/restore, or activation.

### Wave 2B — Non-destructive local backup and recovery — complete

- Added `scripts/atlas_backup.py`, `scripts/atlas_restore.py`, and shared
  safety primitives using SQLite’s online backup API.
- Refuse ambiguous destinations, symlinks, active holders, unexpected files,
  unsupported schema/identity, checksum mismatch, and silent overwrite.
- Produce restrictive `atlas-sqlite-backup/v1` manifests with checksum,
  journal mode, integrity, and migration metadata; restore only to a new path.
- Synthetic safety suite: 7 tests passed, including WAL, concurrent readers,
  corruption/checksum, path safety, active-holder refusal, permissions, and
  disposable restore equivalence.
- A verified personal backup exists outside the repository; its post-evidence
  manifest is checked at `X7a1b2c3d4e5`, WAL mode, integrity `ok`.

### Wave 2C — Personal activation acceptance — complete

- Explicit authorization expanded the scope from four to all six active Atlas
  accounts. All six remained owned, active, USD-denominated, and eligible.
- Fresh WAL-safe backup and disposable restore passed with schema
  `Z9a1b2c3d4e5`, integrity `ok`, and verified SHA-256 metadata. The verified
  pre-activation backup remains outside the repository; a final post-activation
  safety backup is also preserved.
- Six-account currency and exact-cent balance evidence is append-only,
  hash-bound, and authoritative. No legacy balance amount was rewritten and
  no historical Float precision was claimed restored.
- The authorized `500.00 USD` monthly `net_worth` projection configuration and
  one immutable personal baseline forecast are present. Forecast reads reload
  through the authenticated API and Scenario Lab readiness recognizes the
  baseline.
- The disposable restored clone passed forecast, recommendation, decision,
  history reload, pending/not-yet-measurable/measured outcome lifecycle,
  Scenario Lab generation, comparison, archive/history, full restart, and
  cleanup. External providers, email, scheduler, LLM, execution, trading,
  brokerage, and money movement were disabled in child-process acceptance.
- Personal restart acceptance passed health, authenticated readiness, goals/UI
  route loading, baseline read/reload, persistence, and clean Atlas-owned
  shutdown. Personal database write journeys for recommendations, decisions,
  outcomes, and scenarios were intentionally not exercised; those writes were
  proven only on the disposable clone.
- PR #60 corrected the authenticated adapter seam so the already-validated
  `fc_session` cookie is forwarded to Rules/Finlynq forecast and Scenario Lab
  adapters without exposing the signing secret.
- Do not begin the combined Waves 3–5 stabilization wave or Phase 7
  automatically.

### Goal Float and other boundaries

- Keep `Goal.target_amount` Float unchanged in Wave 2 planning. Resolve it in
  a separate high-risk prerequisite before Wave 2C if personal activation
  would make target precision material; otherwise keep the existing
  `Decimal(str(value))`/non-restored-precision disclosure.
- Preserve the retention/deletion blocker, SQLite/PostgreSQL parity risk,
  transitional tenancy, trusted generation boundary, and external-provider
  restrictions.

### Exclude

- No additional Wave 2B/2C behavior remains in this backlog. The completed
  work did not add currency conversion, forecast-engine rewrites, optimization,
  tax/probability models, execution, provider purchase, email, scheduler, LLM,
  tenancy, retention/deletion policy, or Phase 7 work.

**Validation:** Wave 2A used focused currency/provenance/auth/ownership/
Decimal/migration/parity tests; Wave 2B used synthetic WAL/manifest/restore
tests; and Wave 2C used the six-account backup-first clone and personal
restart/readiness journey. Full phase certification is not implied by this
remediation plan.
**Rollback:** keep defaults off; append evidence corrections; refuse unsafe
migration downgrade; use a checked pre-restore backup; never delete immutable
history.
**Completion criteria:** 2A proves authority; 2B proves non-destructive backup/
restore; 2C proves the authorized six-account activation and restart gates;
proves verified local recovery; 2C proves only the explicitly authorized local
journey.
## Wave 3 — Broken UI/API integrations

**Status:** Complete for the bounded stabilization scope. The delivered server-owned journeys remain unchanged; focused route-mocked coverage now exercises canonical navigation, Scenario Lab persistence/recovery, and sanitized API diagnostics.
**Risk:** Medium unless backend authority changes, then High.
**Priority:** P1/P2.

### Include

- Prove an enabled local forecast/recommendation/history journey against synthetic state.
- Prove Market Intelligence local provider readiness only with reviewed local configuration and fake/synthetic alternatives.
- Reconcile screenshot/acceptance routes to final canonical IA.
- Improve readiness/error recovery where the current workaround is unclear.

### Exclude

- No provider purchase, real email, scheduler, LLM summarization, execution, or client-side financial computation.

**Likely files:** UI route-mocked specs, typed clients, help/readiness docs, provider readiness components, focused backend fixtures.
**Validation:** affected Vitest, TypeScript/lint, route-mocked browser tests, isolated live stack only where integration is genuine, scoped axe/overflow/console checks.
**Rollback:** revert UI/readiness changes; preserve compatibility redirects and default-off behavior.
**Completion criteria:** every enabled capability has an honest loading/empty/unavailable/error state and one reproducible synthetic journey. Satisfied by the existing Scenario Lab and Market Intelligence route-mocked suites plus the focused local validation recorded in the completion evidence.

## Wave 4 — Dead code, duplicate paths, and dependency cleanup

**Status:** Complete for the bounded inventory/ownership scope. The legacy simulation directory has no runtime imports outside its own tests and remains quarantined rather than deleted; compatibility routes remain intentionally preserved. The screenshot matrix now targets canonical IA destinations while redirect tests retain legacy bookmark coverage.
**Risk:** Medium.
**Priority:** P3, escalating if financial authority or privacy boundaries are affected.

### Include

- Quarantine or remove legacy simulation components after reference/use confirmation.
- Inventory unused exports/dependencies and duplicate documentation.
- Clarify Data Connections delegation and legacy route ownership.
- Update screenshot and route inventories to label compatibility aliases.

### Exclude

- Do not delete compatibility redirects, safety fallbacks, or authoritative server code solely because it is old.
- Do not remove simulation tests until replacement coverage proves no authority regression.

**Likely files:** `ui/components/simulation/**`, `ui/lib/math/**`, route inventory/tests, docs and package manifests.
**Validation:** reference search, affected Vitest, TypeScript/lint, focused browser navigation, diff review.
**Rollback:** restore deleted paths or revert the cohesive cleanup commit.
**Completion criteria:** every removed item has zero required runtime references or an explicit compatibility disposition; no duplicate full visualization remains. Satisfied without deleting compatibility code or server-authoritative financial modules; the unreferenced legacy simulation components remain a documented deferred removal candidate because their historical tests still provide compatibility evidence.

## Wave 5 — Performance, accessibility, observability, and polish

**Status:** Complete for the bounded diagnostics and browser-harness scope. Known handled recovery responses are now logged only as bounded status/code diagnostics; unexpected server failures remain observable without raw response/request payloads. Route-mocked browser startup now explicitly supports the SSR backend bypass it documents.
**Risk:** Medium.
**Priority:** P2/P3.

### Include

- Reduce duplicate request patterns and startup ambiguity.
- Add route-level readiness diagnostics and bounded logging.
- Reconcile intermittent Next dev chunk/404 behavior in the test harness without masking API failures.
- Expand representative final-IA axe, keyboard, reduced-motion, and overflow evidence.

### Exclude

- Do not blanket-suppress browser errors, increase timeouts without evidence, or change financial semantics.

**Likely files:** browser harness, shared shell, API/cache utilities, health/readiness surfaces.
**Validation:** focused browser journeys, scoped axe, console/page-error assertions, typecheck/lint; certification only if shared infrastructure changes.
**Rollback:** revert harness/observability changes independently of product behavior.
**Completion criteria:** expected handled responses remain quiet while unexpected 5xx/JS errors remain visible; route matrix is deterministic. Satisfied by the focused API logging tests and seven passing route-mocked Scenario/System navigation tests. The full appearance/screenshot execution remains reserved for Wave 6.

## Wave 6 — Final personal-use acceptance and release candidate

**Risk:** High because it certifies the integrated system, not because it adds authority.
**Priority:** P1.
**Status:** Complete for the authorized bounded single-user local release-candidate scope.

### Completed evidence

- Complete local matrix at clean main `8efcdaee`: Rules `1,321 passed, 10 skipped, 1 expected xfail`; Finlynq `138 passed`; root `51 passed`; frontend `639 passed`; TypeScript, ESLint, and production build passed.
- Canonical Playwright `108 passed, 1 policy-defined skip`; screenshot matrix `1/1` passed; scoped axe, keyboard, reduced motion, responsive overflow, recovery, console, page-error, and appearance/profile checks passed.
- Isolated synthetic forecast → recommendation → decision/history → outcome → Scenario Lab generation/comparison/archive → restart journey passed with external capabilities forced off.
- Fresh WAL-safe backup and disposable restore passed at schema `Z9a1b2c3d4e5`, integrity `ok`; no in-place restore was attempted.
- Read-only personal acceptance passed for six active USD accounts, six currency and balance authorities, one projection configuration, one immutable baseline reload, authenticated readiness, intended routes, restart persistence, and clean shutdown. No personal recommendation, decision, outcome, or scenario writes were created.

### Exclude

- No Phase 7 planning/implementation; no production deployment or external multi-user rollout.
- No real provider, email, scheduler, LLM, trading, brokerage, execution, or money-movement calls.

**Likely files:** certification evidence and status/handoff documentation only after the matrix passes; product corrections only if an evidenced in-scope defect is found.
**Validation:** complete local matrix at the release boundary, including canonical Playwright and applicable service suites.
**Rollback:** evidence-only rollback; product corrections retain their own reversible commits and are not hidden by certification records.
**Completion criteria:** satisfied for the bounded local scope; unresolved retention/provider/tenancy/Float/in-place-restore risks remain explicitly open or constrained.

## Dependency order

`Wave 1 → Wave 2 → Wave 3 → Wave 4/Wave 5 → Wave 6`.

Waves 3–5 completion evidence was scoped to the stabilized UI/API boundary; Wave 6 now adds the integrated local matrix, isolated synthetic journey, backup/restore gate, and read-only personal acceptance. No Phase 7 work is implied.

Wave 2 precedes forecast/scenario behavior. Wave 3 depends on a safe activation contract. Waves 4 and 5 proceeded after ownership was confirmed. Wave 6 is complete only for the explicitly authorized single-user release-candidate scope.
