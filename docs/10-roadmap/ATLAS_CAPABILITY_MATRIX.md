# Atlas Phases 0–6 Capability Matrix

- **Audit date:** 2026-08-15
- **Audited commit:** `ff85ad7bc39680a2beb13533795478e515cda931`
- **Certification tag:** `phase-6-complete` resolves to `ff85ad7bc39680a2beb13533795478e515cda931`
- **Scope:** repository and isolated synthetic local acceptance evidence for Phases 0–6; no personal database, real provider, email, trading, money movement, or production execution.
- **Related reports:** [Personal-Use Readiness Report](../07-engineering/PERSONAL_USE_READINESS_REPORT.md), [System Health Audit](../07-engineering/SYSTEM_HEALTH_AUDIT.md), [UI Acceptance Matrix](../06-ui-ux/UI_ACCEPTANCE_MATRIX.md), [Remediation Backlog](./REMEDIATION_BACKLOG.md), and [Personal Mode Proposal](../07-engineering/PERSONAL_MODE_PROPOSAL.md).

## Evidence sources

- `docs/00-product-vision/ATLAS_MASTER_PRODUCT_SPEC.md`
- `docs/06-ui-ux/ATLAS_INFORMATION_ARCHITECTURE_AND_UI_MIGRATION_PLAN.md`
- `docs/07-engineering/SCENARIO_LAB_CONTRACT.md`
- `docs/10-roadmap/PHASE6_SCENARIO_LAB_PLAN.md`
- `docs/10-roadmap/COMPLETED_PHASES.md`
- `docs/10-roadmap/CURRENT_HANDOFF.md`
- `docs/10-roadmap/PROJECT_STATUS.json` and generated `PROJECT_STATUS.md`
- Rules Service routes, services, models, and Alembic revisions
- `ui/lib/informationArchitecture.ts`, `ui/components/layout/Sidebar.tsx`, and primary `ui/app/**/page.tsx` routes
- Clean-main Phase 6 certification evidence recorded in `COMPLETED_PHASES.md` and `PHASE6_CERTIFICATION_RECONCILIATION.md`
- Isolated synthetic browser acceptance: canonical route-mocked journeys and focused live-stack journeys described in the audit report.

**Confirmed facts** are stated directly. Statements labelled **Inference** are conclusions from repository structure or test coverage and require confirmation before product changes.

## Final route ownership

| Domain | Authoritative route | Primary navigation | State contract |
|---|---|---|---|
| Home | `/` | Home → Mission Control | Cross-domain bounded summaries only |
| Money | `/cash-flow` | Money → Cash Flow | `view=overview\|income\|spending\|transactions`; legacy Money routes redirect |
| Money | `/plan` | Money → Plan | `view=budget\|commitments\|calendar` |
| Wealth | `/wealth` | Wealth → Wealth | `view=overview\|assets\|debts\|universe`; `/debts` and `/universe` redirect |
| Wealth | `/portfolio` | Wealth → Portfolio | Holdings/allocation/performance/risk specialist surface |
| Wealth | `/goals` | Wealth → Goals | Goals/forecasts/progress specialist surface |
| Intelligence | `/decisions` | Intelligence → Decisions | `view=recommendations\|journal\|outcomes`; `/recommendations` redirects |
| Intelligence | `/market-intelligence` | Intelligence → Market Intelligence | Portfolio/pulse/earnings/scanner/archive; `/market-briefs` redirects |
| Intelligence | `/scenario-lab` | Intelligence → Scenario Lab | `view=scenarios\|comparisons\|archive`, goal/scenario/compare query state |
| System | `/data-connections` | System → Data Connections | Accounts/imports/synchronization/data quality; `/accounts` redirects |
| System | `/settings` | System → Settings | Appearance, accent profile, safe preferences and data maintenance |
| System | `/help` | System → Help | Product navigation, limitations, privacy and recovery guidance |

Phase 0 is foundational and intentionally has no page. Phases 1–4 are also primarily backend/foundation capabilities surfaced through Goals and Decisions rather than separate duplicate pages. Phase 5 is presented through Market Intelligence. Phase 6 is presented through Scenario Lab.

## Capability matrix

| Phase | Capability | Intended user outcome | Backend/module and endpoint | Persistence | UI route/tab | Navigation | Flags/config | Honest state | Status and usability | Test evidence | Documentation | Limitations/disposition |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | Projection foundation | Deterministic projection inputs and outputs | Rules `calculations/projection.py`; canonical contracts | None by itself | No standalone page | Foundational | None | Invalid or stale inputs fail closed | **Confirmed implemented**; not a user destination | Phase 6 and prior clean-main suites | Phase 0 records; ADR-005 | Decimal authority remains server-side; keep foundational |
| 0 | Decimal correctness and rounding | Repeatable money values | Rules Decimal contracts and projection engine | Snapshots where later phases persist | Consumed by Goals and Scenario Lab | Foundational | None | Non-finite/out-of-range values rejected | **Confirmed implemented** | Projection/scenario focused suites | Scenario contract | Legacy non-authoritative modules still contain floats; see audit |
| 0 | Canonical contracts and synthetic fixtures | Safe, reproducible development | `forecasts/canonical_state.py`; `tests/synthetic_fixtures` | Test fixtures only | No standalone page | Foundational | None | Missing authority/currency fails closed | **Confirmed implemented** | Canonical and synthetic fixture tests | Phase 0/1 records | Synthetic fixtures do not prove local personal data readiness |
| 0 | Foundational architecture | Clear service and dependency boundaries | Rules Service, Finlynq, UI, local lifecycle | Shared local SQLite by documented dev path | Shared shell | System support | Separate Python environments | Missing environment is an operator error | **Implemented; setup cost remains** | Environment and startup tests | `LOCAL_PYTHON_ENVIRONMENTS.md` | Two service environments are required |
| 1 | Immutable forecast identity/versioning | Reopen an exact forecast baseline | Forecast models/repository; `/api/v1/goals/{goal_id}/forecasts` generation and version routes | `forecasts`, `forecast_versions` | Goals → Forecasts | Wealth → Goals | `ATLAS_FORECAST_PERSISTENCE_ENABLED=false` by default | Disabled, missing, stale, and conflict states | **Implemented; unavailable by default** | Forecast service, repository, migration and route tests | ADR-006; forecast plan | Personal Mode must not auto-enable until currency authority is resolved |
| 1 | Forecast generation | Create a server-authoritative baseline | Rules forecast service and Finlynq projection adapter | Immutable forecast versions | Goals → Forecasts | Wealth → Goals | Persistence flag, trusted adapter | No client generation when unavailable | **Implemented; local activation requires config/data** | Forecast generation and adapter tests | Phase 1 evidence | No confirmed operator-ready activation path with real local data |
| 1 | Forecast read API | Read persisted baseline safely | Typed forecast read routes and codecs | Forecast snapshots | Goals → Forecasts; Scenario Lab readiness | Wealth/Intelligence deep links | Read flag default off | No recommendation/scenario inferred without read authority | **Implemented; default-off** | Read-route and default-off tests | ADR-006 | Requires reviewed server configuration |
| 1 | Trusted canonical state boundary | Prevent client-supplied financial authority | Finlynq projection-state provider and Rules adapter | Provenance/hash fields in snapshots | No standalone page | Foundational | Server-owned | Missing/cross-owner/unsupported currency rejected | **Confirmed implemented** | Provider, hash, ownership and privacy suites | Forecast contract | Account currency authority remains open P1 risk |
| 2 | Deterministic recommendations | See a bounded next action grounded in a forecast | `forecasts/recommendation_engine.py`; derived recommendation routes | `recommendations`, linked journal records | Decisions → Recommendations | Intelligence → Decisions | Depends on forecast read authority | No recommendation if current evidence absent | **Implemented; often unavailable by default** | Recommendation contract and route suites | Decision/recommendation plans | Acceptance is not execution or success |
| 2 | Explanation/evidence | Understand why a recommendation exists | Recommendation schemas and server-derived evidence | Immutable recommendation data | Decisions → Recommendations | Intelligence → Decisions | Forecast/read gates | Evidence date, risks, confidence, limitations | **Implemented** | Recommendation schema/privacy tests | Domain and Phase 3 docs | Evidence remains bounded and privacy-safe |
| 2 | Decision journal | Record accept/reject/defer intent | Decision journal service; `/api/v1/recommendations/{id}/decisions` | Append-only journal | Decisions → Recommendations/Journal | Intelligence → Decisions | Server-owned | Sanitized conflict/precondition errors | **Implemented** | Decision journal, ETag, idempotency tests | ADR-004; journal plan | Does not execute actions |
| 3 | Outcome evaluation | See pending/not-measurable/measured lifecycle | Outcome evaluation service and routes | `outcome_evaluations` | Decisions → Outcomes; compact related summaries | Intelligence → Decisions | History/read gates | Pending, not measurable, measured shown explicitly | **Implemented; evidence dependent** | Outcome service/migration/privacy suites | Phase 3 plans | No claim of success from acceptance |
| 3 | Evidence-reference safeguards | Avoid raw sensitive evidence exposure | Hash-only evidence references and allowlist | Immutable outcome rows | Decisions → Outcomes | Intelligence → Decisions | Server-side | Sanitized errors and bounded evidence | **Confirmed implemented** | Privacy and outcome tests | ADR-004; security docs | Hashes do not make underlying retention policy complete |
| 4 | Decision history | Reload prior decisions | Decision history routes/services; `/api/v1/goals/{goal_id}/decision-history` | `decision_history_entries`, audit events | Decisions → Journal/Outcomes; Goals compact history | Intelligence → Decisions | `ATLAS_DECISION_HISTORY_API_ENABLED=false` | Loading/unavailable and immutable ordering states | **Implemented; default-off** | History route/API/UI/remount tests | Phase 4 plan | Personal activation requires explicit review |
| 4 | Append-only linkage | Preserve decision/outcome identity | Server IDs and lifecycle values | Decision history and outcome foreign keys | Decisions → Journal/Outcomes | Intelligence → Decisions | Server-owned | Cross-owner resources are indistinguishable 404s | **Confirmed implemented** | Owner-isolation/idempotency tests | ADR-004 | Retention/deletion policy remains open for multi-user rollout |
| 5 | Portfolio market intelligence | Review cited market context | `market_intelligence`; `/api/v1/market-briefs`, `/pulse`, `/{brief_id}` | `market_briefs`, delivery records | Market Intelligence → Portfolio/Pulse/Earnings/Archive | Intelligence → Market Intelligence | Read/generation/provider/email/scheduler/local flags default off | Fresh/stale/degraded/unavailable/warning states | **Implemented; synthetic journey usable; provider off by default** | Market foundation, brief, provider and UI journeys | ADR-007; Phase 5 plans | No provider activation was attempted in audit |
| 5 | Quotes/news/earnings/citations/freshness | Distinguish evidence from interpretation | Provider adapters and typed brief contracts | Cited immutable brief snapshots | Market Intelligence specialist tabs | Intelligence | External provider requires server config and key | Omitted mappings and stale data are named | **Implemented where authoritative mapping exists** | Synthetic archive/detail/axe/mobile tests | Phase 5 operational audit | No authoritative CIK mapping means filings may be omitted |
| 5 | Brief generation/archive/detail | Generate and revisit a brief | `/generate`, list, detail routes | Immutable owner-scoped briefs | Market Intelligence → Archive | Intelligence | Generation/read/provider gates | Empty/disabled/provider recovery | **Implemented and route-mocked tested** | Synthetic generate/archive journey passed | Phase 5 records | Real local provider path still needs operator validation |
| 6 | Scenario identity/versioning | Reopen an exact what-if result | `scenarios/service.py`, `repository.py`, `models/scenario.py` | `scenarios`, immutable `scenario_versions` | Scenario Lab → Archive | Intelligence → Scenario Lab | `ATLAS_SCENARIO_LAB_ENABLED=false` | Missing/stale/incompatible state | **Implemented; default-off** | 72 focused backend tests in certification | ADR-008; Scenario contract | No probability or trajectory claims |
| 6 | Server-authoritative deterministic scenarios | Compare bounded changes safely | `POST /api/v1/goals/{goal_id}/scenarios` | Immutable version snapshots | Scenario Lab → Scenarios | Intelligence | Scenario flag | Decimal strings, deterministic bands, warnings | **Implemented; synthetic route-mocked journey passed** | Scenario contract, engine, route suites | Phase 6 plan | Requires baseline and compatible USD authority |
| 6 | Comparisons | Compare one to three explicit scenarios | `/api/v1/scenarios/compare`, `/compare` | Reads immutable versions | Scenario Lab → Comparisons | Intelligence | Scenario flag | Incompatible selections recover explicitly | **Implemented and tested** | Comparison focus and browser journeys | Scenario contract | No automatic “first three” selection |
| 6 | Archive/history | Archive lifecycle without deleting history | `/api/v1/scenarios/{id}/archive` and list | Lifecycle on identity; versions immutable | Scenario Lab → Archive | Intelligence | Scenario flag | Archived entries remain reviewable | **Implemented and tested** | Archive/idempotency tests and browser journey | Scenario contract | No destructive delete path |
| 6 | Scenario Lab baseline readiness | Know why modeling is unavailable | `ScenarioReadiness`, typed client | No client authority | Scenario Lab → Scenarios | Intelligence | Server-owned | Disabled/no goal/missing/stale/error/loading | **Implemented and browser-tested** | 4 route-mocked journeys in certification | Phase 6 Slice 2 plan | Full local activation not proven with a real forecast |

## Evidence gaps

1. No acceptance run used personal financial data; therefore personal-data migration/recovery behavior is intentionally unproven.
2. No real Finnhub/SEC credentials or provider calls were used; market provider readiness remains a configuration task.
3. The default-off forecast, decision-history, market, and Scenario Lab flags prevent one complete enabled end-to-end financial journey from being demonstrated without a separate reviewed local configuration.
4. Screenshot capture generated 126 external screenshots at `/tmp/atlas-phase0-6-audit-ff85ad7-screenshots`; the legacy matrix stopped on a migrated Market Briefs/Market Intelligence route harness expectation. Existing tracked artifacts were restored and no screenshots were committed.
5. The repository has no proven automated backup/restore drill for a personal SQLite database.

## Recommended disposition

Treat Phases 0–6 as certified implementation with a **personal-use activation audit gap**, not as permission to enable all flags. Use [REMEDIATION_BACKLOG.md](./REMEDIATION_BACKLOG.md) and [PERSONAL_MODE_PROPOSAL.md](../07-engineering/PERSONAL_MODE_PROPOSAL.md) before enabling any server-owned capability.
