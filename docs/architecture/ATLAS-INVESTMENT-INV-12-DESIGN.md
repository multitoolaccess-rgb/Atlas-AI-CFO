# INV-12 Design Gate — Evaluation, Replay, Historical Evidence & Retention

**Status:** DESIGN ONLY. No production code, migration, API, route, UI, existing contract, or test was changed. The only repository modifications are this design document and the gate prompt (`ATLAS-INVESTMENT-INV-12-DESIGN-GATE-PROMPT-v2.md`).
**Date:** 2026-09-04
**Gate executed against:** `ATLAS-INVESTMENT-INV-12-DESIGN-GATE-PROMPT-v2.md` (v2), with `ATLAS-INVESTMENT-COMPLETENESS-GAP-REPORT.md` as the audited starting point.
**Source precedence applied:** (1) accepted ADRs and committed implementation contracts/tests, (2) `docs/10-roadmap` tracker and remaining-phases audit, (3) planning documents. Every disagreement found is recorded inline rather than silently resolved.
**Evidence verification performed (read-only):** all of GAP-01..05, 07, 08, 09, 15, 16 in the audit were re-verified against source before designing around them. Notable live confirmations are recorded in §1.

---

## Executive Verdict

**GO WITH EXPLICIT PRODUCT DECISIONS → GO (implementation-ready) after owner approvals of 2026-09-04**

The INV-12 architecture is defined and implementation-ready for a **bounded first slice (replay meanings C + D + E over the frozen investment substrate)**. The three prerequisite contracts are designed in this document with full delta analyses against the existing `investment_*` persistence layer.

**Owner approvals recorded (2026-09-04):**

| Decision | Approved disposition |
|---|---|
| **D-1** — Substrate scope | **Investment substrate only** — APPROVED; goal-substrate IDs never appear in investment artifacts |
| **D-2** — Security-identity rule | **`atlas-security`/`RESOLVED` for symbol + known instrument type; else `atlas-unresolved` and ineligible for storage/evaluation; exact string equality; GAP-09 shared-identity refactor scheduled BEFORE store population** — APPROVED |
| **D-3** — Replay semantics | **C + D + E now; A + B deferred** until real observation history exists — APPROVED |
| **D-7** — Calibration | Explicitly deferred; no calibration infrastructure (inside the approved C+D+E scope) |
| **D-8** — Retention | Architecture position approved: **no automatic deletion; delete = policy-designed soft-tombstone later**; implementation-complete proceeds while retention durations/deletion semantics stay an open PRODUCT/SECURITY decision gating the retention slice and production-ready claim |
| **D-9** — CIO archive | NOT REQUIRED unless a concrete consumer dependency appears |

The recommended next Codex task is stated in §26. **Nothing in this gate was implemented; nothing was committed or pushed.**

---

## 1. Existing Architecture Reviewed (verified, not assumed)

### 1.1 Substrates — two independent recommendation/decision/outcome chains (D-1 input)

1. **Goal/forecast substrate (Phase 1–3, personal finance).** `app/models/recommendation.py` (`Recommendation`), decision journal entries, and `app/models/outcome_evaluation.py` (`OutcomeEvaluation`). Append-only enforced by SQLite+PostgreSQL `BEFORE UPDATE`/`BEFORE DELETE` triggers (migration `T8a1b2c3d4e5_add_decision_journal_substrate.py`). Deterministic PKs over canonical inputs; **hash-only** outcome evidence (`evidence_reference_hash`); USD fail-closed (`currency = 'USD'`); ownership triggers (`recommendations_goal_owner`) make cross-user rows impossible.
2. **Investment substrate (INV-08..11).** `app/models/investment_persistence.py`: `investment_committee_runs`, `investment_committee_findings`, `investment_evidence_packets`, `investment_recommendation_records`, `investment_decision_records`, `investment_outcome_records`, plus evidence link tables. Owner `RESTRICT` FKs, `(owner_id, logical_id)` unique constraints, lowercase-64-hex hash CHECK constraints, ID-shape CHECK constraints. No DB immutability triggers on these tables (immutability is service-enforced); the scout tables (migration `AB16a1b2c3d4e5`) added the immutable-run migration test precedent.

### 1.2 Verified findings the design depends on

| Audit claim | Live verification |
|---|---|
| GAP-01: no evaluation artifact | No INV-12 module, contract, table, or test exists. `RecommendationOutcome/v1` is an INV-11 outcome, not an INV-12 artifact (remaining-phases audit: "needs an explicit evaluation artifact, not merely an outcome row"). |
| GAP-02: no durable observation store | `app/investments/market_observations.py` defines `MarketObservation/v1` **contract-only** (Pydantic; no table, no `as_known_at`). `app/investments/outcome_tracking.py` defines a **second, different** `MarketObservation` (fields `observation_hash, security_id, price, observed_at, as_known_at, state`). Grep found no observation table anywhere. |
| GAP-03: no durable portfolio-snapshot store | `PortfolioSnapshot/v1` (`app/investments/portfolio_intelligence.py`) is computed on demand and never persisted; `investment_recommendation_records` stores only `portfolio_snapshot_hash`. |
| GAP-05: replay semantics ambiguous | Roadmap lists A–E without choosing; §4 resolves. |
| GAP-07: version strings, no registry | Methodology versions embedded per module (`investment-outcome/v1`, `quant-calculations/v1`, `cio-report/v1`, …); no registry table. |
| GAP-08: calibration undefined | No cohort/sample/benchmark definition anywhere; deliberately gated by roadmap. |
| GAP-09: divergent identity derivations | `portfolio_intelligence._identity`: `atlas-security` namespace → `security_id = sec:sha256("atlas-security:{type}:{SYMBOL}")[:32]`, `SecurityState.RESOLVED` for symbol + known type. `risk_scenarios._identity`: `atlas-unresolved` namespace → different `security_id` string, `SecurityState.UNRESOLVED` always (lines 295–304). Same holding → two different canonical keys. Confirmed. |
| GAP-15: CIO archive | `cio_reports.py` builds deterministic in-memory `CIOReport/v1` with hashes; no persistence, route, scheduler, delivery, or archive. |
| GAP-16: deletion/orphan | All investment FKs `ondelete="RESTRICT"`; no deletion path for owners with records. |

### 1.3 Reuse inventory (what INV-12 calls — never re-implements)

| Existing function/contract | Location | INV-12 use | Mode |
|---|---|---|---|
| `evaluate_outcome()` / `OutcomeResult` | `app/investments/outcome_tracking.py` | The evaluation engine for every computed evaluation. Produces `RecommendationOutcome/v1` with `outcome_hash`, zero-price/insufficient-history fail-closed, `as_known_at <= as_of` + `observed_at <= as_of` eligibility filters, benchmark support. | Called as-is with observations read from the durable store |
| `track_recommendation()` / `TrackedRecommendation` | same | Establishes the tracking record an evaluation refers to. | Called as-is |
| `record_decision()` / `HumanDecisionRecord` | same | Decision linkage for decision-performance evaluation. | Called as-is |
| `RecommendationOutcome/v1` + `record_outcome()` | same + `app/investments/persistence_service.py` | All computed evaluation values are frozen through the existing outcome row path (single store of measured values). | Called as-is |
| `build_portfolio_snapshot()` / `PortfolioSnapshot/v1` | `app/investments/portfolio_intelligence.py` | The **only** snapshot builder; the new snapshot store persists its payload + `snapshot_hash`. | Called as-is, plus persistence hook at recommendation-persist time |
| `MarketObservation/v1` (INV-02) + `outcome_tracking.MarketObservation` | both modules | Validation + evaluation input shapes for the durable observation store (§6). | Bridged by the store contract; never re-implemented |
| `InvestmentRepository` projections | `app/investments/persistence_repository.py` | Owner-scoped, hash-verified reads of recommendation/decision/outcome/committee/evidence — the only way INV-12 reads authoritative state. | Called as-is; extended with evaluation/snapshot/observation readers |
| `InvestmentPersistenceService` | `app/investments/persistence_service.py` | Persists validated snapshots only; idempotency-conflict and linkage invariants are reused for new stores. | Called as-is; extended additively |
| Quant metrics (`quant.py`), CIO reports (`cio_reports.py`) | INV-07 / INV-10 | **Not used** by the C+D+E slice. If a later slice needs benchmark-relative quantitative context beyond `RecommendationOutcome`, it reads the same `PriceSeriesPoint`/observation path — no new engine. | Not used now (reason: out of first-slice scope) |
| Append-only trigger pattern | migration `T8a1b2c3d4e5` (recommendations, decision_journal_entries); `R6f1g2h3i4j5` (forecast history) | Immutability guards for the new observation/snapshot/evaluation stores. | Convention reused (§19a) |
| Immutability migration test suite | `tests/test_investment_scout_migration.py` (+ `test_outcome_evaluation_migration.py`) | Test precedent for round-trip upgrade/downgrade and write-rejection proofs. | Convention reused (§22) |

---

## 2. INV-12 Canonical Definition

> **INV-12 is responsible for deterministic, owner-scoped, append-only *evaluation* of investment recommendations and recorded human decisions — recomputing what the system measured (and verifying what it could have known) at defined points in time — together with the *retention boundary* that governs how long that immutable history must remain available.**

Sub-capabilities, each with an explicit owner phase:

| Sub-capability | Definition | Owner | Required inputs | Required outputs |
|---|---|---|---|---|
| **Evaluation** | Measure realized recommendation/decision performance over a defined window, reusing INV-11 `evaluate_outcome()` semantics | INV-12 first slice | frozen `TrackedRecommendation` (+ optional frozen decision), evaluation window, durable observations, optional benchmark | immutable `InvestmentEvaluationRecord` referencing a frozen `RecommendationOutcome` |
| **Replay (deterministic verification)** | Reproduce the stored result from the same frozen inputs and methodology; detect any drift (methodology change, missing inputs, corrupted hash) | INV-12 first slice | stored artifact + input hash + evaluation hash + observation store bound | `replay_state`: `MATCH` / `METHODOLOGY_CHANGED` / `INPUTS_UNAVAILABLE` / `HASH_MISMATCH` |
| **Replay (reconstruction of analysis state)** | Rebuild "what the system knew" at an analysis timestamp from durable vintaged observations | **Deferred (D-3)** — requires store population over real history first | durable observation store with vintages | point-in-time observation snapshot |
| **Retention** | Policy for duration, deletion, legal hold, backups of immutable investment history | **Deferred (D-8)** — policy approval required | product/security decisions | approved policy, not code |
| **Calibration** | Statistical cohort validation of recommendation quality | **Deferred (D-7)** — requires cohort/methodology definition | product definition | none now |

---

## 3. Evaluation Semantics

INV-12 evaluates **recommendation performance** and, where a recorded human decision exists, **decision performance** — as two distinct, never-collapsed objects, matching the existing four-concept separation:

```
Recommendation  — "what the system recommended"   (frozen InvestmentRecommendationRecord)
Decision       — "what the human chose"           (frozen InvestmentDecisionRecord, optional)
Outcome        — "what was measured at the time"  (frozen RecommendationOutcome row)
Evaluation     — "how the recommendation/decision compared with reality"
                   (new immutable InvestmentEvaluationRecord over the above)
```

Rules:
- An evaluation **always** refers to a persisted recommendation by `recommendation_record_id` FK + `recommendation_hash`.
- A decision link is optional: if present, it must be the owner's persisted decision whose `recommendation_hash` equals the recommendation's hash. `no_action` and missing decisions evaluate recommendation performance with `decision_id = NULL` — never synthesized.
- INV-12 **never mutates** a recommendation, decision, or outcome. It reads them only through `InvestmentRepository` hash-verified projections. It never parses `payload_json` directly except where the design documents that a frozen payload is the canonical source (evidence packets/outcomes are re-validated through their typed contracts by the repository).
- Deterministic arithmetic only: no LLM participates in any calculation. LLM text is not an input to the engine.

---

## 4. Replay Semantics (D-3)

| Meaning | Required? | Why | Required Data | INV-12 Now? | Future? |
|---|---|---|---|---|---|
| A — Recalculate historical result from historical inputs | **No (deferred)** | Requires durable historical observation + snapshot stores populated with real history and vintages; no market-data history exists yet | full historical series | — | Yes, gated on HP-01/HP-02 population |
| B — Reconstruct what the system knew at analysis time | **No (deferred)** | "What the system knew" needs `as_known_at` vintages over real history; not reconstructable today and not required by roadmap wording for the first slice | durable vintaged observations | — | Yes, gated on HP-01 + real history |
| C — Reconstruct the recommendation from frozen analytical inputs | **Yes** | Already supported by persisted frozen payload + `recommendation_hash`; INV-12 makes it an explicit integrity assertion (hash re-verification on every read, already in `InvestmentRepository`) | persisted recommendation + hash | Yes | — |
| D — Reproduce methodology/versioned analytical output | **Yes** | `evaluate_outcome()` is deterministic: same observations+tracking → same `outcome_hash`. Re-run over the durable store must reproduce the stored artifact or report drift | frozen observations (store) + methodology version | Yes | — |
| E — Evaluate historical outcome vs later market/portfolio state | **Yes** | The core capability: evaluation at a defined window over durable observations; extends today's outcome flow which requires observations to be supplied at evaluation time | durable observation store + snapshot reference | Yes | — |

**Decision D-3 (recommended, evidenced):** initial INV-12 scope = **C + D + E**. A + B are explicitly deferred until the durable stores are populated with real provider history and product requires point-in-time reconstruction. Rationale: C/D/E require only frozen artifacts plus observations from the point the store starts writing forward (store is additive; no historical backfill needed). A/B would silently claim a history the repository does not possess — that is the fail-closed posture the audit requires.

---

## 5. Evaluation Artifact Contract (GAP-01) + Delta Analysis (D-4)

### 5a. Mandatory delta analysis vs `investment_outcome_records` (§7a of the gate)

`investment_outcome_records` persists: `outcome_id` (`recommendation-outcome:<hash>`), recommendation FK + `recommendation_id`/`recommendation_hash`, optional `decision_id` FK, `evaluation_as_of`, `outcome_hash`, `payload_json` (full `RecommendationOutcome/v1`), `created_at`.

**Can the INV-12 evaluation artifact be a read-projection over that table?** No — three capabilities the artifact requires are not representable there:
1. **Evaluation lifecycle/eligibility state** distinct from a frozen outcome (the outcome row *is* a completed measurement; there is no pending/evaluable/blocked state and no place to record *why* an evaluation was not produced).
2. **Replay metadata**: replay request parameters (window, methodology version, benchmark, vintage/as-known-through bound), deterministic **input hash**, and the **durable store reference** the evaluation was computed over.
3. **Result-state vocabulary beyond outcome availability** (e.g., `NOT_COMPARABLE` for adjustment-basis/currency mismatch) must live on the artifact, not on the INV-11 outcome.

**Delta conclusion (D-4):** a **new table `investment_evaluation_records`**, additive and immutable, that **does not duplicate outcome values**. Every computed evaluation persists its measured values by routing through the existing `record_outcome()` path, so the outcome row stays the single store of measured values and the evaluation row carries identity/lifecycle/replay/result metadata and references `outcome_record_id` + `outcome_hash`. An evaluation whose window refers to an already-recorded outcome references it; an evaluation at a new point calls `evaluate_outcome()` first (reuse), records the outcome, then references it. No second calculation engine, no value duplication.

### 5b. Contract — `InvestmentEvaluationRecord` (persisted) / `InvestmentEvaluationArtifact/v1` (typed domain)

| Field | Why it exists | Authoritative | Immutable | In hash | Nullable |
|---|---|---|---|---|---|
| `evaluation_id` = `investment-evaluation:<sha256[:32]>` | deterministic identity | yes (DB CHECK `LIKE 'investment-evaluation:%'`) | yes | no (self) | no |
| `schema_version` = `InvestmentEvaluationArtifact/v1` | contract versioning | yes | yes | yes | no |
| `owner_id` (+ RESTRICT FK to `users`) | owner scope | yes | yes | yes | no |
| `recommendation_record_id` (FK `investment_recommendation_records.id`) | immutable rec linkage | yes | yes | — (referenced) | no |
| `recommendation_hash` | hash-locked rec identity | yes | yes | yes | no |
| `decision_record_id` (FK `investment_decision_records.id`) | optional decision linkage | yes | yes | — (referenced) | yes |
| `decision_id` + `decision_hash`-equivalent (`recommendation_hash` equality is checked at write) | decision identity | yes | yes | yes | yes |
| `outcome_record_id` (FK `investment_outcome_records.id`) | references the frozen measured outcome | yes | yes | — (referenced) | yes (only when result_state ≠ `evaluated`) |
| `outcome_hash` | hash-locked outcome identity | yes | yes | yes | yes (when outcome absent) |
| `evaluation_window_start` | baseline instant (`recommendation_as_of`) | yes | yes | yes | no |
| `evaluation_as_of` | evaluation instant (window end) | yes | yes | yes | no |
| `horizon` (`1D|1W|1M|3M|6M|1Y`) | window identity consistent with outcomes | yes | yes | yes | no |
| `benchmark_security_id` | benchmark identity when required | yes | yes | yes | yes |
| `evaluation_state` (see §5c) | lifecycle | yes | append-only transition via new row or one-time column update? — **no updates**; states `pending/evaluable` are only reachable through the internal evaluator within the same transaction that writes the final `evaluated`/`blocked` row, or the row is written in its terminal state. See §5c | yes | no |
| `result_state` (see §5c) | typed insufficiency/unavailable/not-comparable vocabulary | yes | yes | yes | yes |
| `methodology_version` = `investment-evaluation/v1` | reproducibility (D) | yes | yes | yes | no |
| `vintage_bound` (as_known_through) | replay boundary: observations with `as_known_at > vintage_bound` excluded | yes | yes | yes | no |
| `input_hash` | deterministic hash of all inputs (owner, rec hash, decision, window, horizon, benchmark, methodology, vintage bound) | yes | yes | — | no |
| `evaluation_hash` | sha256 over canonical payload (excluding hash fields) | yes | yes | — | no |
| `replay_state` (`match`/`methodology_changed`/`inputs_unavailable`/`hash_mismatch`) | last deterministic re-verification result; computed, not stored as mutable truth — stored only as the frozen result of the replay that created the artifact (`match` on creation; later re-runs produce a new replay record or typed response) | yes | yes | yes | no |
| `created_at` | provenance timestamp | yes | yes | no (excluded like other created_at) | no |
| `payload_json` | full typed artifact for read-projection and tamper detection | derived | yes | — | no |

Every evaluation row references `input_hash`; identical inputs (owner, rec hash, decision, window, horizon, benchmark, methodology, vintage bound) → identical `evaluation_id` → idempotent single row via `UNIQUE(owner_id, evaluation_id)`. Conflicting request (different window/methodology/vintage) → different deterministic ID → **distinct row, never overwrite**.

### 5c. Evaluation states (invented only where existing enums cannot express them)

- `evaluation_state` ∈ `{pending, evaluable, evaluated, blocked}`:
  - `pending`/`evaluable` mirror `OutcomeState.PENDING` vocabulary; reachable only inside the internal evaluator transaction (an evaluation row is created and immediately advanced; a crash leaves no half-state because the row is written once in its terminal state — see below).
  - `evaluated` — the artifact references a frozen outcome row.
  - `blocked` — a typed `blocked_reason` code explains why (missing snapshot row, missing observation eligibility, no stored outcome path, temporal violation, owner mismatch, corrupted source hash).
  - `invalidated` is **not** introduced: supersession/expiry of a recommendation does not invalidate historical evaluation (that is the point of E); no state in this slice ever rewrites an artifact.
- `result_state` ∈ `{available, insufficient_history, unavailable, temporal_violation, not_comparable}` — first four reuse `OutcomeState` values verbatim; `not_comparable` is new and covers adjustment-basis/currency mismatch per §26 of the gate (it belongs on the evaluation artifact, never on the INV-11 outcome).
- **Append-only rule:** rows are written once. A later evaluation at a new window or with a changed methodology is a **new row** (different deterministic inputs → different ID). No `UPDATE`, no `DELETE` (triggers, §19a).

---

## 6. Durable Market-Observation Contract (GAP-02)

### 6a. Which existing `MarketObservation` wins — and why

Neither existing contract is persisted as-is; the store is a new table, and the design resolves the current duplication by assigning each shape its role:

- `app/investments/market_observations.py` `MarketObservation/v1` (INV-02) is the **validation/ingestion shape**: source, source_identifier, currency, `adjustment_basis`, `quality`, `freshness`, `retrieved_at`. It lacks a vintage (`as_known_at`).
- `outcome_tracking.MarketObservation` is the **evaluation input shape** consumed by `evaluate_outcome()`: `security_id` string, `price`, `observed_at`, `as_known_at`, `state`, hash. It lacks currency/basis/source.

**Decision:** the durable store row is a superset of both. Writes validate against INV-02 semantics (currency 3-letter, adjustment basis, quality never `invalid`, `as_of <= retrieved_at`); evaluation reads project the row into `outcome_tracking.MarketObservation` so `evaluate_outcome()` is called **as-is**. This ends the duplication by making the two shapes two projections of one stored fact — no second market-data product, no engine change.

### 6b. Table `investment_market_observations` (minimum scope for INV-12)

| Column | Justification | Nullable |
|---|---|---|
| `observation_id` = `market-observation:<sha256[:32]>` | deterministic identity over canonical fields | no |
| `security_id` | canonical INV-01 identity under the frozen D-2 rule; equality is exact string match | no |
| `observed_value` (decimal string) | the price/value; finite, non-negative for prices (reuse `evaluate_outcome` zero-price semantics at evaluation time) | no |
| `currency` (`[A-Z]{3}`) | required so evaluation can fail closed on mismatch — never silently convert | no |
| `adjustment_basis` (`unadjusted\|split_adjusted\|total_return_adjusted\|unknown`) | baseline/evaluation comparability; mismatch → `not_comparable` | no |
| `observed_at` | market time the value refers to (satisfies `observed_at <= evaluation_as_of`) | no |
| `as_known_at` | vintage — when the value became known (satisfies `as_known_at <= analysis/evaluation as_of`; also `>= observed_at`) | no |
| `retrieved_at` | provider fetch time; `>= as_known_at` (ingestion-time provenance; never used as an eligibility key) | no |
| `source`, `source_identifier` | provider provenance (existing adapters only) | source no / identifier yes |
| `state` (DataState) | `observed` only for rows eligible for evaluation | no |
| `quality`, `freshness` | data-quality provenance carried from INV-02 write validation | no |
| `observation_hash` (lowercase 64-hex, DB CHECK) | integrity; referenced by outcome/quant/evidence `source_observation_hashes` — the store is what makes those hashes "openable" | no |

**Storage semantics:**
- **Append-only + immutable**: `BEFORE UPDATE`/`BEFORE DELETE` triggers on SQLite and PostgreSQL (§19a).
- **Vintage/restatement**: a provider restatement of the same `observed_at` is a **new row** with a later `as_known_at` — never an update. An evaluation at time T uses rows with `as_known_at <= T` (the vintage rule, §9); earlier artifacts are untouched because they froze their hashes and values.
- **Unique key**: `UNIQUE(security_id, observed_at, as_known_at, adjustment_basis, source, source_identifier, observed_value)` — deduplicates true duplicates (same row delivered twice) while permitting restatements.
- **Ownership**: **not owner-scoped** — provider-derived market observations are public security data identical for every owner (consistent with both existing contracts having no `owner_id`). This is the single deliberate deviation from the "every new store is owner-scoped" rule (§19a) and is justified in §15.
- **Writers**: server-internal only (provider adapters / evaluation backfill); no ingestion API, no browser write path.
- **Retention**: subject to D-8.

---

## 7. Durable Portfolio-Snapshot Contract (GAP-03)

### 7a. Delta analysis vs today's hash-only linkage

Today `investment_recommendation_records.portfolio_snapshot_hash` is a 64-hex fingerprint with no payload anywhere. The new store does **not** create a second portfolio ledger: it persists the output of the existing `build_portfolio_snapshot()` (INV-03) — the single builder — as an immutable payload.

**Answers (§11a of the gate):**
1. The store persists the **full `PortfolioSnapshot/v1` payload + `snapshot_hash`** per written snapshot. Writes happen (a) when a recommendation is persisted (the snapshot whose hash the recommendation references is written first), and (b) when an evaluation needs an explicit owner-scoped baseline.
2. The builder is **reused**; the store adds no calculation. Stored snapshots may embed computed exposure/total (the existing builder's output), but the store itself computes nothing and re-derives nothing.
3. Linkage = **both**: hash-only stays on the recommendation (unchanged column), and the new table stores the payload keyed by hash. Recommendation→snapshot resolution is `SELECT ... WHERE owner_id = ? AND snapshot_hash = recommendation.portfolio_snapshot_hash`. A recommendation whose hash has no stored payload (legacy rows) is **`unavailable`** — never silently re-derived from current holdings.

### 7b. Table `investment_portfolio_snapshots`

| Column | Justification | Nullable |
|---|---|---|
| `snapshot_id` = `portfolio-snapshot:<sha256[:32]>` | deterministic identity | no |
| `owner_id` (+ RESTRICT FK) | snapshots embed private holdings/value — owner-private (§15) | no |
| `snapshot_hash` (lowercase 64-hex, DB CHECK) | equals the `PortfolioSnapshot/v1.snapshot_hash` and the recommendation's `portfolio_snapshot_hash` when linked | no |
| `as_of` | the snapshot instant (for a recommendation-linked snapshot: `recommendation_as_of`) | no |
| `security_ids` (JSON array or link rows) | canonical identities under D-2; enables owner-scoped join without re-derivation | no |
| `payload_json` | canonical `PortfolioSnapshot/v1` domain payload for typed read-projection | no |
| `source_holding_ids` | provenance to Account/Holding rows at snapshot time | no |
| `created_at` | provenance | no |

**Storage semantics:** immutable/append-only (triggers); `UNIQUE(owner_id, snapshot_hash)`; positions embedded in payload are never re-validated against current holdings (a snapshot is a point-in-time fact). Currency semantics: snapshot values carry the builder's currency state; mixed/unknown currency is preserved as typed `unknown` — never aggregated or converted.

---

## 8. Recommendation → Decision → Outcome → Evaluation Chain

Transition table — every hop enforces: identifier + hash + timestamp + owner + security + provenance + immutability + temporal constraint.

| Transition | Required identifier | Hash | Timestamp | Owner | Temporal constraint (verified existing) |
|---|---|---|---|---|---|
| `EvidencePacket → CommitteeFinding` | `packet_id`/`finding_id` + link row | `packet_hash`/`finding_hash` | `analysis_as_of` | same owner (checked at persist) | finding `analysis_as_of <= run.analysis_as_of`; evidence subject/owner match |
| `CommitteeFinding → Recommendation` | `committee_finding_id`/`committee_run_id` | `input_hash`/`recommendation_hash` | `analysis_as_of <= recommendation_as_of` | same owner | `review_after >= recommendation_as_of`; `expires_at >= review_after` |
| `Recommendation → HumanDecision` | `recommendation_id` + `decision_id` | `recommendation_hash` (If-Match), idempotency hash | `decided_at >= created_at` | same owner | decision requires persisted active recommendation with matching hash |
| `Recommendation/Decision → Outcome` | `recommendation_record_id` FK, optional `decision_id` FK | `outcome_hash` | `evaluation_as_of >= recommendation_as_of` | same owner | observations filtered `as_known_at <= evaluation_as_of`, `observed_at <= evaluation_as_of` |
| `Outcome → Evaluation` (new) | `outcome_record_id` FK (or its own window when no prior outcome) | `outcome_hash` + `input_hash` + `evaluation_hash` | `window_start <= evaluation_as_of` | same owner | observations restricted to `as_known_at <= vintage_bound <= evaluation_as_of`; snapshot hash must exist in the store |

INV-12 reads authoritative state **only** through `InvestmentRepository`/typed service projections. The one documented frozen-payload-as-canonical case is the outcome row's `payload_json` (re-validated into `RecommendationOutcome/v1` by the repository before use).

---

## 9. Temporal Model (point-in-time semantics)

**Definitions (pinned):**
- `observed_at` — the market instant a value refers to (a close belongs to its session).
- `as_of` — the analysis/evaluation horizon instant.
- `as_known_at` — the vintage instant when the value became known; the *only* eligibility key for "what the system knew". `as_known_at >= observed_at` and `as_known_at <= retrieved_at`.
- `retrieved_at` — when the provider was actually fetched; ingestion provenance only, **never** an evaluation eligibility key (a late fetch of an old value must not look "new").

**Eligibility predicates (existing, reaffirmed and made store-level):**
```
baseline/observation eligible for evaluation at time T  ⇔  as_known_at <= T  AND  observed_at <= T
```
- The evaluation engine already enforces `as_known_at <= evaluation_as_of` and `observed_at <= evaluation_as_of`; the store additionally enforces the same filter against `vintage_bound` so a replay at a later date cannot pull vintages that postdate the original evaluation.
- **Vintage rule:** at evaluation time T the chosen vintage is the latest row with `as_known_at <= T` for the `(security, observed_at)` pair. A later restatement (new row, later `as_known_at`) is invisible to that evaluation; a re-run over the same `vintage_bound` reproduces the identical choice (deterministic, D).
- **Future-information leak prevention:** an evaluation never sees a row with `as_known_at > vintage_bound`; a provider delivering today's value with an old `observed_at` but today's `as_known_at` is correctly excluded from any evaluation whose `vintage_bound` precedes today.
- **Window semantics for evaluation at a new point:** `window_start = recommendation.recommendation_as_of` (baseline must not precede the recommendation) and `evaluation_as_of` must be `>= window_start` and after the window has closed per horizon — otherwise `result_state = pending` is impossible (no scheduled model); the internal evaluator refuses with `blocked`/typed reason until the window closes. `evaluation_as_of` strictly after `vintage_bound` is allowed only when the extra vintages are real observations (not predictions).

---

## 10. Provenance Model

| Hop | Provenance carried | Lost today? | INV-12 fix |
|---|---|---|---|
| provider → observation | `source`, `source_identifier`, `retrieved_at`, `as_known_at`, `observation_hash` | observation values not durable → `source_observation_hashes` on quant/evidence/outcomes could not be "opened" | durable store opens every hash; artifacts carry `source_observation_hashes` + copied frozen values |
| holdings → snapshot | `snapshot_hash`, `source_holding_ids`, `as_of` | payload not durable | durable payload + hash |
| analysis chain | `analysis_as_of`, packet/finding/rec hashes | none (frozen) | repository re-verification on read (exists) |
| evaluation | `input_hash` (inputs), `evaluation_hash` (artifact), `outcome_hash` (result), `vintage_bound` | n/a (new) | artifact contract §5b |

No UI/API layer fabricates provenance: every displayed evaluation field comes from the typed artifact projection; read routes never accept provenance-bearing client fields (client `owner_id`/hashes/values → 422, existing convention).

---

## 11. Hash / Integrity Model (D-4 mechanics)

Follows the established repo convention exactly:
- `canonical_payload()` = `json.dumps(model_dump(mode="json", exclude={hash_fields, created_at}), sort_keys=True, separators=(",", ":"))`.
- `with_hash()` computes `sha256(canonical_payload)` over the provisional object, then validates; stored hashes are lowercase 64-hex with DB CHECK (`length(x)=64 AND x=lower(x)`).
- **Nested/ordering rule:** nested collections are canonicalized by `model_dump(mode="json")` order (tuples preserve insertion order; all list-producing code sorts deterministically before hashing — same rule the current contracts use).
- `input_hash` covers only inputs; `evaluation_hash` covers the canonical artifact (excluding `input_hash`? — **no**: `evaluation_hash` covers the artifact canonical payload including `input_hash` and referencing hashes, excluding its own hash fields and `created_at`). Consequence: same ID + different contents ⇒ different hash ⇒ rejected by repository re-verification on read (mirrors `InvestmentRepository.get_recommendation` integrity checks).
- DB CHECK constraints on `observation_hash`, `snapshot_hash`, `outcome_hash`, `evaluation_hash`, `input_hash`.

**Prevention proof required in tests:** same `evaluation_id` with tampered payload_json or hash must raise `InvestmentRepositoryError` (or equivalent) rather than return data.

---

## 12. Versioning Model (GAP-07, D-10)

**Decision: Option A — embedded version strings suffice for the bounded first slice; no registry.**

- Every artifact carries `methodology_version` (`investment-evaluation/v1`) and references the outcome's `METHODOLOGY_VERSION` (`investment-outcome/v1`); the snapshot carries `calculation_version`; the observation store records the validation contract version in the row (`MarketObservation/v1`-derived) — all already embedded today.
- A methodology change is **detected, never silently applied**: replaying with a different methodology produces a *different deterministic input hash* → a new artifact (not an overwrite), and the replay comparison reports `METHODOLOGY_CHANGED` when the stored methodology_version differs from the request.
- A registry (Options B/C) is deferred until a second evaluation methodology actually exists; building one now would be speculative infrastructure (§20).

---

## 13. Calibration Decision (GAP-08, D-7)

**Decision: explicitly deferred.** No cohort definition, minimum-sample rule, benchmark, success metric, or confidence requirement exists; the roadmap gates calibration behind product definition. The deferral trigger is recorded: revisit calibration when ≥ 1 methodology has produced a defined population of evaluations (or product defines a cohort). **No placeholder calibration infrastructure is created.**

---

## 14. Retention / Deletion Decision (GAP-04, D-8)

Do not implement. Per record class, the required disposition and owner:

| Record class | Retention question | Disposition |
|---|---|---|
| Recommendations / decisions / outcomes | duration | **PRODUCT DECISION REQUIRED** (recommendation: no automatic deletion; personal-use default-off until policy) |
| Evaluations (new) | duration | **PRODUCT DECISION REQUIRED** (recommendation: same as outcomes) |
| Market observations | duration; provider terms | **PRODUCT + SECURITY DECISION REQUIRED** (public security data; provider license terms may cap retention) |
| Portfolio snapshots | duration | **PRODUCT DECISION REQUIRED** (private; contains cost basis/value) |
| Evidence packets / committee runs / scout runs | duration | **PRODUCT DECISION REQUIRED** |
| CIO reports | not persisted | n/a (D-9) |
| Account/owner deletion | immutable-history handling | **SECURITY DECISION REQUIRED** — deletion path is undefined (GAP-16); RESTRICT FKs fail safe today |
| Legal/audit hold, backups | hold semantics | **SECURITY DECISION REQUIRED** |
| Multi-user transition | changes between personal and multi-user | **PRODUCT/SECURITY DECISION REQUIRED** (ties to GAP-18 tenant model) |

**Architecture position (can be frozen now, independent of policy):** new stores are append-only and physically-deletion-resistant by trigger; any future deletion must be a designed, policy-approved operation (soft-tombstone + derived-data rebuild plan), never an ad-hoc `DELETE`. This matches the existing "Never roll back by deleting or rewriting analytical, decision, or outcome records" rule in the consolidated execution plan. Implementation-complete (per §23) is reachable without D-8; production/multi-user ready is not.

---

## 15. Multi-User / Privacy Requirements

- **Owner isolation:** snapshots and evaluations are owner-scoped (`owner_id` RESTRICT FK + `UNIQUE(owner_id, logical_id)` + owner filters in repository reads + non-enumerating 404 on cross-owner lookup). Observations are the single **owner-independent** store (public security data); their API reads remain owner-scoped (an owner can only read observations for securities they are authorized to evaluate), and writes are server-internal only.
- **Privacy classification:**
  - **Private evaluation artifacts** — evaluation records (embed portfolio-linked baselines and per-owner windows), snapshot store.
  - **Public security data** — observation store rows (value/source/vintage for a canonical security).
  - **Internal audit data** — `input_hash`/`evaluation_hash`/`replay_state`/`methodology_version` may be shown to the owner but are never presented as financial advice.
- **Known multi-user caveat (recorded, not depended on):** `get_or_create_local_user` convenience in scout routes and the transitional tenancy mean production multi-user rollout requires the GAP-18 tenant decision; INV-12 design does not depend on it — every new table uses the established `owner_id` FK model.
- **Redaction:** future UI projections must not render other-owner data, account identifiers, or cost basis embedded in snapshot payloads outside the owner's private surface.

---

## 16. CIO Archive Decision (GAP-15, D-9)

**Decision: NOT REQUIRED for INV-12.** Proven by dependency trace: INV-12 evaluation operates on canonical recommendation records (frozen payload + hashes), evidence packets/committee findings (frozen), decision/outcome records, and the new observation/snapshot stores. `cio_reports.py` builds reports **from** those records; an archived report adds no input that replay or evaluation consumes — the report is a consumer, not a producer, of evaluation state. The archive stays deferred (existing GAP-15 posture) unless a concrete report consumer with a durable-delivery requirement is approved.

---

## 17. API / Service Boundary (D-6)

### Read endpoints (typed, owner-scoped, no mutation)
```
GET /api/v1/investments/evaluations?recommendation_id=<id>          # list owner artifacts (window/methodology filters server-side)
GET /api/v1/investments/evaluations/{evaluation_id}                 # detail + replay_state
GET /api/v1/investments/evaluations/{evaluation_id}/replay          # deterministic re-verification result (typed, no side effects)
```
Conventions: auth via `require_user`; owner scope from auth (client `owner_id` rejected → 422); non-enumerating 404 for foreign/unknown IDs; typed envelopes; bounded pagination; no ORM leakage; every error has a typed reason code.

### Write boundary — trigger model (D-6)
- **(a) internal on-demand service call** — chosen for the first slice: the evaluator is invoked (i) when an outcome is recorded and its window has closed, or (ii) by an explicit internal command/repository job. No scheduler, no browser, no user-triggered evaluation writes.
- (c) scheduled background evaluation is **out of scope** (no scheduler exists; background execution is a project-wide safety boundary).
- Evaluation request inputs are validated server-side (allowed horizons, closed windows, owner's persisted recommendation, supported securities, numeric bounds) — no arbitrary analytical JSON.

### What the next implementation session must NOT decide (§24c — pre-frozen)
D-1..D-10 values, identity rule + namespace, state enums (§5c), hash serialization (§11), storage delta analyses (§5a/§6/§7a), trigger model (§17), vertical slice (§21b). The implementer makes zero architectural choices; only the named product decisions may change the table above and only with explicit approval.

---

## 18. Failure / Safety States (all fail closed, typed reason codes)

| Condition | Behavior |
|---|---|
| Missing observation for baseline/evaluation | `result_state = insufficient_history` (mirrors `OutcomeState.INSUFFICIENT_HISTORY`) |
| Missing portfolio-snapshot row for a stored `portfolio_snapshot_hash` | `blocked` (`missing_snapshot`) — **never re-derive from current holdings** |
| Missing evidence packet / committee payload | `blocked` (`missing_evidence`) |
| Recommendation withdrawn/superseded/expired | still evaluable over the frozen recommendation (E semantics); supersession never blocks |
| Zero price | `unavailable` via existing engine path (baseline zero → unavailable) |
| Incompatible/missing currency between baseline and evaluation observations | `not_comparable` — never silently convert |
| Adjustment-basis mismatch (unadjusted vs split-adjusted) | `not_comparable` |
| Provider restatement / new vintage after evaluation | original artifact untouched (frozen hashes + values); new vintage only affects new artifacts (`vintage_bound` respected) |
| Corrupted hash / tampered payload | repository raises `InvestmentRepositoryError`; route → 422/500 typed, never returns data |
| Owner mismatch | 404 non-enumerating |
| Temporal violation (`evaluation_as_of < window_start`; future `as_known_at` selection) | `blocked`/`result_state = temporal_violation` |
| Duplicate evaluation request (identical inputs) | idempotent single artifact (deterministic `evaluation_id` + UNIQUE) |
| Conflicting evaluation request (same rec, different window/methodology/vintage) | distinct artifact; no overwrite |
| Methodology change on replay | `replay_state = methodology_changed` + new artifact on recompute |

---

## 19. Minimum Storage Design

| Store | Required for INV-12? | Immutable? | Owner-scoped? | Historical? | Minimum fields | Delta vs existing table |
|---|---|---:|---:|---:|---:|---|---|
| MarketObservation store (`investment_market_observations`) | **Yes** | Yes (triggers) | **No** (public security data, §15) | Yes (vintaged) | §6b | No table exists; two contract shapes today |
| PortfolioSnapshot store (`investment_portfolio_snapshots`) | **Yes** | Yes (triggers) | Yes | Yes | §7b | Only hash column today |
| Recommendation | **Yes** (referenced) | Yes (service-enforced; goal substrate triggers) | Yes | Yes | exists | exists |
| Decision | **Yes** (referenced) | Yes | Yes | Yes | exists | exists |
| Outcome | **Yes** (referenced) | Yes | Yes | Yes | exists | exists |
| EvaluationArtifact (`investment_evaluation_records`) | **Yes** | Yes (triggers) | Yes | Yes | §5b | must delta-analyze vs outcomes — done (§5a): new, non-duplicative |
| EvidencePacket | **Yes** (referenced) | Yes | Yes | Yes | exists | exists |
| CommitteeRun | **Yes** (referenced) | Yes | Yes | Yes | exists | exists |
| CIOReport | **No** | — | — | — | — | not persisted; NOT REQUIRED (D-9) |

### 19a. Repository persistence mechanics (all new stores follow existing conventions)
- Additive Alembic migrations **after the single head `AB16a1b2c3d4e5`**; exactly one head maintained; `upgrade`/`downgrade`/re-upgrade round-trip proven per the scout-migration suite pattern.
- Append-only `BEFORE UPDATE`/`BEFORE DELETE` triggers on **both SQLite and PostgreSQL** (precedent `T8a1b2c3d4e5`) for `investment_portfolio_snapshots` and `investment_evaluation_records`; same for `investment_market_observations`.
- Owner FK `RESTRICT` to `users` + `UNIQUE(owner_id, logical_id)` for snapshots/evaluations; lowercase-64-hex hash CHECKs; ID-shape CHECKs (`investment-evaluation:%`, `portfolio-snapshot:%`, `market-observation:%`).
- Ownership trigger pattern where cross-owner linkage must be impossible (precedent `recommendations_goal_owner`), e.g., evaluation `owner_id` must equal referenced recommendation/decision/outcome owners — enforced both in service and by trigger where practical.
- New tables exported through `app/models/__init__.py`.

---

## 20. Explicit Non-Goals (do-not-build list)

Out of scope for initial INV-12, with reason: full market-data warehouse / real-time ingestion (bounded store only, §6); second evaluation engine (reuse inventory §1.3); scheduler/background evaluation (§17); calibration infrastructure (D-7); model/methodology registry (D-10 option A); UI-triggered evaluation ingestion (server/internal only); CIO report archive (D-9); arbitrary historical backtesting over pre-store data (A/B deferred, D-3); predictive forecasting; autonomous optimization/trading/rebalancing/order placement (execution boundary unchanged); portfolio mutation of any kind; generic data lake; any second portfolio ledger (snapshot store persists one builder's output only, §7).

---

## 21. Implementation Dependency Graph

### 21a. Sequence (D-driven)

```text
0.  Freeze D-1..D-10 (this gate) — approvals listed in Executive Verdict
1.  Schedule GAP-09 shared holding→identity refactor (D-2) — land BEFORE store population
2.  Freeze INV-12 contracts as code: InvestmentEvaluationArtifact/v1 + enums + market-observation
    store row contract + portfolio-snapshot row contract (contract tests only)
3.  Implement durable observation store migration + model + triggers (additive; head AB16 → new head)
4.  Implement durable portfolio-snapshot store migration + model + triggers
5.  Implement investment_evaluation_records migration + model + triggers (D-4 delta design)
6.  Extend persistence service/repository: write hook at recommendation-persist time (snapshot),
    observation ingestion via existing adapters, evaluation engine reusing evaluate_outcome(),
    typed read projections
7.  Internal evaluation boundary + read API routes (auth, owner scope, idempotency, non-enumerating 404)
8.  Deterministic + temporal/provenance/security tests (§22)
9.  INV-12 implementation certification (§23)
10. Retention/deletion slice — ONLY after D-8 policy approval
```

Prerequisites per step are listed inline; every step that persists rows depends on D-2's frozen identity rule, and steps 3–5 depend on the delta analyses in §5a/§6/§7a.

### 21b. Minimal vertical slice (§29b of the gate)

One owner + one security with a resolved identity under D-2 → provider fixture writes 3+ vintaged observation rows → a recommendation is persisted and its `PortfolioSnapshot/v1` payload is stored (hash equality asserted) → one frozen `RecommendationOutcome` recorded via `record_outcome()` → evaluation artifact created for the closed window → deterministic `input_hash`/`evaluation_hash` asserted → replay returns `match` → owner-scoped read route returns the typed artifact and cross-owner lookup returns 404 → immutability trigger tests pass for all three new tables. Every later slice is additive.

---

## 22. Test Strategy (design only — none implemented)

- **Contract:** artifact/observation/snapshot schema serialization and validation; enum sets (§5c); temporal rules (§9); `input_hash`/`evaluation_hash` determinism.
- **Persistence:** immutability triggers (SQLite + PostgreSQL, UPDATE/DELETE rejected); owner isolation; FK integrity; hash CHECKs; round-trip upgrade/downgrade (scout-migration suite pattern).
- **Replay:** same inputs → same artifact and `replay_state = match`; changed inputs → changed hash/new artifact; future-dated `as_known_at` excluded by `vintage_bound`; methodology change → `methodology_changed`, never silent; tampered stored hash/payload → repository error.
- **Evaluation:** correct baseline (window start = `recommendation_as_of`); zero price; insufficient history; missing observation; missing snapshot row → `blocked` (`missing_snapshot`), never re-derived; currency/basis mismatch → `not_comparable`.
- **Provider restatement/vintage:** same `observed_at`, later `as_known_at` → earlier artifact unchanged; new evaluation at later bound uses the new vintage.
- **Security:** cross-owner evaluation/artifact/snapshot reads → 404 non-enumerating; owner-id injection in request → 422; corrupted IDs/hashes rejected; unauthenticated → 401.
- **Idempotency:** identical evaluation request → single artifact; conflicting window/methodology → distinct artifacts, no overwrite.
- **Regression:** existing investment suites (`test_investment_outcome_tracking.py`, `test_investment_persistence_final.py`, `test_investment_persistence_http.py`, `test_outcome_evaluation_migration.py`, `test_investment_scout_migration.py`, migration/head checks) must stay green; no INV-08/09/11/UI-08..12 behavior changes.

---

## 23. INV-12 Completion Criteria

**INV-12 implementation complete** (reachable without D-8):
- [ ] D-1..D-3, D-6, D-7, D-9, D-10 frozen and documented; D-2 identity rule enforced in store writes
- [ ] Contracts typed and contract-tested (§5–§7)
- [ ] Three additive immutable stores migrated with one Alembic head; upgrade/downgrade/re-upgrade proven
- [ ] Evaluation engine reuses `evaluate_outcome()`; no parallel engine (reuse inventory audit passes)
- [ ] Replay C/D/E proven: idempotent artifacts, deterministic hashes, `replay_state` accurate, no future-information leakage, methodology drift detected
- [ ] Owner isolation, non-enumerating 404, client-injection rejection proven per route
- [ ] Read API typed, internal write boundary enforced (no browser/scheduler trigger)
- [ ] Failure modes fail closed with typed reason codes (§18)
- [ ] Regression suites green; documentation updated (this design + tracker/status)

**INV-12 production/multi-user ready** (NOT reachable without approvals):
- [ ] D-8 retention/deletion policy approved and retention slice implemented
- [ ] Multi-user deletion/orphan semantics approved (GAP-16/GAP-18 tenant boundary)
- [ ] Populated multi-owner data proof for the new surfaces

---

## 24. Required Product / Architecture Decisions (freeze list)

| ID | Decision | Options | Recommended | Owner | Status |
|---|---|---|---|---|---|
| D-1 | Substrate scope | investment / goal / both | **investment only** (roadmap intent; goal substrate is Phase-1 personal finance; IDs never cross substrates) | product owner | **APPROVED 2026-09-04** |
| D-2 | Security-identity rule for stores | portfolio_intelligence rule (resolve symbol+known type → `atlas-security`/`RESOLVED`) vs risk_scenarios rule (always `atlas-unresolved`) vs defer | **`atlas-security`/`RESOLVED` for symbol + known instrument type; anything else `atlas-unresolved` (`UNRESOLVED`/`UNSUPPORTED`) and ineligible for storage/evaluation; exact string equality only; GAP-09 refactor scheduled before population** | architecture (product owner here) | **APPROVED 2026-09-04** — GAP-09 refactor scheduled pre-population |
| D-3 | Replay semantics | A/B/C/D/E | **C+D+E now; A+B deferred** (§4) | product owner | **APPROVED 2026-09-04** |
| D-4 | Evaluation artifact storage | new table / extend outcomes / read-projection | **new `investment_evaluation_records`**, non-duplicative (§5a) | architecture | Freeze |
| D-5 | Snapshot store scope | payload + hash vs hash-only | **full payload + hash, single builder reused** (§7a) | architecture | Freeze |
| D-6 | Evaluation trigger | internal on-demand / job / scheduler | **internal on-demand** (§17) | architecture | Freeze |
| D-7 | Calibration | include / defer | **defer** (§13) | product owner | Freeze (deferral) |
| D-8 | Retention durations + deletion semantics | per §14 | **no automatic deletion; default-off until approved; delete path policy-designed** | product/security | **Architecture position APPROVED 2026-09-04** — durations/deletion policy remain open; retention slice gated |
| D-9 | CIO archive | required / not required | **not required** unless consumer dependency appears (§16) | product owner | Freeze |
| D-10 | Versioning | embedded strings / registry | **embedded strings**; registry only when a 2nd methodology exists (§12) | architecture | Freeze |

---

## 25. Final GO / NO-GO

**GO — INV-12 IS IMPLEMENTATION-READY (bounded first slice; retention slice remains approval-gated).**

- D-1 (investment substrate only), D-2 (identity rule + GAP-09 scheduling), D-3 (C+D+E now, A+B deferred), D-7 (calibration deferral), D-8 (architecture position: no auto-deletion; policy stays open for the retention slice), and D-9 (CIO archive not required) were approved by the product/architecture owner on 2026-09-04. D-4/D-5/D-6/D-10 are architectural and frozen by this design.
- The retention/deletion **slice** (durations, account deletion, legal hold) remains gated on the open D-8 product/security policy decision; implementation-complete per §23 does not require it.
- **NO-GO conditions were checked and do not apply:** no foundational contract is missing from this design (the three prerequisite contracts are now specified), and no architectural revision of INV-08/09/11 is required (all reuse is additive).

---

## 26. Recommended Next Codex Task

> **Implement the approved INV-12 contracts and prerequisite stores in the exact dependency order defined in §21a**, limited to: (1) the frozen contracts and enums, (2) the three additive immutable migrations (observation store, portfolio-snapshot store, `investment_evaluation_records`) after the GAP-09 shared-identity refactor (D-2) lands, (3) the evaluation/replay engine **reusing `evaluate_outcome()`**, (4) the owner-scoped read API with the internal write boundary, and (5) the deterministic/temporal/provenance/security tests and vertical slice (§21b). **Stop before the retention/deletion slice** (D-8) and before any calibration work (D-7 deferral). No execution, mutation, scheduling, or UI work.

---

*End of INV-12 design gate. Design only: no production code, migrations, API implementation, UI changes, commit, or push were made.*

---

## 27. Implementation Record (2026-09-04) — post-gate status

### 27a. Landed (committed, design §21a steps 1–8)

| §21a step | Status | Commit / evidence |
|---|---|---|
| 0–1. D-1/D-2/D-3/D-7/D-8(position)/D-9 approvals; GAP-09 scheduled | APPROVED | Executive Verdict table (2026-09-04) |
| 2. GAP-09 shared identity resolver (D-2) | Landed | `a8a6016` — `holding_identity.py` consumed by `portfolio_intelligence` (CANONICAL) and `risk_scenarios` (MASTER_VERIFIED_ONLY); byte-identical outputs per surface |
| 3–5. Three additive immutable stores + contracts | Landed | `a8a6016` — observation/snapshot/evaluation stores under single head `AE19a1b2c3d4e5`; 19 migration tests |
| 6. Persistence/service writers + engine reusing `evaluate_outcome()` | Landed | `f782ffd` — `EvaluationService` (`store_observation`, `store_portfolio_snapshot`, `evaluate`, replay); projections of the durable store into the `outcome_tracking` shape; values frozen only via `record_outcome()` |
| 7. Internal boundary + owner-scoped read API | Landed | `f782ffd` — `GET /api/v1/investments/evaluations`, `/{evaluation_id}`, `/{evaluation_id}/replay` (auth, non-enumerating 404, typed envelopes, no write routes) |
| 8. Deterministic/temporal/provenance/security tests + vertical slice | Landed | `f782ffd` — 15 new tests; vertical slice (§21b) proves store→outcome→artifact→replay-match; broad regression 119 passed |

**Two recorded implementation deviations (both fail closed; neither changes a certified INV-08/09/11 contract):**

1. **SQLite datetime normalization before `record_outcome()`.** SQLite strips tzinfo when persisting `DateTime(timezone=True)`, so the certified persistence service's aware-vs-naive `evaluation_as_of >= recommendation_as_of` comparison would trip under the repo's SQLite test DB. `evaluation_service.evaluate()` converts the identity-mapped recommendation row's stored instant back to aware UTC immediately before delegating. On PostgreSQL (the production dialect) this is a no-op. No certified code changed.
2. **Temporal violation is a typed service error, not a persisted artifact.** An evaluation whose `evaluation_as_of` precedes the baseline cannot be recorded honestly as an artifact without violating the immutable DB CHECK `evaluation_as_of >= evaluation_window_start` (blocked artifacts carry their typed reason only in `payload_json`, not as a column). The evaluator therefore raises `EvaluationServiceError('temporal_violation')` and persists nothing — fail closed with a typed reason (design §18) rather than fabricate a row. `EvaluationResultState.TEMPORAL_VIOLATION` remains part of the contract vocabulary for future use.

**Integration-hook note (by design, not a defect):** the store writers exist but no *live* flow calls them yet — no route persists recommendations today, so the recommendation-persist snapshot-write hook and provider-adapter observation ingestion will be wired when those flows materialize. The engine is proven end-to-end via the service vertical slice (§21b) and the read API serves persisted artifacts.

### 27b. Remaining gates

**INV-12 implementation-complete (§23)** — the code-level work above is done; what remains is evidence + documentation: certification evidence recording (this doc + tracker), and the live integration hooks noted in §27a.

**INV-12 production/multi-user ready (§23)** — NOT reachable without approvals:
- D-8 retention/deletion policy (PRODUCT/SECURITY decision required) + the retention slice; architecture position approved (no auto-deletion; future deletion = policy-designed soft-tombstone).
- Multi-user deletion/orphan semantics (GAP-16/GAP-18) and a populated multi-owner data proof.

**Explicitly deferred (D-3/D-7/D-9/D-10):** replay A+B (until real vintaged observation history exists), calibration, CIO archive, methodology registry (until a second methodology), scheduler/background evaluation, and any UI surface for evaluations.

### 27c. Tracker

- `work-inv-12-foundation-durable-stores` — complete, `a8a6016`.
- `work-inv-12-evaluation-engine-and-read-api` — complete, `f782ffd`.
- Phase `inv-12`: `in_progress`; exit criterion `ec-inv-12-boundary` (evaluation/calibration/replay and retention boundary implemented and certified) remains open until §27b implementation-complete evidence is recorded and the retention/calibration boundaries are closed by the approvals above.
