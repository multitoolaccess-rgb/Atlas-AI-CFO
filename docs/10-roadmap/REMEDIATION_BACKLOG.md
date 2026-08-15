# Atlas Personal-Use Remediation Backlog

- **Audit date:** 2026-08-15
- **Audited commit:** `ff85ad7bc39680a2beb13533795478e515cda931`
- **Source:** [Personal-Use Readiness Report](../07-engineering/PERSONAL_USE_READINESS_REPORT.md) and [System Health Audit](../07-engineering/SYSTEM_HEALTH_AUDIT.md).
- **Status:** Wave 1A, Wave 2A, and Wave 2B are complete. Wave 2C was authorized and partially executed after a verified backup, but final personal activation remains blocked by missing projection configuration/baseline and an unresolved local service-lifecycle acceptance failure.

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

**Status:** Wave 2A and Wave 2B complete; Wave 2C is incomplete and blocked after backup-first personal evidence confirmation and a failed bounded activation/restart gate.
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

### Wave 2C — Personal activation acceptance — blocked

- Backup gate passed; the personal database was migrated forward from
  `W6a1b2c3d4e5` to `X7a1b2c3d4e5` through a compatibility-safe additive path.
- Bounded inventory found four active accounts, all unknown; authorized local
  operator confirmation appended four USD evidence events. No conflicting or
  non-USD evidence was overwritten.
- Doctor/readiness and the non-disclosing goal precision gate passed for
  currency/storage prerequisites.
- Disposable clone restart/readiness evidence passed for currency persistence,
  but forecast generation exposed a sanitized-unavailability integration gap
  (fixed in `d769870`) and the personal enabled-stack attempt did not remain
  available for authenticated readiness. The personal database is intact and
  flags were rolled back/off.
- Do not claim Wave 2C complete until projection configuration/baseline and the
  service lifecycle/startup contract are repaired and the isolated clone plus
  personal readiness gates pass.

### Goal Float and other boundaries

- Keep `Goal.target_amount` Float unchanged in Wave 2 planning. Resolve it in
  a separate high-risk prerequisite before Wave 2C if personal activation
  would make target precision material; otherwise keep the existing
  `Decimal(str(value))`/non-restored-precision disclosure.
- Preserve the retention/deletion blocker, SQLite/PostgreSQL parity risk,
  transitional tenancy, trusted generation boundary, and external-provider
  restrictions.

### Exclude

- Wave 2B/2C remain unimplemented: no backup/restore, personal-data access,
  automatic flags, currency conversion, rounding-policy
  change, forecast-engine rewrite, optimization, tax/probability model,
  execution, provider purchase, email, scheduler, LLM, tenancy, retention/
  deletion policy, or Phase 7 work.

**Validation:** Wave 2A uses focused currency/provenance/auth/ownership/
Decimal/migration/parity tests; future 2B requires synthetic WAL/manifest/restore
tests; and 2C requires a separately authorized backup-first isolated live-stack
journey. Full certification is not implied by this plan.
**Rollback:** keep defaults off; append evidence corrections; refuse unsafe
migration downgrade; use a checked pre-restore backup; never delete immutable
history.
**Completion criteria:** 2A proves authority or keeps activation blocked; 2B
proves verified local recovery; 2C proves only the explicitly authorized local
journey.
## Wave 3 — Broken UI/API integrations

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
**Completion criteria:** every enabled capability has an honest loading/empty/unavailable/error state and one reproducible synthetic journey.

## Wave 4 — Dead code, duplicate paths, and dependency cleanup

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
**Completion criteria:** every removed item has zero required runtime references or an explicit compatibility disposition; no duplicate full visualization remains.

## Wave 5 — Performance, accessibility, observability, and polish

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
**Completion criteria:** expected handled responses remain quiet while unexpected 5xx/JS errors remain visible; route matrix is deterministic.

## Wave 6 — Final personal-use acceptance and release candidate

**Risk:** High because it certifies the integrated system, not because it adds authority.
**Priority:** P1.

### Include

- Run the complete local acceptance journey against isolated synthetic data.
- Verify restart persistence, readiness, recovery, appearance, accessibility, and no horizontal overflow.
- Record a release-candidate evidence bundle and update the handoff.

### Exclude

- No Phase 7 planning/implementation in the remediation wave; no production deployment or external multi-user rollout.

**Likely files:** documentation/evidence and focused acceptance harness; product files only if a prior approved wave identifies a defect.
**Validation:** complete local matrix at the release boundary, including canonical Playwright and applicable service suites.
**Rollback:** evidence-only rollback; product changes retain their own reversible commits and are not hidden by certification records.
**Completion criteria:** all launch-critical journeys are proven, open P0/P1 blockers are resolved or explicitly keep features disabled, and no unauthorized capability is introduced.

## Dependency order

`Wave 1 → Wave 2 → Wave 3 → Wave 4/Wave 5 → Wave 6`.

Wave 2 must precede enabling forecast/scenario behavior. Wave 3 depends on a safe activation contract. Waves 4 and 5 may proceed in parallel after ownership is confirmed. Wave 6 is a separate release-candidate authorization and is not started by this audit.
