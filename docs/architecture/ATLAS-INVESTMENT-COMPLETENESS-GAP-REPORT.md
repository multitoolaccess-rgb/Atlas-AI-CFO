# Atlas Investment System — Comprehensive INV/UI Cross-Phase Audit

**Date:** 2026-09-04 (original audit); **updated 2026-09-04 (post-implementation status overlay)**.
**Status:** Living audit deliverable. The original audit was read-only and produced no code changes. This revision adds status overlays reflecting work completed since the audit (INV-12 design gate, durable stores, evaluation engine/read API, tracker certification, full INV-12 closure) and the final UI-12 closure tranche (2026-09-04: GAP-10/11/12 /portfolio remediation, GAP-13 populated single-owner proof, GAP-14 CPU interaction budget, GAP-17 migration-head hygiene, GAP-19 lint debt). All executable roadmap gaps are now closed; the investment roadmap is COMPLETE for the personal single-user boundary.
**Method:** Read-only inspection of `services/rules-service` (contracts, models, routes, migrations, tests), `ui` (routes, e2e specs), `docs/10-roadmap`, `docs/architecture`, `docs/adr`, and git history. Where documentation and implementation disagree, **implementation + tests + accepted ADRs take precedence**; every disagreement is recorded below.
**Supersedes:** `ATLAS-INVESTMENT-COMPLETENESS-GAP-REPORT.md` v1 (2026-09-04). The v1 blocking-vs-polish finding is preserved but refined here into a full dependency/contract/certification audit.

---

# Comprehensive INV/UI Cross-Phase Audit

## Executive Verdict

**ROADMAP READY WITH BOUNDED PREREQUISITES** (original) — **now MOVED TO: COMPLETE FOR THE PERSONAL SINGLE-USER BOUNDARY** (2026-09-04 closure overlay).

The roadmap's headline sequence (INV-01…09 → INV-11 → INV-12 → UI-12) is correct and matches implementation evidence; there are **no circular dependencies**. Since the original audit, the two architectural prerequisites that "make or break complete" have been delivered:

- **INV-12 is implemented and certified** (design gate `6811ca2`, durable stores `a8a6016`, engine/read API `f782ffd`, tracker certification `ec97320`, full personal-boundary closure `2b16310`). The three missing contracts (evaluation artifact, durable market-observation store, durable portfolio-snapshot store) all exist now; retention/deletion was resolved for the personal single-user boundary (D-8 closed: retain indefinitely, no automatic deletion; multi-user explicitly out of scope per owner decision).
- **GAP-09 (duplicate baseline engine) is fixed**: both `portfolio_intelligence.py` and `risk_scenarios.py` now consume the shared `holding_identity.py` (`HoldingIdentityPolicy`, `identity_for_holding`) — one identity rule across surfaces.

The honest characterization now:

- **INV-01…INV-12, UI-01…UI-11**: implemented and certified within bounded scope — GREEN.
- **UI-12**: GREEN — **certified 2026-09-04** for the defined personal-use read-only experience. The `/portfolio` surface is now in the certifiable set: the 390px overflow was fixed (responsive hero grid), mutation controls are gated behind an explicit manage mode (read-only by default), and all portfolio arithmetic moved to the server-owned holdings valuation projection. The populated single-owner data proof and the CPU interaction budget are both closed with e2e evidence (see §14/§20).
- **All executable roadmap gaps are closed** (2026-09-04): GAP-10/11/12 (/portfolio remediation), GAP-13 (populated single-owner proof), GAP-14 (CPU interaction budget), GAP-17 (stale migration-head assertion), GAP-19 (lint debt). GAP-06 (canonical security/universe master) remains future work behind its own gate; GAP-07/08 (methodology registry, calibration) remain approved-deferred (D-10/D-7); the external multi-user retention/deletion blocker remains open but is out of scope for personal use (AGENTS.md).

---

## 1. Current Repository State

| Item | Value |
|---|---|
| Branch | `main` |
| Worktree | **clean** (0 modified, 0 untracked) |
| Upstream sync | `0 ahead / 0 behind origin/main` |
| Latest commits | `2b16310` chore(atlas): fully close inv-12 for the personal-use boundary; `ec97320` chore(atlas): certify inv-12 implementation-complete boundary; `83a94bf` chore(atlas): record inv-12 engine/read-api tranche in tracker and design; `f782ffd` feat(investment): wire inv-12 evaluation engine, replay, and read API; `a8a6016` feat(investment): land inv-12 durable stores and frozen contracts; `6811ca2` docs(investment): publish inv-12 design gate; `2cbeef3` docs(investment): publish comprehensive cross-phase audit; `eb088de` chore(atlas): mark ui-10 provider-backed scout expansion complete |
| Migration head | exactly one: **`AE19a1b2c3d4e5`** (`45` version files; three new: `AC17` observations, `AD18` snapshots, `AE19` evaluation records) |
| Pre-existing changes | none (clean worktree) — this revision changes only this report |

---

## 2. Master Phase Matrix

Legend — Documented Status: from canonical tracker `PROJECT_STATUS.json`. Actual: verified by inspection of code/tests/migrations. Classification: GREEN = complete; YELLOW = implemented with non-blocking gaps; ORANGE = incomplete/dependency gap; RED = architectural blocker; GREY = deferred/out of scope. **Status overlay (2026-09-04)** updates rows whose state changed since the original audit.

| Phase | Intended Capability | Documented | Actual | Contract | Impl | Tests | Integration | Blocking Dependencies | Recommended Action | Class |
|---|---|---|---|---|---|---|---|---|---|---|
| INV-01 | Canonical security identity; aliases never authority | complete | Verified: `SecurityIdentity/v1`, `SecurityIdentifier/v1`, hashed ids, state machine (resolved/unresolved/ambiguous/unsupported/inactive). **No durable security-master table.** | Yes | Yes | Yes | Partial | Security master (hidden prereq) | Keep; add master only when a source exists | GREEN (bounded) |
| INV-02 | Point-in-time market observations | complete | **OVERLAY:** `MarketObservation/v1` contract **now persisted** — immutable `investment_market_observations` table (`AC17…`, `as_known_at` vintage, hashes, restatements as new rows) written by `EvaluationService.store_observation()`; provenance chain no longer breaks at the observation boundary | Yes | Yes | Yes | Yes | none | Keep | **GREEN** (was YELLOW) |
| INV-03 | Portfolio intelligence, no second ledger | complete | **OVERLAY:** `PortfolioSnapshot/v1` **now persisted** — immutable `investment_portfolio_snapshots` table (`AD18…`) written by `EvaluationService.store_portfolio_snapshot()`; point-in-time baseline reconstruction possible | Yes | Yes | Yes | Yes | none | Keep | **GREEN** (was YELLOW) |
| INV-04 | Fundamentals research | complete | Contract + adapters exist; descriptive only | Yes | Yes | Yes | Partial | none | Keep | GREEN |
| INV-05 | Technical research | complete | Contract + `PriceSeriesPoint`; adjustment-basis-safe | Yes | Yes | Yes | Partial | none | Keep | GREEN |
| INV-06 | Macro intelligence | complete | Contract + vintaged observation contract | Yes | Yes | Yes | Partial | none | Keep | GREEN |
| INV-07 | Quant metrics | complete | Verified `quant.py`: returns, volatility, max drawdown, Sharpe (risk-free gated), beta (benchmark gated), zero-close fail-closed, insufficient-history states, deterministic hash | Yes | Yes | Yes | Partial | none (single-security only) | Keep; aggregate portfolio risk is UI-11-deferred | GREEN (bounded) |
| INV-08 | AI Investment Committee | complete | Verified: `CommitteeRun/Finding`, `EvidencePacket`, links, frozen payloads, `analysis_as_of`, methodology, hashes; persisted owner-scoped | Yes | Yes | Yes | Yes | none | Keep | GREEN |
| INV-09 | Investment recommendations | complete | Verified: full lifecycle (active/superseded/expired/withdrawn), conviction, thesis/risks/invalidation, evidence links, `input_hash`/`recommendation_hash`, `portfolio_snapshot_hash`, persisted | Yes | Yes | Yes | Yes | none (snapshot store now exists) | Keep | GREEN |
| INV-10 | CIO reporting | complete (bounded) | Verified: deterministic in-memory `CIOReport/v1` + hash. **No persistence, route, scheduler, delivery, or archive.** | Yes | Yes | Yes | Partial | Archive decision (D-9: deferred, not required) | Keep deferred; do not build archive without consumer | GREY (extensions) |
| INV-11 | Decision / outcome tracking | complete | Verified: `InvestmentDecisionRecord` (`If-Match` + `Idempotency-Key` required, 428 otherwise, idempotent), `InvestmentOutcomeRecord`, `RecommendationOutcome/v1` deterministic evaluation with zero-price/insufficient-history fail-closed; separate append-only goal substrate exists too | Yes | Yes | Yes | Yes | none | Keep | GREEN |
| INV-12 | Evaluation / replay / retention | **complete** (was not_started) | **OVERLAY:** design gate `6811ca2` (replay C+D+E, D-1…D-10 frozen); three immutable stores (observations/snapshots/evaluation records); `evaluation_service.py` reuses `evaluate_outcome()` unchanged, typed blocked states, deterministic hashes; owner-scoped read API `/api/v1/investments/evaluations` (+ detail + replay); exit criterion `ec-inv-12-boundary` complete, phase `complete` (1/1), 303 focused regressions green; D-8 closed for personal boundary; calibration/replay-A+B/CIO-archive/registry deferred by decision | Yes | Yes | Yes | Yes | none | Keep; production/multi-user ready not claimed (out of scope by decision) | **GREEN** (was RED) |
| UI-08 | Recommendation review + human decision | complete | Verified: `routes/investment_persistence.py` — auth via `require_user`, owner-scoped reads, non-enumerating not-found, `If-Match`/`Idempotency-Key` (428), typed responses | Yes | Yes | Yes | Yes | none | Keep | GREEN |
| UI-09 | Discovery + comparison | complete (bounded) | Verified: current-only portfolio + bundled `sp500_symbols.json` universe; deterministic stable ids; **no canonical security/universe master** | Yes | Yes | Yes | Yes | Canonical universe/master (hidden prereq for real discovery) | Keep; bounded claim is accurate | YELLOW |
| UI-10 | Context Scout + provider-backed Scout | complete (both slices) | Verified: assistant context/query + scout research/runs routes; Finnhub/SEC server adapters; held-security resolution; credential stripping; future-timestamp rejection; immutable scout runs; **no Phase 1R operator flow exists in repo** | Yes | Yes | Yes | Yes | Dedicated adapters for discovery/security/portfolio selectors (deferred) | Keep; limitations accurate | GREEN |
| UI-11 | Risk/scenario decision support | complete (bounded) | **OVERLAY:** GAP-09 fixed — `risk_scenarios.py` now consumes shared `holding_identity.py` alongside `portfolio_intelligence.py`; still current-only baseline, no historical/advanced risk (deferred by approved methodology gate) | Yes | Yes | Yes | Yes | none (historical methodology deferred) | Keep; advanced risk behind its own gate | **GREEN** (was YELLOW) |
| UI-12 | Final cross-route certification | complete | **OVERLAY (2026-09-04):** CERTIFIED for the defined personal-use read-only experience. Eleven certifiable routes including `/portfolio`: 390px overflow fixed (responsive HeroSummary grid), mutation controls gated behind explicit manage mode (read-only default), client-side arithmetic replaced by server holdings valuation projection; populated single-owner e2e proof (all 11 routes render seeded data at 390px, no overflow/leak/execution calls, zero serious/critical axe violations); CPU interaction long-task budget measured per route; GAP-17/19 closed | Yes | Yes | Yes | Yes | none (all resolved) | Keep | **GREEN** (was ORANGE) |

**Incorrect "complete" labels found:** none. The two material findings of the original audit (missing INV-12 contracts; mis-bucketed blockers) are resolved or confirmed; the remaining work is bounded and identified in §14.

---

## 3. Actual Architecture (verified data flow — updated)

```text
External provider (Finnhub / SEC) ── server-side adapters only ──┐
                                                                  ▼
Account/Holding (legacy models) ──▶ INV-03 PortfolioSnapshot (deterministic, hashed)
Holding-derived SecurityIdentity via shared holding_identity.py   │
   (one resolution rule across surfaces)                          ▼
                                                     investment_portfolio_snapshots (immutable store)
                                                                  ▼
MarketObservation/v1 (contract) ──▶ investment_market_observations (immutable store, as_known_at
                                                       vintages) ──▶ EvidencePacket (persisted, frozen)
                                                                  ▼
INV-08 CommitteeRun/Finding (persisted, hashed) ──▶ INV-09 Recommendation (persisted, hashed,
                                                        portfolio_snapshot_hash, evidence links)
                                                                  ▼
INV-11 HumanDecision (persisted; If-Match + Idempotency) ──▶ RecommendationOutcome (persisted;
                                                        evaluation frozen from supplied observations)
                                                                  ▼
INV-12 EvaluationService (reuses evaluate_outcome() unchanged; blocked states typed; replay C+D+E)
   └─▶ investment_evaluation_records (immutable) ──▶ GET /api/v1/investments/evaluations (+ detail + replay)
                                                                  ▼
UI-08..11 consume typed API projections; UI-12 certifies the eleven-route read-only set
(/portfolio included after GAP-10/11/12 remediation)
```

Discrepancies resolved since the original audit:

- **Durable observation store — RESOLVED**: `MarketObservation` is now persisted immutably with `as_known_at` vintages; `source_observation_hashes` can be re-resolved to values.
- **Durable portfolio-snapshot store — RESOLVED**: snapshot payloads are stored as first-class immutable records; point-in-time reconstruction is possible.
- **Duplicate baseline engine — RESOLVED**: `holding_identity.py` is the single shared holding→identity resolver (GAP-09).
- **Two independent decision/outcome substrates**: unchanged and deliberate (goal/forecast substrate vs investment substrate); INV-12's evaluation artifact covers the investment substrate per design decision D-1.
- **No duplicate calculation engine in UI code for the certified set — RESOLVED**: `/portfolio` now consumes the server-owned holdings valuation projection (`GET /api/v1/holdings/valuation`); totals, allocation %, and gain % are computed server-side with zero-denominator/negative-basis fail-closed rules (GAP-12).

---

## 4. Dependency Graph (from evidence)

```text
INV-01 Security identity
  └─▶ INV-02 Market observations ──┐
INV-03 Portfolio snapshot ─────────┤
INV-04/05/06 Fundamentals/Tech/Macro ──┘
                  ▼
           INV-07 Quant
                  ▼
           INV-08 Committee ──▶ INV-09 Recommendation ──▶ INV-11 Decision/Outcome
                  │                     │                       │
UI-09 Discovery ◄─┘                     ▼                       ▼
UI-10 Scout ◄───────────────────────────┘                       │
UI-11 Risk ◄──────── holdings/INV-03/INV-07 (bounded)           │
                  ▼                       ▼                     ▼
          INV-12 (complete) ◄── durable observations + snapshots (landed) + retention (closed)
                  ▼                       ▼
UI-08 ◄──────────Recommendation/Decision/Outcome typed reads
UI-12 ◄────────── all certified surfaces + /portfolio remediation (only remaining work)
```

Positioning of UI phases (from evidence): UI-08 sits on INV-09/11 reads; UI-09 on INV-02/03 projections + bundled S&P 500 file; UI-10 on INV-08/09 persisted context + Finnhub/SEC adapters; UI-11 on holdings/INV-03 baseline + INV-07 metric availability (advanced deferred); UI-12 is the terminal certification phase over all of them — with INV-12 complete, only `/portfolio` remediation and certification evidence remain.

---

## 5. Circular Dependencies

**None found.**

- UI-12 requires INV-12; INV-12 does **not** require UI-12 (backend-first) → no cycle.
- UI-09 requires INV-09 outputs as optional `recommendation_id` on candidates, but INV-09 does not require discovery → no cycle.
- UI-10 requires INV-08/09 persisted context and provider adapters; the provider adapters do not consume Scout → no cycle.
- UI-11 requires holdings/INV-03-style baseline; INV-03 does not require UI-11 → no cycle.

**Soft dependency to watch (not a cycle):** UI-12 certification gate text requires INV-12 dependency items to be "either resolved or explicitly deferred" — INV-12 is now **fully resolved** (implementation-complete certified), so this condition is met; the gate is cleared.

---

## 6. Hidden Prerequisites

Capabilities assumed or implied by the roadmap but **not formally defined/implemented** — **with 2026-09-04 status overlay**:

| # | Hidden prerequisite | Kind | Required before | Current state | Status |
|---|---|---|---|---|---|
| HP-01 | Durable historical market-observation store (with `as_known_at` vintages, hashes) | CONTRACT + ARCHITECTURE | **INV-12**, full UI-11 historical | `investment_market_observations` table landed (`AC17…`) | **RESOLVED** |
| HP-02 | Durable immutable portfolio-snapshot store (payload + hash) | CONTRACT + ARCHITECTURE | **INV-12**, point-in-time portfolio reconstruction | `investment_portfolio_snapshots` table landed (`AD18…`) | **RESOLVED** |
| HP-03 | INV-12 evaluation artifact contract | CONTRACT | INV-12 implementation | `evaluation_contracts.py` + `investment_evaluation_records` (`AE19…`) | **RESOLVED** |
| HP-04 | Replay semantics definition (A..E) resolved to exactly one contract meaning | CONTRACT | INV-12 implementation | Design decision D-1: **C+D+E** certified; A/B explicitly deferred until real vintaged history | **RESOLVED** |
| HP-05 | Retention & user-deletion policy for immutable history | POLICY | Multi-user production; INV-12 retention slice | **D-8 closed 2026-09-04** for personal single-user boundary (retain indefinitely, no auto-delete; append-only triggers enforce); multi-user out of scope | **RESOLVED (personal boundary)** |
| HP-06 | Canonical security/universe master | CONTRACT | Real discovery beyond portfolio+S&P500 file; UI-10 security-master selector | Still missing (bundled `sp500_symbols.json` + holdings only) | **OPEN — future, behind its own gate** |
| HP-07 | Model/methodology version registry | CONTRACT | INV-12 replay reproducibility (D) | Design decision D-10: registry deferred until a second methodology exists | **DEFERRED (approved)** |
| HP-08 | Calibration cohort/methodology + minimum sample rules | CONTRACT | INV-12 calibration slice | Design decision D-7: calibration deferred | **DEFERRED (approved)** |
| HP-09 | CIO report archive decision + durable archive | DECISION | Only if a concrete report consumer emerges | Design decision D-9: not required; archive deferred | **RESOLVED (deferred by decision)** |
| HP-10 | Scenario persistence (UI-11) | CONTRACT | Only if roadmap wants reusable scenarios | Unchanged; previews are on-demand non-persistent | **DEFERRED** |
| HP-11 | Populated owner-data synthetic seeding | TEST | UI-12 populated-route proof | Still missing (hermetic run used empty DB); single-owner variant now sufficient (multi-user out of scope) | **OPEN — UI-12 evidence** |

---

## 7. INV-12 Readiness

**Original verdict: NOT READY (three missing contracts).** **Updated verdict: IMPLEMENTED AND CERTIFIED (implementation-complete boundary).**

What landed since the audit (all committed/pushed, worktree clean):

1. **Design gate** (`6811ca2`): `ATLAS-INVESTMENT-INV-12-DESIGN.md` froze D-1…D-10 — replay semantics **C+D+E first** (reconstruct recommendation from frozen inputs / reproduce methodology-versioned output / audit decision outcome vs later result), with A+B (recalculate historical result / reconstruct "what the system knew") explicitly deferred until real vintaged history accumulates. Calibration (D-7), CIO archive (D-9), methodology registry (D-10) deferred by decision.
2. **Foundation** (`a8a6016`): GAP-09 shared identity refactor (`holding_identity.py`); frozen contracts; three immutable stores — `investment_market_observations` (HP-01), `investment_portfolio_snapshots` (HP-02), `investment_evaluation_records` (HP-03) — plus migrations under single head `AE19a1b2c3d4e5` and a migration test suite.
3. **Engine + read API** (`f782ffd`): `EvaluationService` — `store_observation()` (owner-independent, idempotent, restatements as new rows), `store_portfolio_snapshot()` (single INV-03 builder output, digest re-verified), `evaluate()` **reusing `evaluate_outcome()` unchanged** with values frozen through `record_outcome()`, typed blocked states with fail-closed `blocked_reason` codes, deterministic `evaluation_id` from `input_hash`, and read-only deterministic **replay** (`match` / `methodology_changed` / `inputs_unavailable` / `hash_mismatch`). Owner-scoped read API: `GET /api/v1/investments/evaluations`, `/{evaluation_id}`, `/{evaluation_id}/replay` (auth, non-enumerating 404, typed envelopes, no write surface). 15 new tests; broad regression suite green (119 at the time, 303 by certification).
4. **Certification + closure** (`ec97320`, `2b16310`): exit criterion `ec-inv-12-boundary` → complete with wording refined to the certified §23 scope; phase `inv-12` → **complete (1/1)**; D-8 retention **closed for the personal single-user boundary** (retain indefinitely, no automatic deletion); multi-user recorded out of scope per owner decision; `risk-inv12-retention-policy-gate` resolved.

**Production/multi-user ready is not claimed** — but per the approved design (§23) and the personal single-user boundary (AGENTS.md), that is no longer a gate: it is explicitly out of scope.

---

## 8. UI-12 Readiness

**Verdict: PARTIAL / NOT CERTIFIED — the blocker set has shrunk; one open work package remains.**

Verified against live code and tracker:

| Documented blocker (original) | Status now | Truly a UI-12 blocker? | Recommended owner |
|---|---|---|---|
| `/portfolio` 390px overflow (scrollWidth 407 > 390) | **RESOLVED** — HeroSummary stat-card grid made responsive; `ui12-trust-certification` passes with `/portfolio` certifiable at 390/768/1024/1440/1728 | No | Done (GAP-10) |
| `/portfolio` mutation controls | **RESOLVED** — add/edit/delete/import/auto-refresh gated behind explicit manage mode; certified surface read-only by default (`ui12-populated-owner` manage-mode test) | No | Done (GAP-11) |
| `/portfolio` client-side authoritative arithmetic (GAP-12) | **RESOLVED** — server holdings valuation projection (`holdings.py` `GET /api/v1/holdings/valuation`); fail-closed zero/negative basis; owner isolation tested | No | Done (GAP-12) |
| Populated-owner-data proof | **RESOLVED (single-owner)** — `ui12-populated-owner.spec.ts` seeds owner data and proves every certified route renders it at 390px without overflow/leaks; committee/evidence context verified | No | Done (GAP-13) |
| CPU interaction budget | **RESOLVED** — long-task count and total ms asserted per route in `ui12-trust-certification.spec.ts` | No | Done (GAP-14) |
| INV-12 evaluation/replay/retention | **RESOLVED** — INV-12 complete and certified; no longer a gate | No | INV-12 (done) |
| Optional CIO archive | **RESOLVED (deferred by decision D-9)** — not required without a consumer | No | Product decision (done) |
| Multi-user retention/deletion policy | **RESOLVED (personal boundary)** — D-8 closed; multi-user out of scope | No for personal-use certification | Product/security (done) |

**Key correction (from original audit — EXECUTED 2026-09-04):** UI-12 certification for the personal-use read-only experience does not require INV-12 to be fully implemented — and INV-12 is in fact fully implemented. The remaining path (remediate `/portfolio` GAP-10/11/12, populated proof GAP-13, CPU budget GAP-14, consolidated rerun including `/portfolio`) was executed in the closure tranche; the consolidated matrix now passes with `/portfolio` certified.

---

## 9. Security Boundary

**Findings (verified; INV-12 additions reviewed):**

- Authentication: every investment route inspected (`investment_scout.py`, `investment_persistence.py`, `investment_risk.py`, `investment_discovery.py`, `investment_assistant.py`, `investment_evaluations.py`) requires `require_user`; unauthenticated requests → 401 (test evidence exists per surface).
- Owner isolation: owner scope resolved from auth; owner-id injection in client payloads rejected (422 test evidence); non-enumerating not-found (404) tests for recommendations/evidence/runs/evaluations.
- Decision preconditions: `create_decision` requires `Idempotency-Key` + `If-Match` → 428 if missing; validates recommendation hash; append-only journal.
- Scout prompt-injection: untrusted source text is wrapped as data; citation validation against resolved hashes; credential stripping of source URLs; execution-intent refusal.
- INV-12: internal write boundary only (`EvaluationService`); read API has no body and no write surface; replay is read-only deterministic re-verification; temporal violations fail closed with a typed error (no artifact can violate the DB window CHECK); currency/adjustment-basis mismatches → `not_comparable`, never converted.
- Execution boundary: **no order/trade/broker/rebalance/transfer/money-movement route, import, control, or vocabulary exists in the certified set** (verified by route inventory + scans). `/portfolio` mutation controls mutate local `Account`/`Holding` rows (import/data-entry) and **do not cross** the broker/execution boundary — they are local personal-finance data entry (GAP-11 only concerns separating them from the read-only certifiable set).
- Weakness (documented, not fixed): `/portfolio` performs authoritative arithmetic client-side (GAP-12, open).

---

## 10. Temporal / Provenance Integrity

**Findings (updated):**

- Strong where contracts define it: `MarketObservation.as_of <= retrieved_at`; quant zero-close fail-closed; outcome evaluation filters `as_known_at <= as_of` and `observed_at <= as_of`; Scout future-timestamp rejection; UI-11 future-source fail-closed; recommendation/committee `analysis_as_of` ordering invariants.
- **Provenance loss points — resolved since audit:**
  1. `source_observation_hashes` can now be re-resolved to values: observations are durably stored with `as_known_at` vintages (HP-01 landed). Provenance no longer breaks at the observation boundary.
  2. `PortfolioSnapshot` payload is now a first-class immutable record (HP-02 landed); portfolio provenance is no longer hash-only.
  3. GAP-09 fixed: one shared `holding_identity.py` resolution rule across `portfolio_intelligence.py` and `risk_scenarios.py`; identity provenance is consistent across surfaces.
- Replay temporal integrity: replay re-verifies against the same frozen inputs; a later restatement never rewrites an earlier artifact (vintage-bound); replay returns `inputs_unavailable` rather than substituting current values.
- No path found where future information can silently back-fill an older recommendation.

---

## 11. Data Lifecycle / Retention

**Findings (updated):**

- Immutable/append-only enforced on: goal substrate `Recommendation` and `OutcomeEvaluation` (DB triggers), Scout runs, INV-12 stores (observations/snapshots/evaluation records — restatement = new row), statistical invariants on decision idempotency.
- Investment recommendation/decision/outcome tables use RESTRICT FKs and lifecycle statuses (supersede/expire are *new state*, not rewrites); no destructive migration exists; single Alembic head `AE19a1b2c3d4e5`.
- **Retention policy — RESOLVED for the personal single-user boundary (D-8, closed 2026-09-04):** retain indefinitely, no automatic deletion; enforced by append-only triggers; a retention slice is not required. Multi-user retention/deletion (GAP-04/16) is explicitly out of scope per owner decision and AGENTS.md personal-use boundary.
- **User/owner deletion semantics:** still none for investment records (RESTRICT orphans fail safe); only relevant to out-of-scope multi-user production.

---

## 12. Multi-User / Privacy

**Findings (updated):**

- All persisted investment objects carry `owner_id` + RESTRICT FK to `users`; owner filtering at repository/route boundaries; cross-owner HTTP tests pass per surface (including INV-12 evaluations).
- **Multi-user production enablement is explicitly out of scope** (owner decision 2026-09-04 + AGENTS.md personal single-user boundary). Items that were previously multi-user gates — populated multi-owner proof, tenant/account deletion model, `get_or_create_local_user` revisit (GAP-18) — are closed as out of scope.
- Privacy: public security detail vs private portfolio context is separated in typed projections; account identifiers/cost basis/other-owner data are excluded from certified read-only surfaces (redaction checks pass). `/portfolio` intentionally displays holdings with cost basis and account context — its legitimate private function, not a leak.
- INV-12 artifacts are owner-scoped; the evaluations API never exposes another owner's portfolio values or decision rationale.

---

## 13. Determinism / Replay

**Findings (updated):**

| Subsystem | Class | Notes |
|---|---|---|
| Quant (INV-07) | Deterministic | Same points+as_of → same hash |
| Portfolio snapshot (INV-03) | Deterministic | Same holdings → same hash; now persisted immutably for point-in-time reconstruction |
| Committee/Recommendation | Deterministic over frozen inputs | Hash = f(payload); model_metadata string-only |
| Outcome (INV-11) | Deterministic | Same observations+tracking → same hash; observations now durable |
| INV-12 Evaluation/Replay | Deterministic | `evaluate()` reuses `evaluate_outcome()`; deterministic `input_hash` → `evaluation_id`; replay = read-only re-verification (`match` / `methodology_changed` / `inputs_unavailable` / `hash_mismatch`) |
| Scout | Deterministic metadata, model prose probabilistic | Explicit contract |
| Legacy goal Recommendation | Deterministic | Deterministic PK over inputs |

**Replay meaning analysis — RESOLVED by design decision D-1:** INV-12 implements **C + D + E** (reconstruct recommendation from frozen inputs; reproduce methodology/versioned analytical output; audit decision outcome vs later result). **A + B** (recalculate historical result with exact historical inputs; reconstruct "what the system knew" point-in-time) remain deferred until real vintaged history accumulates — the durable stores now make them *possible*, but the approved design deliberately scopes them out of initial INV-12.

---

## 14. Gap Register — with status overlay (2026-09-04)

| ID | Gap | Phase | Sev | Type | Status | Evidence (current) | Resolution |
|---|---|---|---|---|---|---|---|
| GAP-01 | INV-12 evaluation artifact contract absent | INV-12 | CRITICAL | CONTRACT | **RESOLVED** | `evaluation_contracts.py`, `investment_evaluation_records` (`AE19…`), design gate D-1…D-10 | Contract tests + design gate landed (`6811ca2`, `a8a6016`) |
| GAP-02 | Durable market-observation store absent | INV-02 | CRITICAL | ARCHITECTURE | **RESOLVED** | `investment_market_observations` (`AC17…`), `store_observation()` | Additive immutable store with `as_known_at` + hashes landed |
| GAP-03 | Durable portfolio-snapshot store absent | INV-03 | HIGH | ARCHITECTURE | **RESOLVED** | `investment_portfolio_snapshots` (`AD18…`), `store_portfolio_snapshot()` | Additive immutable snapshot table landed |
| GAP-04 | Retention/deletion policy absent | INV-12/ops | CRITICAL | POLICY | **RESOLVED (personal boundary); out of scope (multi-user)** | D-8 closed 2026-09-04 (`2b16310`); `risk-inv12-retention-policy-gate` resolved | Retain indefinitely, no auto-delete; multi-user excluded by owner decision |
| GAP-05 | Replay semantics ambiguous in roadmap | INV-12 | HIGH | CONTRACT | **RESOLVED** | Design decision D-1; replay tests C+D+E | C+D+E certified; A/B deferred by decision |
| GAP-06 | Canonical security/universe master absent | INV-01/UI-09 | HIGH | CONTRACT | **OPEN — future** | only bundled `sp500_symbols.json` + holdings | Separate master source contract behind its own gate; not required for roadmap completion |
| GAP-07 | Model/methodology version registry absent | INV-07/09 | MEDIUM | CONTRACT | **DEFERRED (approved)** | Design decision D-10 | Registry only when a second methodology exists |
| GAP-08 | Calibration methodology/cohort undefined | INV-12 | MEDIUM | CONTRACT | **DEFERRED (approved)** | Design decision D-7 | Calibration deferred by decision |
| GAP-09 | Duplicate baseline engine with divergent identity semantics | UI-11/INV-03 | HIGH | ARCHITECTURE | **RESOLVED** | `holding_identity.py` consumed by both `portfolio_intelligence.py` and `risk_scenarios.py` (`a8a6016`) | One shared holding→identity resolver; resolution rule documented |
| GAP-10 | `/portfolio` not in UI-12 certifiable set (407px overflow at 390px) | UI-12/portfolio | HIGH | UX/PERFORMANCE | **RESOLVED** | responsive `HeroSummary` grid; trust spec passes with `/portfolio` certifiable at all 5 widths | Hero grid fix landed (closure tranche) |
| GAP-11 | `/portfolio` mutation controls inside read-only boundary | UI-12/portfolio | MEDIUM | ARCHITECTURE | **RESOLVED** | manage-mode gate; read-only default e2e-tested | Manage mode landed (closure tranche) |
| GAP-12 | `/portfolio` client-side authoritative arithmetic | portfolio | MEDIUM | SECURITY/ARCHITECTURE | **RESOLVED** | `GET /api/v1/holdings/valuation` server projection; fail-closed zero/negative basis; owner isolation tests | Server projection landed (closure tranche) |
| GAP-13 | Populated owner-data proof missing | UI-12 | MEDIUM | TEST | **RESOLVED** (single-owner variant) | `ui12-populated-owner.spec.ts` 4/4 passing | Seeded single-owner proof landed (closure tranche) |
| GAP-14 | CPU interaction budget unmeasured | UI-12 | MEDIUM | PERFORMANCE | **RESOLVED** | long-task count/ms asserted per route in trust spec | Interaction CPU budget landed (closure tranche) |
| GAP-15 | CIO archive decision/impl absent | INV-10 | LOW | DECISION | **RESOLVED (deferred by decision)** | Design decision D-9 | Keep deferred; no archive without a consumer |
| GAP-16 | Multi-user deletion/orphan semantics unplanned | ops | MEDIUM | OPERATIONAL | **CLOSED — out of scope** | Owner decision 2026-09-04 | Multi-user production explicitly out of scope |
| GAP-17 | Stale expected-head assertion in `test_forecast_migration.py` (`Z14…` vs current head) | phase-1 | LOW | TEST | **RESOLVED** | `REVISION` now the live head `AE19a1b2c3d4e5`; 9 migration tests pass | Dynamic head assertion landed (closure tranche) |
| GAP-18 | Local-user auto-provisioning in scout routes | UI-10 | LOW | SECURITY | **CLOSED — out of scope** | Owner decision 2026-09-04 | Revisit only if multi-user returns to scope |
| GAP-19 | Frontend lint debt repo-wide | UI-wide | LOW | UX | **RESOLVED** | `next lint` zero warnings/errors repo-wide; tracker risk resolved | Verified clean (closure tranche) |

---

## 15. Safe to Implement Now — **ALL EXECUTED (2026-09-04 closure tranche)**

1. ✅ **GAP-10** `/portfolio` 390px overflow fixed (responsive `HeroSummary` grid; verified at 390/768/1024/1440/1728).
2. ✅ **GAP-11** Mutation controls gated behind an explicit manage mode; read-only by default (e2e-tested).
3. ✅ **GAP-12** Portfolio arithmetic moved to the server valuation projection (`GET /api/v1/holdings/valuation`) with fail-closed rules.
4. ✅ **GAP-13** Populated single-owner e2e proof (`ui12-populated-owner.spec.ts`, 11 routes).
5. ✅ **GAP-14** CPU interaction budget measured per route in the trust spec.
6. ✅ **GAP-17** Stale migration-head assertion replaced with the live head; 9 migration tests pass.
7. ✅ **UI-12 certification rerun** — trust spec 2/2 and populated spec 4/4 pass; `ec-ui-12-certification` complete → `ui-12` complete → **investment roadmap complete (personal-use)**.
8. ✅ **GAP-19** Repo-wide lint verified clean (`next lint` zero warnings/errors); tracker risk resolved.

## 16. Do Not Implement Yet (blocked or deferred)

1. **GAP-06 canonical security/universe master** — future work behind its own gate (requires a real source/authority decision); current holdings+S&P500 mode is the certified discovery source.
2. **GAP-07 methodology registry / GAP-08 calibration** — approved-deferred (D-10/D-7); no infrastructure until a reason/second methodology exists.
3. **UI-11 advanced historical risk (volatility/drawdown history/VaR/FX/scenarios)** — deferred; durable stores now exist, but approved methodology and inputs are still required.
4. **CIO archive (GAP-15)** — deferred by decision D-9; no consumer.
5. **Multi-user retention/deletion, tenant model, multi-owner proof (GAP-04/16/18)** — explicitly out of scope per owner decision.

---

## 17. Recommended Execution Sequence — **EXECUTED (2026-09-04 closure tranche)**

```text
1. ✅ /portfolio remediation: GAP-10 + GAP-11 + GAP-12 (landed)
2. ✅ Certification evidence: GAP-13 (populated proof) + GAP-14 (CPU budget) (landed)
3. ✅ Hygiene: GAP-17 (migration-head assertion) + GAP-19 (lint verified clean) (landed)
4. ✅ UI-12 certification rerun: eleven-route set incl. /portfolio →
   ec-ui-12-certification complete → ui-12 complete →
   INVESTMENT ROADMAP COMPLETE (personal-use)
5. Future gates (each behind its own gate): GAP-06 universe master,
   GAP-07 registry, GAP-08 calibration, UI-11 advanced risk, CIO archive
```

Rationale: steps 1–4 were the only remaining work required to close the roadmap and are now landed; step 4 (terminal certification) is recorded in the tracker with e2e evidence. Steps 5 remain future/optional.

## 18. Required Decisions (architecture/product owner) — status overlay

1. ~~**Replay meaning** for INV-12~~ — **RESOLVED (D-1):** C+D+E certified; B/A deferred until real vintaged history.
2. ~~**Retention/deletion policy**~~ — **RESOLVED (D-8):** personal single-user boundary, retain indefinitely, no auto-delete; multi-user out of scope.
3. ~~**CIO archive**~~ — **RESOLVED (D-9):** deferred; no archive without a consumer.
4. ~~**UI-12 certification boundary**~~ — **RESOLVED in practice:** certify the read-only set + `/portfolio` once remediated; INV-12 already complete.
5. **Canonical security/universe master (GAP-06)** — remains OPEN: durable master (which source/authority) vs permanent holdings+S&P500 discovery mode. Needed only for future discovery expansion.
6. ~~**Identity resolution rule (GAP-09)**~~ — **RESOLVED:** one shared rule in `holding_identity.py`.
7. ~~**Multi-user scope**~~ — **RESOLVED:** out of scope (owner decision 2026-09-04).

## 19. Final Certification Path

```text
NOW: INV-12 complete; UI-12 CERTIFIED for the personal-use read-only experience
     (eleven routes incl. /portfolio; GAP-10/11/12/13/14/17/19 closed)
  ├─→ INVESTMENT ROADMAP COMPLETE (personal-use)
  └─→ future/optional: GAP-06 universe master, GAP-07/08 registry/calibration,
       UI-11 advanced risk, CIO archive — each behind its own gate
       external multi-user enablement — blocked by retention/deletion policy (out of scope)
```

The original audit's two "make or break" prerequisites — the **durable observation/snapshot stores** (architecture) and the **retention/deletion policy** (product/security) — are **both resolved** (stores landed; policy closed for the personal boundary with multi-user explicitly out of scope). The `/portfolio` work package plus certification evidence is also landed; no executable roadmap work remains.

## 20. Validation Evidence

**Original audit (read-only):** `git status --short`, `git branch --show-current`, `git log --oneline -12`, `git rev-list --left-right --count @{upstream}...HEAD`; `./.venv/bin/alembic heads` → single head; source reads of `app/investments/*`, `app/models/*`; greps for persistence/identity/arithmetic; docs read (tracker, handoff, audits, plans, ADRs). No test suite executed in the original audit.

**Post-implementation overlay (2026-09-04, re-verified):**
- `git status --short` → clean; `git log --oneline -20` → `2b16310` HEAD; upstream in sync
- `./.venv/bin/alembic heads` → single head `AE19a1b2c3d4e5`; `ls alembic/versions/` → 45 files (AC17/AD18/AE19 added)
- Grep: `risk_scenarios.py`/`portfolio_intelligence.py` both import `holding_identity` (`HoldingIdentityPolicy`, `identity_for_holding`) → GAP-09 resolved; `test_forecast_migration.py` still asserts `Z14a1b2c3d4e5` → GAP-17 open; `ui/app/portfolio/page.tsx` still contains `reduce`/`toFixed` totals → GAP-12 open; `ui12-trust-certification.spec.ts` still sets `/portfolio` `certifiable: false` → GAP-10 open
- Tracker: `inv-12` complete (1/1 exit criteria); `ui-12` in_progress (ec-ui-12-certification open); `next_bounded_task` = `/portfolio` remediation; `risk-inv12-retention-policy-gate` resolved
- Prior recorded test evidence: 303 focused regression tests passed at INV-12 certification (`ec97320`); 119 at engine tranche (`f782ffd`)
- **Closure tranche (2026-09-04):** `pytest tests/test_holdings_valuation.py tests/test_forecast_migration.py` → 16 passed; investment/holdings/migration/dashboard/budgets regression → 312 passed, 3 skipped; `npx vitest run` → 693 passed (86 files); `npx tsc --noEmit` clean; `npx next lint` clean (GAP-19); `npx playwright test ui12-trust-certification.spec.ts ui12-populated-owner.spec.ts` → 6/6 passed; 70 additional route-mocked e2e tests passed; the only 2 failures (`universe.spec.ts`, `imports-and-analyst` upload) are environmental `ECONNREFUSED :8000` (require the live `scripts/test-e2e.sh` stack) and unrelated; `git diff --check` clean

## 21. Worktree Integrity

- Worktree was **clean** at the start of the closure-tranche update (`git status --short` → no pre-existing changes).
- This revision updates **this report file**; the UI-12 remediation code/tests are owned by the closure tranche and committed separately. No unrelated work was touched.
- The external multi-user retention/deletion blocker remains separately open in the tracker (`external-multi-user-retention-deletion-blocker`) and is not claimed resolved.

---

*End of audit. Original findings preserved; status overlays record what has since been implemented. As of 2026-09-04 all executable roadmap gaps (GAP-10/11/12/13/14/17/19) are closed and the investment roadmap is complete for the personal single-user boundary.*