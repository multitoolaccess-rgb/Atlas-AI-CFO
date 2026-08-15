# Atlas Personal-Use Readiness Report

- **Audit date:** 2026-08-15
- **Audited commit:** `ff85ad7bc39680a2beb13533795478e515cda931`
- **Verdict:** **Conditionally ready for isolated local exploration; readiness tooling is implemented, but not ready for unattended or fully activated personal use.**
- **Phase status:** Phases 0–6 certified locally; Phase 7 not started.
- **Related:** [Capability Matrix](../10-roadmap/ATLAS_CAPABILITY_MATRIX.md), [System Health Audit](./SYSTEM_HEALTH_AUDIT.md), [UI Acceptance Matrix](../06-ui-ux/UI_ACCEPTANCE_MATRIX.md), [Remediation Backlog](../10-roadmap/REMEDIATION_BACKLOG.md), [Personal Mode Proposal](./PERSONAL_MODE_PROPOSAL.md), [Wave 2 Currency/Recovery Plan](../10-roadmap/WAVE2_CURRENCY_BACKUP_RECOVERY_PLAN.md), [ADR-010](../adr/ADR-010-ACCOUNT-CURRENCY-AND-LOCAL-RECOVERY.md).

## Method and evidence

This audit used repository inspection, the clean-main Phase 6 certification evidence, isolated synthetic live-stack browser journeys, route-mocked UI journeys, tracker/render/handoff checks, and the existing pinned local environments. The production-audit skill named by the task was not available in the current skill registry, so the repository contracts and closest local audit/governance guidance were applied instead. No production behavior or personal database was changed.

Confirmed evidence:

- Clean main, `origin/main`, GitHub main, and `phase-6-complete` target are synchronized at the audited commit.
- Phase 6 local certification recorded Rules Service `1,298 passed, 10 skipped, 1 xfailed`; Finlynq `106 passed`; root tests `37 passed`; Scenario focus `72 passed, 3 skipped`; frontend Vitest `630 passed`; canonical Playwright `108 passed, 1 skipped`; TypeScript, ESLint, build, tracker, render, handoff, and scope checks passed.
- Isolated synthetic browser acceptance selected 17 journeys: 16 passed and one first-run axe journey failed because the screenshot/appearance harness saw a transient Next 404 on a migrated route; rerunning that single journey passed. The focused route set therefore passed after bounded retry, without code changes.
- The screenshot matrix produced 126 transient screenshots under `/tmp/atlas-phase0-6-audit-ff85ad7-screenshots`; the repository’s tracked screenshot directory was restored unchanged.

## Score

**Personal-Use Readiness: 70/100**

This score is deliberately capped below launch-ready because a complete enabled forecast → recommendation → decision → outcome → market → scenario journey was not proven under a supported personal configuration, and account-currency authority remains an open high-risk issue. Green certification suites prove contracts and regressions; they do not prove an operator can safely enable every capability.

| Dimension | Score | Basis |
|---|---:|---|
| Financial correctness | 82 | Decimal-safe Phase 0/1/6 authority, parity and stale-state tests are strong; legacy goal float and currency authority remain open risks. |
| Data integrity | 78 | Immutable versions, append-only history, idempotency, restrictive migrations and archive semantics are tested; personal backup/restore and live SQLite recovery are not drilled. |
| Security/privacy | 80 | Owner isolation, sanitized errors, hash-only evidence, server-owned flags, auth and CORS boundaries are covered; transitional tenancy and retention policy remain open. |
| Feature completeness | 58 | Phases 0–6 are implemented, but key server capabilities are intentionally default-off and real local provider readiness is not established. |
| UI usability | 79 | Final IA, shared shell, accessible states, URL routing, responsive checks and route-mocked journeys are strong; older screenshot inventory is partly harness-limited. |
| Reliability | 72 | Local tests, isolated E2E lifecycle, health endpoints and recovery states pass; startup has known migration/seed complexity and no full personal restart drill was completed. |
| Operations | 68 | `start.sh`, Atlas Doctor, isolated test harness, separate environments, and health probes exist; a full service-restart and personal backup/restore drill remains open. |
| Maintainability | 62 | Typed Phase 6/5 boundaries and shared IA are good; legacy simulation components, duplicate service wiring, legacy names and float-based presentation paths remain. |
| Documentation | 76 | Phase contracts, ADRs, handoff, status and engineering guides are substantial; personal activation and backup/recovery documentation need the waves below. |

The overall score is a risk-weighted judgment, not an average of green tests.

## Confirmed working or well-supported

- Final navigation and route ownership across Mission Control, Money, Wealth, Intelligence, and System.
- Legacy Money, Wealth, Recommendations, Market Briefs, Accounts, Debts, and Universe bookmark mappings where the IA contract specifies them.
- Server-authoritative Decimal projection, forecast, recommendation, decision, outcome, market-brief and Scenario Lab contracts.
- Append-only decision/outcome/history behavior, owner-scoped reads, sanitized errors, idempotency, and immutable scenario/archive behavior.
- Synthetic Market Intelligence citation/freshness/warning/detail/archive presentation.
- Scenario Lab generation presentation, persisted reload, explicit comparison selection, archive lifecycle, disabled/missing-baseline/incompatible recovery.
- Settings appearance mode/profile controls, reduced-motion behavior, keyboard navigation, mobile overflow checks, and scoped serious/critical axe checks.
- Isolated test lifecycle creates a temporary SQLite database and removes it on exit; no personal database was used.

## Implemented but unavailable or not proven operationally

- Forecast persistence/read API, decision-history API, Scenario Lab, and Market Brief provider/generation capabilities remain server-owned and default-off in checked-in configuration.
- Wave 1A now provides `python3 scripts/atlas_doctor.py` and authenticated Settings → Readiness checks; both keep server-owned flags and currency uncertainty fail-closed.
- The disposable synthetic acceptance command runs focused forecast, recommendation, decision-history, outcome, scenario, and fake-provider contract suites in a temporary SQLite database with test-only flags.
- A complete enabled financial journey was not run because doing so would require an explicit local configuration and an authoritative currency-ready synthetic dataset; the audit did not silently enable flags.
- Real Finnhub/SEC provider calls, Plaid connectivity, OCR, Ollama, email delivery, scheduler, brokerage, trading, and money movement were not used.
- Personal SQLite backup/restore, migration downgrade with retained personal records, and restart persistence were not exercised against a personal database.

## P0/P1 blockers

### P0 — none newly discovered

No new evidence shows a critical financial-integrity, authorization, privacy, or destructive-loss defect in the certified code paths.

### P1 — activation and safety blockers

1. **Account currency authority:** The repository has nullable source-backed fields and fail-closed validators, but no authorized evidence proves every current active personal account has fresh USD authority. A preference/default cannot prove USD. Keep forecast/scenario activation fail-closed until Wave 2A resolves the evidence lifecycle; tracked as `risk-p1-account-currency-authority`.
2. **Retention and deletion policy:** Immutable history has no approved retention/user-deletion policy. This blocks external multi-user rollout and must not be bypassed; tracked as `risk-p1-retention-rollout-gate`.
3. **Personal activation runbook:** No single supported operator path proves the ordered configuration, synthetic baseline, flags, and recovery checks needed for an enabled local journey.

## Highest-value P2/P3 findings

- **Completed Wave 1A:** Atlas Doctor, authenticated readiness contract/UI, and disposable synthetic acceptance command now expose safe recovery state without secrets or financial values.
- **P2:** Complete the isolated service-restart/persistence and backup/restore acceptance drill after authoritative currency is resolved.
- **P1:** Design and implement the non-destructive WAL-aware backup/restore contract in Wave 2B; no personal database action is authorized by this report.
- **P2:** Reconcile screenshot matrix route inventory with the final IA so legacy aliases are labelled as compatibility captures and migrated destinations are captured directly.
- **P3:** Quarantine or remove legacy client-side simulation calculators after compatibility references are no longer needed; do not make them financial authority.
- **P3:** Reduce legacy names and duplicate service/model documentation after a bounded terminology decision.
- **P3:** Address repository-wide frontend lint debt and dependency/reference inventory.

## Wave 2 planning outcome

Wave 2 is now planned as three separately authorized slices: 2A authoritative
currency, 2B non-destructive local backup/recovery, and 2C backup-first personal
activation acceptance. The plan records that the current schema is additive and
no-backfill, but a full correction/revocation audit lifecycle and supported
backup tool are not yet implemented. See the linked plan and ADR-010.

## Evidence gaps

- No real local provider credentials or provider network were used.
- No personal database was opened, inspected, migrated, backed up, or modified.
- No enabled feature-flag journey was certified against a personal database; the new acceptance command enables flags only inside a disposable synthetic test process.
- No production deployment or external multi-user behavior is implied.
- The full screenshot matrix is not a clean final-IA acceptance artifact because its checked-in test still includes compatibility routes; 126 transient captures are retained outside Git for audit reference.

## Recommended first remediation wave

The next bounded authorization is **Wave 2A — authoritative account currency only**. Do not access the personal database, implement backup/recovery, enable financial flags, or begin Wave 2B/2C or Phase 7.
