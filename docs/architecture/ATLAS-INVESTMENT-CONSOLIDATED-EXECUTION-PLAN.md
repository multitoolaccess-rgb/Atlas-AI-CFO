# Atlas Investment Intelligence — Consolidated Execution Plan

**Status:** UI-08 certified; UI-09 backend foundation in progress using approved separated current-only portfolio and bounded S&P 500 modes
**Authority:** Existing INV-01–INV-HARDEN-01 implementation records, UI/UX architecture and roadmap, canonical project tracker, and repository tests
**Scope:** Safe completion of the investment application boundary, followed by gated UI delivery

## Executive decision

INV-01 through INV-11 domain foundations and the additive INV-PERSIST-03 boundary are implemented. UI-08 now has a server-backed review route and typed client; the remaining roadmap phases require additional bounded contracts and are not yet complete.

```text
INV-01–07 canonical evidence and research
        ↓
INV-08 committee finding
        ↓
INV-09 investment recommendation
        ↓
INV-PERSIST-03 trusted repository/application boundary
        ↓
HTTP/API readiness certification
        ↓
UI-08 recommendation review
        ↓
INV-11 decision/outcome history
        ↓
INV-12 evaluation and trust review
```

## Phase status

| Phase | Status | Notes |
|---|---|---|
| INV-01–INV-07 | Complete | Canonical identity, observations, portfolio, research, macro, and quant contracts are established. |
| INV-08 | Complete | Committee contracts and deterministic evidence-linked findings are established. |
| INV-09 | Complete | Investment recommendation taxonomy and lifecycle contracts are established. |
| INV-10 | Bounded complete | CIO projection exists; archive/delivery/scheduling are future extensions. |
| INV-11 | Complete through persistence boundary | Decision/outcome contracts and durable investment records exist; evaluation/calibration extensions remain future work. |
| INV-HARDEN-01 | Complete | Temporal, provenance, hash, ownership, and fail-closed safeguards remain authoritative. |
| INV-PERSIST-03 | Committed/validated | Commits `55644b3` and `c4b0148`; additive relationship hardening is included. |
| UI-01 | Complete as planning checkpoint | Architecture and adoption rules are documented. |
| UI-02–UI-07 | Implemented in repository | Navigation, brief, portfolio, research, chart adapter, and evidence components exist. |
| UI-08 | Certified | Recommendation review, committee context, bounded evidence, decision history, outcome history, human decision recording, and HTTP auth/precondition coverage are committed and validated. |
| UI-09 | Backend foundation in progress | Approved scope: separate current-only portfolio and bounded S&P 500 modes, deterministic filtering/stable ordering, no discovery score. Typed API/HTTP validation and UI remain pending. See `ATLAS-INVESTMENT-UI-09-READINESS-AND-EXECUTION-PLAN.md`. |
| UI-10 | Not started | Requires a typed investment-context assistant boundary and citation tests. |
| UI-11 | Partially available via existing Scenario Lab | A dedicated investment risk/scenario projection surface is not implemented. |
| UI-12 | Not started | Requires cross-route trust, privacy, accessibility, performance, and execution-boundary certification. |
| INV-12 | Not started | Evaluation/calibration/replay/retention extensions are intentionally deferred. |

## Completed persistence boundary

The committed investment persistence boundary contains owner-scoped durable records for committee runs/findings, bounded evidence packets, recommendations, human decisions, and outcomes. `InvestmentRepository` validates persisted recommendation and committee snapshots before projection; evidence membership is represented by explicit link tables; outcome decision linkage is optional and explicit; decision writes require `If-Match` and `Idempotency-Key`; no analytical public ingestion route or execution path exists.

The historical PERSIST-01 document remains uncommitted as historical work. Unrelated dirty backend/UI files remain untouched.

## Validation evidence

The focused and affected investment, recommendation, decision, outcome, scenario, and assistant suites have passed in the repository-managed environment. The current combined selection recorded **327 investment/affected tests** in the persistence validation and **177 additional scenario/assistant/route tests** in the broader validation pass. Python compilation, Alembic one-head/import checks, and `git diff --check` passed. The current Alembic head is `AA15a1b2c3d4e5`.

## UI-08 certification evidence

The UI-08 slice and dedicated authenticated HTTP boundary tests are committed. The tests cover unauthenticated access, owner-subject isolation, non-enumerating not-found behavior, required `If-Match`/`Idempotency-Key`, malformed command rejection, typed route boundaries, and no raw persistence leakage. Full production-like multi-owner seeded-record tests remain a future environment expansion, not a browser-side workaround.

## UI-09 readiness and execution plan

The UI-09 readiness audit found no complete durable Security/Instrument master or approved discovery/screening methodology. The approved first slice is now explicitly bounded to separate current-only portfolio and S&P 500 modes, with deterministic filtering/stable ordering and no discovery score. Holdings remain owner-scoped current-state input; the S&P 500 file remains a bounded factual universe input; Market Brief and recommendations remain downstream.

The authoritative plan is documented in `docs/architecture/ATLAS-INVESTMENT-UI-09-READINESS-AND-EXECUTION-PLAN.md`. The approved source decision is separate current-only portfolio and bounded S&P 500 modes; the source adapter and typed API foundation are now being implemented. UI-09 remains incomplete until HTTP/API and UI certification gates pass.

## Future sequence

1. Complete UI-09 source adapter and typed API/HTTP certification.
2. Implement UI-09 bounded opportunity discovery/comparison UI.
3. Add INV-10 report archive only if a concrete UI/report requirement requires it.
5. Implement UI-10 read-only contextual Scout with citations and prompt-injection defenses.
6. Implement UI-11 hypothetical risk/scenario presentation from server-owned projections.
7. Implement INV-12 evaluation, calibration, replay, and retention policy.
8. Implement UI-12 cross-route trust, privacy, accessibility, performance, and execution-boundary certification.

## Safety and non-goals

No phase in this plan authorizes broker integration, order creation, trading, execution, transfers, money movement, portfolio mutation, automatic rebalancing, autonomous scheduling, or browser-side financial calculations. Investment decisions remain human-controlled records.

## Rollback

Disable future investment route activation or UI feature flags without altering goal/forecast records, holdings, Market Briefs, or immutable investment history. Never roll back by deleting or rewriting analytical, decision, or outcome records.
