# Atlas Investment Intelligence — Consolidated Execution Plan

**Status:** INV-PERSIST-03 committed and validated; UI-08 readiness certification remains the next bounded work item
**Authority:** Existing INV-01–INV-HARDEN-01 implementation records, UI/UX architecture and roadmap, canonical project tracker, and repository tests
**Scope:** Safe completion of the investment application boundary, followed by gated UI delivery

## Executive decision

INV-01 through INV-11 domain foundations and the additive INV-PERSIST-03 boundary are implemented. The next work is an explicit HTTP/API readiness certification, followed by UI-08. Later UI and INV-12 work remain intentionally sequenced and unstarted.

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
| UI-08 | Blocked pending readiness certification | Must consume only server-owned investment APIs and record human decisions without execution. |
| UI-09–UI-12 | Not started | Each requires its own contract and validation gate. |
| INV-12 | Not started | Evaluation/calibration/replay/retention extensions are intentionally deferred. |

## Completed persistence boundary

The committed investment persistence boundary contains owner-scoped durable records for committee runs/findings, bounded evidence packets, recommendations, human decisions, and outcomes. `InvestmentRepository` validates persisted recommendation and committee snapshots before projection; evidence membership is represented by explicit link tables; outcome decision linkage is optional and explicit; decision writes require `If-Match` and `Idempotency-Key`; no analytical public ingestion route or execution path exists.

The historical PERSIST-01 document remains uncommitted as historical work. Unrelated dirty backend/UI files remain untouched.

## Validation evidence

The focused and affected investment, recommendation, decision, outcome, scenario, and assistant suites have passed in the repository-managed environment. The current combined selection recorded **327 investment/affected tests** in the persistence validation and **177 additional scenario/assistant/route tests** in the broader validation pass. Python compilation, Alembic one-head/import checks, and `git diff --check` passed. The current Alembic head is `AA15a1b2c3d4e5`.

## Readiness certification still required

Before UI-08 begins, add and run dedicated TestClient/API tests covering owner isolation across all investment routes, lifecycle eligibility, stale `If-Match`, malformed commands, evidence membership/provenance/temporal rejection, outcome decision linkage, and sequential/simulated concurrent idempotency. This certification must verify that typed responses remain bounded and that goal/forecast records cannot appear through investment routes.

## Future sequence

1. Complete the dedicated HTTP/API readiness certification for INV-PERSIST-03.
2. Implement UI-08 recommendation review and human decision, without execution controls.
3. Add INV-10 report archive only if a concrete UI/report requirement requires it.
4. Implement UI-09 bounded opportunity discovery/comparison.
5. Implement UI-10 read-only contextual Scout with citations and prompt-injection defenses.
6. Implement UI-11 hypothetical risk/scenario presentation from server-owned projections.
7. Implement INV-12 evaluation, calibration, replay, and retention policy.
8. Implement UI-12 cross-route trust, privacy, accessibility, performance, and execution-boundary certification.

## Safety and non-goals

No phase in this plan authorizes broker integration, order creation, trading, execution, transfers, money movement, portfolio mutation, automatic rebalancing, autonomous scheduling, or browser-side financial calculations. Investment decisions remain human-controlled records.

## Rollback

Disable future investment route activation or UI feature flags without altering goal/forecast records, holdings, Market Briefs, or immutable investment history. Never roll back by deleting or rewriting analytical, decision, or outcome records.
