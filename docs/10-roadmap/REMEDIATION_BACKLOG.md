# Atlas Personal-Use Remediation Backlog

- **Audit date:** 2026-08-15
- **Audited commit:** `ff85ad7bc39680a2beb13533795478e515cda931`
- **Source:** [Personal-Use Readiness Report](../07-engineering/PERSONAL_USE_READINESS_REPORT.md) and [System Health Audit](../07-engineering/SYSTEM_HEALTH_AUDIT.md).
- **Status:** planning only; no remediation is started by this audit.

## Priority definitions

- **P0:** financial integrity, privacy, authorization, or data-loss risk.
- **P1:** blocks a safe personal-use journey or launch-critical recovery.
- **P2:** broken or inconsistent feature with a safe workaround.
- **P3:** maintainability, dead code, duplication, polish, or optimization.

## Wave 1 — Personal-use blockers and activation

**Risk:** Medium, with high-risk gates for currency or flag changes.
**Priority:** P1.

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
**Completion criteria:** one repeatable local command reports prerequisites without leaking secrets; enabled/disabled states are both tested; currency and ownership gates remain fail-closed.

## Wave 2 — Financial and data correctness

**Risk:** High.
**Priority:** P0/P1.

### Include

- Resolve authoritative active-account currency for projection state.
- Decide and, if approved, migrate legacy `Goal.target_amount` away from a precision-losing Float boundary.
- Run isolated SQLite/PostgreSQL parity and migration round-trip evidence for any changed financial persistence.
- Add a non-destructive WAL-aware backup/restore drill and recovery documentation.
- Reconcile Rules Service Alembic authority with Finlynq startup schema behavior.

### Exclude

- No rounding-policy change, forecast-engine rewrite, optimization, tax model, probability model, execution, or personal-data migration without explicit authorization.

**Likely files:** Finlynq account models/contracts, Rules projection adapter, forecast/scenario contracts, Alembic revisions, migration tests, local operations docs.
**Validation:** focused Decimal/parity/migration/ownership/idempotency suites plus a fresh independent local review; full certification only if the diff creates broad-regression evidence.
**Rollback:** additive migration with downgrade refusal for immutable records; restore from an operator-validated backup; never delete history to downgrade.
**Completion criteria:** authoritative currency is proven or activation remains disabled; precision boundaries are explicit; backup/restore and migration recovery are evidenced.

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
