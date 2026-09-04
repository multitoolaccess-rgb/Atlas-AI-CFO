# Atlas Investment Intelligence — Consolidated Execution Plan

**Status:** UI-09, UI-10 (including the approved bounded provider-backed Scout expansion), and the bounded current-only UI-11 slice complete/certified; UI-12 and INV-12 remain gated
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
| UI-09 | Complete for approved bounded scope | Separate current-only portfolio and bounded S&P 500 modes, deterministic filtering/stable ordering, typed APIs, comparison/detail UI, accessibility/browser validation. Commit `db69bf3`. |
| UI-10 | Complete/certified for bounded read-only Scout scope | Typed context/tool/query boundary, model response citation validation, prompt fencing, refusal/offline behavior, HTTP tests, and responsive/accessibility browser validation are complete. |
| UI-11 | Complete for bounded current-only slice | Server-owned current-only baseline, descriptive value/data-quality metrics, on-demand hypothetical value preview, typed API, and browser safeguards are certified. Historical/advanced risk remains deferred. |
| UI-12 | Not started — final certification | Requires stable UI-10/UI-11 decisions and contracts, INV-12 boundary decision, route inventory, privacy matrix, and full certification evidence. |
| INV-12 | Not started — prerequisite required | Requires evaluation artifact/replay definitions, calibration methodology, and approved retention/deletion policy; existing outcome tracking is an input, not full INV-12. |

## Completed persistence boundary

The committed investment persistence boundary contains owner-scoped durable records for committee runs/findings, bounded evidence packets, recommendations, human decisions, and outcomes. `InvestmentRepository` validates persisted recommendation and committee snapshots before projection; evidence membership is represented by explicit link tables; outcome decision linkage is optional and explicit; decision writes require `If-Match` and `Idempotency-Key`; no analytical public ingestion route or execution path exists.

The historical PERSIST-01 document remains uncommitted as historical work. Unrelated dirty backend/UI files remain untouched.

## Validation evidence

The focused and affected investment, recommendation, decision, outcome, scenario, and assistant suites have passed in the repository-managed environment. The current combined selection recorded **327 investment/affected tests** in the persistence validation and **177 additional scenario/assistant/route tests** in the broader validation pass. Python compilation, Alembic one-head/import checks, and `git diff --check` passed. The current Alembic head is `AA15a1b2c3d4e5`.

## UI-08 certification evidence

The UI-08 slice and dedicated authenticated HTTP boundary tests are committed. The tests cover unauthenticated access, owner-subject isolation, non-enumerating not-found behavior, required `If-Match`/`Idempotency-Key`, malformed command rejection, typed route boundaries, and no raw persistence leakage. Full production-like multi-owner seeded-record tests remain a future environment expansion, not a browser-side workaround.

## UI-09 readiness and execution plan

The UI-09 readiness audit found no complete durable Security/Instrument master or approved discovery/screening methodology. The approved first slice is now explicitly bounded to separate current-only portfolio and S&P 500 modes, with deterministic filtering/stable ordering and no discovery score. Holdings remain owner-scoped current-state input; the S&P 500 file remains a bounded factual universe input; Market Brief and recommendations remain downstream.

The authoritative plan is documented in `docs/architecture/ATLAS-INVESTMENT-UI-09-READINESS-AND-EXECUTION-PLAN.md`. The approved source decision is separate current-only portfolio and bounded S&P 500 modes; UI-09 is complete for that bounded scope under commit `db69bf3`.

## Remaining-phase audit and execution plan

The comprehensive audit is documented in `ATLAS-INVESTMENT-REMAINING-PHASES-AUDIT-AND-EXECUTION-PLAN.md`; the UI-11 decision is recorded in `ADR-UI-11-CURRENT-PORTFOLIO-RISK-BOUNDARY.md`. These documents record the current capabilities, missing advanced contracts, security/temporal/provenance gates, dependency graph, and bounded execution tasks for INV-10 extensions, INV-12, UI-10, UI-11, and UI-12.

## UI-10 certification status

UI-10 is complete/certified for the bounded read-only Scout scope. The isolated contextual boundary defines `InvestmentAssistantContext/v1`, `InvestmentAssistantQueryRequest/v1`, an allowlisted read-only investment tool, typed citation/response contracts, prompt-injection fencing, sanitized refusal/offline behavior, and authenticated endpoints at `/api/v1/investments/assistant/{context,tool,query}`. The separate provider-backed research boundary defines `InvestmentScoutResearchRequest/v1`, `InvestmentScoutSource/v1`, `InvestmentScoutClaim/v1`, `InvestmentScoutResearchResult/v1`, and `InvestmentScoutRunSummary/v1`, with authenticated routes at `/api/v1/investments/scout/research`, `/api/v1/investments/scout/runs`, and `/api/v1/investments/scout/runs/{run_id}` plus the `/investments/scout` UI. It accepts exactly one bounded selector, resolves provider research only through an owner-held canonical security (including recommendation/committee selectors that reference that held security), validates and source-links provider records, strips credential-bearing source query parameters, persists immutable owner-scoped results, and leaves general `/api/assistant/*` behavior unchanged. There is no unrestricted web search, arbitrary URL retrieval, general crawler, private portfolio-fact prompt context, or provider beyond the bounded existing Finnhub/SEC adapters; current-context and metadata limitations remain explicit.

## UI-10 provider-backed Scout expansion status

The approved UI-10 expansion is implemented as a separate server-owned, current-context research boundary rather than a direct browser-to-web or browser-to-LLM path. It reuses the existing Finnhub and SEC adapters, exposes strict source and claim projections, rejects future publication/retrieval timestamps, excludes client-supplied sources and financial facts, persists immutable owner-scoped runs, and has focused domain/HTTP/migration/UI evidence. The new `/investments/scout` route is included in the UI-12 read-only route inventory. Recommendation and committee selectors do not independently resolve a security-master record; the referenced canonical security must also be present as a resolved held security for the authenticated owner.

## Future sequence

1. Preserve the certified bounded UI-11 current-only baseline and descriptive hypothetical preview.
2. Define and approve any future historical or advanced portfolio-risk methodology separately before expanding UI-11.
3. Define the INV-12 evaluation/replay artifact and retention boundary.
4. Implement INV-12 evaluation, calibration, replay, and retention policy only after its prerequisite decisions are approved.
5. Add INV-10 report archive only if a concrete UI/report requirement requires it.
6. Implement UI-12 cross-route trust certification after the final approved surfaces and policies are stable.
7. Preserve explicit personal-use/default-off boundaries during all later work.
8. Do not start UI-12 or INV-12 concurrently; each requires its own contract and validation gate.

## Safety and non-goals

No phase in this plan authorizes broker integration, order creation, trading, execution, transfers, money movement, portfolio mutation, automatic rebalancing, autonomous scheduling, or browser-side financial calculations. Investment decisions remain human-controlled records.

## Rollback

Disable future investment route activation or UI feature flags without altering goal/forecast records, holdings, Market Briefs, or immutable investment history. Never roll back by deleting or rewriting analytical, decision, or outcome records.
