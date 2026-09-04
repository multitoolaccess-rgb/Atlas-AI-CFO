# Atlas Investment System — Genuine Completeness Gap Report

**Date:** 2026-09-04
**Authority:** Canonical project tracker (`docs/10-roadmap/PROJECT_STATUS.json`), `ATLAS-INVESTMENT-UI-12-READINESS-AND-TRUST-CERTIFICATION-AUDIT.md`, `ATLAS-INVESTMENT-REMAINING-PHASES-AUDIT-AND-EXECUTION-PLAN.md`, `ATLAS-INVESTMENT-CONSOLIDATED-EXECUTION-PLAN.md`, `ATLAS-INVESTMENT-UI-UX-IMPLEMENTATION-ROADMAP.md`, `ADR-UI-11-CURRENT-PORTFOLIO-RISK-BOUNDARY.md`
**Method:** Read-only audit of tracker phase status, phase gate documents, and committed test evidence. Classifications follow the repository rule that a capability is COMPLETE only with runtime/test evidence, never by documentation alone.

---

## 0. Executive summary

The investment system is **not genuinely complete**, and the honest way to say that is: **every implementable phase that was approved has been implemented and certified within its bounded scope, but three substantive backend/policy prerequisites and a set of certification blockers remain open.** None of the remaining work is "UI polish" that a designer could sweep; the bulk of it is contract, methodology, and policy work that must be built and approved before the roadmap can be called finished.

The complete list of what remains, in priority order:

| # | Missing item | Kind | Blocks what | Status today |
|---|---|---|---|---|
| 1 | INV-12 evaluation / calibration / replay / retention | Backend + policy prerequisite | "Genuinely complete" investment system; UI-12 certification | `not_started` |
| 2 | Approved multi-user retention & user-deletion policy | Policy prerequisite | External multi-user production rollout | `blocked` (open product-security risk) |
| 3 | UI-12 certification blockers (6 concrete items, §2.3) | Evidence + boundary prerequisite | UI-12 final certification | `in_progress` |
| 4 | UI-10 external-research adapters (web search, arbitrary URL, security-master lookup, private-context prompts) | Backend prerequisite for the *full* Scout vision | "Full" Scout; explicitly out of the certified slice | deferred by design |
| 5 | UI-11 advanced/historical risk methodology (volatility, drawdown, VaR, etc.) | Methodology prerequisite | Complete portfolio-risk surface | deferred by design |
| 6 | INV-10 durable report archive | Optional decision | Nothing unless a concrete consumer exists | deferred |
| 7 | Small test/lint debt (stale migration assertion, repo-wide frontend lint) | Cleanup | None strictly; hygiene | open |

Everything else in the brief's "journey" — discovery, research (bounded), committee, recommendation, review, decision, scenario/risk (bounded), outcome — **exists and is certified within its declared bounds**.

---

## 1. What "complete" means and the current phase inventory

"Complete" is defined by the roadmap phase map (INV-01…INV-12 + UI-01…UI-12) and the repository's certification rule: a phase is complete when its exit criteria have runtime/test evidence and its declared limitations are explicit. The canonical tracker (verified 2026-09-04) reports:

| Phase | Status | Bounded scope note |
|---|---|---|
| INV-01 Security identity | complete | Canonical identity foundation |
| INV-02 Market/security observations | complete | Point-in-time contracts |
| INV-03 Portfolio intelligence | complete | No second ledger |
| INV-04 Fundamentals | complete | Provenance-aware research contracts |
| INV-05 Technical | complete | Adjustment-basis-safe contracts |
| INV-06 Macro | complete | Vintaged contracts |
| INV-07 Quant | complete | Benchmark-aware, zero-price-safe |
| INV-08 AI Investment Committee | complete | Evidence-linked typed findings |
| INV-09 Investment recommendations | complete | Lifecycle, provenance, hashes |
| INV-10 CIO reporting | complete | Bounded in-memory projection; archive deferred |
| INV-11 Decision/outcome tracking | complete | Append-only human decisions, outcome linkage |
| INV-HARDEN-01 / INV-PERSIST-03 | complete | Fail-closed rules; trusted persistence boundary |
| UI-01…UI-08 | complete | Architecture through certified recommendation review |
| UI-09 Discovery | complete | Current-only portfolio + bounded S&P 500 modes |
| UI-10 Scout | complete for contextual slice (`f5a1cc8`); provider-backed expansion in progress → complete after this push | Two bounded read-only Scout surfaces |
| UI-11 Risk/scenario | complete for bounded first slice (`fb549b4`, hardening `b9ecce0`) | Current-only baseline + hypothetical preview only |
| UI-12 Cross-route trust certification | in_progress; **not certified** | Ten-route read-only matrix passes; explicit blockers remain |
| INV-12 Evaluation/calibration/replay/retention | **not_started** | The single biggest missing backend phase |

---

## 2. Blocking prerequisites (must be built/decided before "genuinely complete")

These are not polish. Each one requires contract, methodology, or policy work.

### 2.1 INV-12 — Evaluation, calibration, replay, and retention (`not_started`)

The largest single gap. INV-11 outcome tracking provides frozen observations and deterministic single-outcome evaluation, but INV-12 as a product contract does not exist. The remaining-phases audit already specifies the minimum artifact:

- **Evaluation artifact**: evaluation ID + schema version, owner scope, recommendation identity + immutable hash/version, optional decision identity/hash, outcome identity/hash or frozen observation references, methodology/version, evaluation window, evaluation `as_of`/`as_known_at`, benchmark identity + observation hashes, result state (insufficient/unavailable/incompatible), deterministic input hash + evaluation hash, provenance, creation timestamp.
- **Evaluation repository + read API**: owner-scoped immutable artifacts, deterministic replay, idempotency, no mutation of source history.
- **Calibration slice**: gated on a statistically valid cohort definition, minimum sample rules, missing-data policy, and metric definitions. "Calibration from a few fixtures" is explicitly prohibited.
- **Retention/deletion slice**: gated on product-security approval (see 2.2).

Why it is a prerequisite: UI-12's certification gate explicitly depends on the INV-12 evaluation/replay/retention boundary ("INV-12 dependency items that touch UI-12 presentation are either resolved or explicitly deferred with an honest limitation"). INV-12 is listed on the roadmap as a dependency of the final trust review.

### 2.2 Approved multi-user retention & user-deletion policy (open product-security blocker)

The repository's open blocker tracked as `external-multi-user-retention-deletion-blocker` and risk `p1-retention-rollout-gate`: **there is no approved retention and user-deletion policy for immutable forecast history.** Consequences:

- External multi-user production enablement is BLOCKED.
- This does not block solo personal-use iteration (explicitly allowed), but it cannot be reclassified as resolved by any personal-use UI pass.
- INV-12's retention/deletion slice cannot be implemented before this policy is approved.

This is a prerequisite for any claim of multi-user production readiness, and is therefore a genuine completeness blocker for the system as a whole.

### 2.3 UI-12 certification blockers (the final trust gate stays `not certified`)

The UI-12 audit (Appendix D/F/G) documents six concrete blockers. All are real and evidence-graded, not cosmetic:

1. **`/portfolio` fails the read-only gate.** The page measured `scrollWidth=407` at a `390px` viewport and includes mutation controls. It needs a separately owned responsive/scope remediation **and** its mutation workflow separated/gated from the read-only certification boundary. The responsive half is polish-adjacent; the mutation-control separation is architectural.
2. **Populated owner-data evidence is incomplete.** The hermetic live-stack run exercised an isolated empty database, so it proved startup/route rendering and safe empty/unavailable states, but not populated owner data for every backend-dependent route. Requires deterministic synthetic owner-data seeding (or documented per-route `unavailable`) and a rerun.
3. **CPU interaction budgets are not measured.** Route-load (<10 s) and payload (<512 KiB) budgets are measured; CPU-during-interaction is not.
4. **INV-12 evaluation/replay/retention semantics unresolved** (see 2.1).
5. **Optional durable CIO report archive decision unresolved.** Pending a concrete consumer; currently correctly excluded.
6. **Multi-user retention/deletion blocker** (see 2.2).

The audit's verdict is explicit: **UI-12 remains PARTIAL and is not certified**, and the matrix correctly marks INV-12 evaluation/replay/retention, CIO archive, and multi-user retention as `BLOCKED`.

### 2.4 Full-vision Scout prerequisites (UI-10) — explicitly out of the certified slice

The approved UI-10 slice is bounded and certified. The *full* "Investment Context Scout" vision in the alternate brief is not implemented, and each missing capability is a dedicated server-owned adapter/contract, not UI work:

- live external web research / unrestricted source retrieval / arbitrary URL fetching / general crawling;
- external-source discovery, security-master, and portfolio adapters for selectors beyond recommendation/committee/holding;
- private portfolio-context research (portfolio facts as prompt context);
- independent security-master lookup (today, recommendation/committee selectors still require the referenced security to be a resolved **held** security);
- numeric source-quality scoring.

Each of these requires its own bounded contract, adapter, and threat model before it can be added. The current slice stays read-only, current-context-only, and Finnhub/SEC-limited by design.

### 2.5 Full-vision risk prerequisites (UI-11) — methodology-gated

The certified UI-11 slice is current-only: position count, observed value, compatible single-currency exposure, data-quality states, bounded position-value deltas. The advanced/historical risk brief items are **blocked by missing approved methodology and missing proven reconstructed historical inputs**, and the brief itself prohibits fabricating them:

- historical portfolio reconstruction; portfolio volatility, covariance, correlation, drawdown history;
- liquidity, sector/geography risk, VaR, probability, optimization, target allocation;
- FX normalization and persisted scenarios;
- security-level sensitivity/range analysis.

These are prerequisites for a "complete portfolio-risk" claim, correctly recorded as deferred in the ADR and UI-12 Appendix A.

### 2.6 Small but genuine backend/test debt

- **`test_forecast_migration.py` contains stale assertions** expecting historical head `Z14a1b2c3d4e5` instead of the current head `AB16a1b2c3d4e5`. The new Scout migration suite is independently green, but this legacy test's expected-head text needs a bounded update (it is deliberately out of scope of the UI-10/12 corrections so far).
- **Repository-wide frontend lint debt** (risk `frontend-lint-debt`, medium/high) — not blocking, but real cleanup scope.
- **Legacy goal float precision** (risk `p1-legacy-goal-float`): `Goal.target_amount` as Float can lose source precision before Phase 1 snapshot normalization — a data-integrity prerequisite for financial correctness in the goal/forecast path.

---

## 3. Non-blocking UI polish (presentation only)

These can be done without any contract, methodology, or policy decision. None of them is required to call the investment logic complete:

| Item | Where | Effort | Impact |
|---|---|---|---|
| `/portfolio` 390px responsive overflow fix (the layout half only) | `ui/app/portfolio` | Small | Removes the measured 407px overflow at 390px |
| Chart/dashboard polish already in the worktree (Sankey, donut, treemap, breakdown, cash-flow, trend, expandable cards, time-range bar) | `ui/components/charts`, `ui/components/dashboard`, several pages | In progress | Visual quality on existing surfaces |
| Legacy product-name cleanup (Finance Copilot, WealthIQ, CashFlix, Finlynq) | Docs + labels | Cosmetic | Brand clarity only |
| Reduced-motion / focus-order refinements on remaining routes not in the ten-route matrix | Various | Small | Accessibility polish beyond the already-passing Axe scans |
| Empty-state copy consistency across investment surfaces | Investment routes | Small | UX consistency |

The ten-route read-only UI-12 matrix already passes at 390/768/1024/1440/1728 with zero serious/critical Axe violations, keyboard reachability, reduced-motion behavior, privacy redactions, no execution vocabulary, and route/payload budgets — so the certified surface set does not need "polish" to be certifiable; it needs the §2.3 blockers closed.

---

## 4. What is genuinely complete today (so the gap list is honest)

- Canonical security identity, market/fundamental/technical/macro/quant contracts (INV-01…07) — complete.
- Committee (INV-08), recommendation (INV-09), bounded CIO projection (INV-10), append-only decisions/outcomes (INV-11), hardening + trusted persistence (HARDEN-01, PERSIST-03) — complete.
- UI-01…08 certified; UI-09 discovery certified for bounded modes; UI-10 certified for the contextual Scout and (after this push) the provider-backed bounded Scout; UI-11 certified for the current-only risk slice.
- One Alembic head (`AB16a1b2c3d4e5`); additive migration with upgrade/downgrade/re-upgrade and immutability tests.
- Ten-route read-only browser matrix (including `/investments/scout`) passing in both degraded-mocked and hermetic live-stack modes.
- No execution capability exists anywhere in the certified set: no broker/order/trade/transfer/rebalance/money-movement routes, controls, or vocabulary — verified by route/request/control scans. This is an intentional design constraint, not a gap.

---

## 5. Dependency ordering (what gates what)

```text
INV-12 evaluation artifact + replay repository          ← 2.1
        ↓
Retention/deletion policy approval (multi-user gate)    ← 2.2
        ↓
UI-12 certification blockers closed                     ← 2.3
        ↓
UI-12 CERTIFIED (final trust gate)
```

Parallel/independent tracks:

```text
UI-10 full-vision adapters   ← requires dedicated server-owned contracts (2.4)
UI-11 advanced risk          ← requires approved methodology + historical inputs (2.5)
INV-10 archive               ← requires a concrete consumer (2.6-optional)
```

The roadmap's stated safe order: preserve certified boundaries → define INV-12 evaluation/replay artifact + retention boundary → implement INV-12 after prerequisite approvals → certify UI-12 → add INV-10 archive only if required. "Do not start UI-12 or INV-12 concurrently."

---

## 6. Things that look like gaps but are intentionally not gaps

- **No execution layer** — by design (hard boundary across all phases; desired chain ends at human decision + outcome).
- **No Monte Carlo / probability-of-outcome model** — intentionally deferred (risk `monte-carlo-deferred`); deterministic projections only.
- **No source-quality numeric scores in Scout** — by design; the contract preserves source identity/provenance for the user to judge.
- **No live third-party provider certification** — external Finnhub/SEC/model behavior stays outside repository-managed certification evidence; hermetic fixtures prove the boundaries.
- **UI-09 "candidates" not being recommendations** — separation is intentional and tested.
- **Scenario Lab ≠ portfolio risk** — intentional goal-scoped semantics.

---

## 7. Recommended next actions (in order)

1. **Commit and push the current worktree** (this report, the UI-10 provider-backed Scout expansion, UI-11 doc corrections, UI-12 audit evidence) so the tracker's UI-10 `in_progress` state becomes accurate-complete with a commit SHA.
2. **Close UI-12 blocker 1**: remediate `/portfolio` responsive overflow and gate its mutation controls; then include it in the certifiable matrix.
3. **Close UI-12 blocker 2**: seed deterministic synthetic owner data in the hermetic harness and rerun populated live-backend proof (or document each backend-dependent route as unavailable).
4. **Close UI-12 blocker 3**: measure CPU interaction budgets for the nine-to-ten-route set.
5. **Define the INV-12 evaluation artifact contract** as a design gate (contract tests only, per the audit's Task G).
6. **Get the retention/deletion policy decision** (product-security) — prerequisite for INV-12 retention slice and multi-user rollout.
7. **Fix the stale migration assertion** in `test_forecast_migration.py` as a bounded cleanup.
8. Only then: **rerun the consolidated UI-12 certification** and record the verdict.

---

## Appendix A — Evidence references

- Tracker phase inventory + work items: `docs/10-roadmap/PROJECT_STATUS.json`; generated `PROJECT_STATUS.md`, `CURRENT_HANDOFF.md`
- UI-12 blockers and matrix: `ATLAS-INVESTMENT-UI-12-READINESS-AND-TRUST-CERTIFICATION-AUDIT.md` (esp. §7, Appendix D/F/G)
- INV-12 contract and blockers: `ATLAS-INVESTMENT-REMAINING-PHASES-AUDIT-AND-EXECUTION-PLAN.md` (INV-12 section)
- UI-11 boundary: `ADR-UI-11-CURRENT-PORTFOLIO-RISK-BOUNDARY.md`
- Route inventory and activation: `ui/lib/informationArchitecture.ts`, `ui/__tests__/e2e/ui12-trust-certification.spec.ts`
- Migration head: `services/rules-service/alembic` (current head `AB16a1b2c3d4e5`)
- Open risks: `risk-frontend-lint-debt`, `risk-monte-carlo-deferred`, `risk-p1-legacy-goal-float`, `risk-p1-retention-rollout-gate`, `risk-ui11-current-only-scope` (tracker)

---

*This report is a read-only assessment; it changes no contracts. Terms like "complete" and "certified" are used only where the repository's own gate documents and test evidence support them, and every limitation named above is carried forward from the authoritative audit records.*