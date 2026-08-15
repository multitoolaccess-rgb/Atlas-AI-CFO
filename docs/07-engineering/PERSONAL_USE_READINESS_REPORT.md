# Atlas Personal-Use Readiness Report

- **Audit date:** 2026-08-15
- **Audited baseline:** `ff85ad7bc39680a2beb13533795478e515cda931`
- **Wave 2C evidence update:** `9fbe20df1345645dd7f2ce95f49a6970faf869b0` (2026-08-15)
- **Waves 3–5 stabilization update:** local branch evidence at the final merged stabilization head; no personal financial state was changed by this wave.
- **Verdict:** **Ready for bounded single-user local use with explicit provider-safety caveats; not ready for unattended, external multi-user, or execution-enabled use.**
- **Phase status:** Phases 0–6 certified locally; Phase 7 not started.
- **Related:** [Capability Matrix](../10-roadmap/ATLAS_CAPABILITY_MATRIX.md), [System Health Audit](./SYSTEM_HEALTH_AUDIT.md), [UI Acceptance Matrix](../06-ui-ux/UI_ACCEPTANCE_MATRIX.md), [Remediation Backlog](../10-roadmap/REMEDIATION_BACKLOG.md), [Personal Mode Proposal](./PERSONAL_MODE_PROPOSAL.md), [Wave 2 Currency/Recovery Plan](../10-roadmap/WAVE2_CURRENCY_BACKUP_RECOVERY_PLAN.md), [ADR-010](../adr/ADR-010-ACCOUNT-CURRENCY-AND-LOCAL-RECOVERY.md).

## Method and evidence

This audit used repository inspection, the clean-main Phase 6 certification evidence, isolated synthetic live-stack browser journeys, route-mocked UI journeys, tracker/render/handoff checks, and the existing pinned local environments. The production-audit skill named by the task was not available in the current skill registry, so the repository contracts and closest local audit/governance guidance were applied instead. No production behavior or personal database was changed.

Confirmed evidence:

- Clean main, `origin/main`, GitHub main, and `phase-6-complete` target are synchronized at the audited commit.
- Phase 6 local certification recorded Rules Service `1,298 passed, 10 skipped, 1 xfailed`; Finlynq `106 passed`; root tests `37 passed`; Scenario focus `72 passed, 3 skipped`; frontend Vitest `630 passed`; canonical Playwright `108 passed, 1 skipped`; TypeScript, ESLint, build, tracker, render, handoff, and scope checks passed.
- Isolated synthetic browser acceptance selected 17 journeys: 16 passed and one first-run axe journey failed because the screenshot/appearance harness saw a transient Next 404 on a migrated route; rerunning that single journey passed. The focused route set therefore passed after bounded retry, without code changes.
- Waves 3–5 focused validation added 34 passing frontend tests, 7 passing route-mocked browser tests, TypeScript, and ESLint. The API diagnostics tests prove handled recovery responses remain out of the browser error channel while unexpected 500s remain observable without raw payloads.
- The screenshot matrix definition now targets canonical IA destinations. Full appearance/screenshot execution remains intentionally reserved for the Wave 6 certification boundary; no new screenshot artifacts were committed.

## Score

**Personal-Use Readiness: 82/100**

The score remains capped because external provider configuration still requires a separate safety decision, immutable-history retention/deletion policy is unresolved, Goal.target_amount remains a legacy Float boundary, and recommendation/decision/outcome/scenario personal writes were intentionally proven only on the disposable clone.

This score remains deliberately capped below launch-ready because Wave 6 integrated certification has not been run, external provider configuration still requires a separate safety decision, immutable-history retention/deletion policy is unresolved, Goal.target_amount remains a legacy Float boundary, and personal recommendation/decision/outcome/scenario writes were intentionally proven only on the disposable clone. Green focused suites prove contracts and regressions; they do not replace the final local certification matrix.

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
- Wave 2B synthetic WAL/checksum/path-safety/restore tests passed. Fresh pre-activation and final personal backups plus disposable restores passed at `Z9a1b2c3d4e5`; no in-place restore was attempted.

## P0/P1 blockers

### Current Wave 2C status

Wave 2C is complete for the explicitly authorized six-account personal scope.
PR #58 established the append-only exact-cent evidence contract with explicit
`ROUND_HALF_EVEN` confirmation; it did not claim to restore historical Float
precision. PR #60 corrected the authenticated adapter seam by forwarding the
already-validated `fc_session` cookie to forecast and Scenario Lab adapters,
without exposing the signing secret.

The personal database now has six authoritative USD currency assertions, six
hash-bound Decimal balance observations, one approved `500.00 USD` monthly
projection configuration, and one immutable baseline forecast. A fresh backup
and disposable restore passed. The six-account clone passed the full synthetic
write/restart journey, and personal health, authenticated readiness, baseline
reload, UI route loading, persistence, and clean shutdown passed.

### P0 — none newly discovered

No new evidence shows a critical financial-integrity, authorization, privacy, or destructive-loss defect in the certified code paths.

### P1 — remaining safety constraints

1. **Retention and deletion policy:** Immutable history has no approved retention/user-deletion policy. This blocks external multi-user rollout and must not be bypassed; tracked as `risk-p1-retention-rollout-gate`.
2. **Pre-existing provider configuration:** Ignored local configuration still contains Market Intelligence read/generation/external-provider flags and a provider credential. No external call was made; automated acceptance overrode these flags to false in child processes. Keep the configuration as a separate safety task.
3. **Legacy goal precision:** `Goal.target_amount` remains a documented Float boundary; no migration or claim of restored source precision was made in Wave 2C.

## Highest-value P2/P3 findings

- **Completed Wave 1A:** Atlas Doctor, authenticated readiness contract/UI, and disposable synthetic acceptance command now expose safe recovery state without secrets or financial values.
- **Completed Wave 2C:** The isolated six-account service-restart/persistence and backup/restore acceptance drill passed. No in-place restore was attempted.
- **Completed Wave 3–5 route stabilization:** Screenshot evidence now targets canonical IA destinations; compatibility aliases remain covered by redirect tests and are not treated as primary visual surfaces.
- **Completed Wave 3–5 diagnostics:** Expected route recovery responses are bounded in browser diagnostics, while unexpected server failures remain visible and raw response/request payloads are no longer logged.
- **P3 deferred:** Quarantine or remove legacy client-side simulation calculators after a dedicated compatibility decision; current reference search found no runtime imports outside their own tests, but the code remains preserved rather than deleted in this wave. Do not make it financial authority.
- **P3:** Reduce legacy names and duplicate service/model documentation after a bounded terminology decision.
- **P3:** Address repository-wide frontend lint debt and dependency/reference inventory.

## Wave 2 planning outcome

Wave 2 is split into three separately authorized slices: 2A authoritative
currency, 2B non-destructive local backup/recovery, and 2C backup-first
personal activation acceptance. All three are complete for the authorized
single-user scope. Full personal write journeys for recommendations, decisions,
outcomes, and scenarios remain intentionally confined to disposable synthetic
acceptance; no external provider or execution behavior was activated.

## Evidence gaps

- No real local provider call or provider network was used. The final Doctor diagnostic detected provider credential presence and pre-existing Market Intelligence read/generation/external-provider flags in ignored local configuration; those flags were not changed or invoked and must not be treated as disabled.
- Waves 3–5 did not mutate the personal database, change financial calculations, enable providers, or alter phase tags. Focused route-mocked tests used synthetic responses only.
- The personal SQLite database was accessed only under the explicit Wave 2C authorization for metadata, integrity, migration, bounded account-currency evidence status, and append-only operator confirmation; balances, transactions, holdings, account numbers, and raw evidence were not printed.
- A verified backup exists outside the repository and a disposable restore passed; no in-place personal restore was attempted.
- The projection operator resolved one active goal and recorded the authorized `500.00 USD` configuration. The personal baseline was generated only after the six-account evidence and clone gates passed.
- Approved local forecast persistence/read, decision-history, and Scenario Lab flags are enabled in the ignored local configuration. External provider flags were overridden off only in automated acceptance; the existing ignored provider configuration was not changed.
- No production deployment or external multi-user behavior is implied.
- The screenshot matrix definition is now aligned to canonical IA destinations; legacy compatibility routes remain covered separately by redirect tests. Existing historical transient captures remain outside Git for audit reference.

## Stabilization outcome and next task

The combined Waves 3–5 Product Stabilization Wave is complete for its bounded scope: canonical route evidence, compatibility disposition, sanitized diagnostics, focused accessibility/recovery coverage, and local TypeScript/ESLint validation. Full local integrated acceptance remains a separate Wave 6 certification boundary.

The next bounded task is **Wave 6 — Final Personal-Use Acceptance and Release Candidate Certification**. It requires separate authorization and must not be started automatically. Phase 7 remains out of scope.
