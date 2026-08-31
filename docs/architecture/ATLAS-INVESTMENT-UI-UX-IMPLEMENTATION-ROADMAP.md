# Atlas Investment Intelligence UI/UX Implementation Roadmap

**Status:** Planning only — UI/UX-01 checkpoint
**Authority:** `docs/architecture/ATLAS-INVESTMENT-UI-UX-ARCHITECTURE.md`
**Scope:** Future read-only investment UI delivery; no phases below are started by this document.

## Delivery rules

- Preserve the existing Next.js/React shell, Atlas tokens, route compatibility, and shared primitives.
- Implement one bounded slice at a time with explicit loading, empty, partial, stale, unavailable, and error states.
- Consume Atlas-owned read models only; the browser never calls financial-data providers directly.
- Keep recommendations separate from execution. Buttons record review/decision intent only.
- Stage only files owned by the active UI phase; preserve unrelated worktree changes.
- Each phase requires focused tests, TypeScript, lint/build checks appropriate to scope, accessibility checks, and a rollback plan.
- A UI phase may proceed in parallel with backend work when its read-only contract is stable; it does not authorize or block backend INV phases by itself.

## Phase map

| Phase | Outcome | Backend dependency | Status |
|---|---|---|---|
| UI-01 | Architecture, adoption matrix, and roadmap | INV-01–07 documentation/contracts | Complete as planning checkpoint only |
| UI-02 | Investment navigation and route contracts | Stable read-only route/read-model decision | Planned |
| UI-03 | Daily Investment Brief | INV-08 findings and/or INV-10 report envelope | Planned |
| UI-04 | Portfolio Intelligence views | INV-03 snapshot/analytics projection | Planned |
| UI-05 | Security Research workspace | INV-02, INV-04, INV-05, INV-06, INV-07 projections | Planned |
| UI-06 | Financial visualization adapter | Stable chart payloads and accessibility requirements | Planned |
| UI-07 | Evidence and provenance experience | INV-01 evidence packets; domain provenance | Planned |
| UI-08 | Recommendation review and user decision | INV-08/09 typed lifecycle | Planned |
| UI-09 | Opportunity discovery and comparison | Future screening/comparison read models | Planned |
| UI-10 | AI investment workspace | INV-08 typed assistant/context boundary | Planned |
| UI-11 | Risk and scenario views | INV-03 risk, later scenario contracts | Planned |
| UI-12 | Integration hardening and trust review | INV-10–12 reports, tracking, evaluation | Planned |

## UI-02 — Investment navigation and route contracts

**Objective:** Add only the minimum navigation/route contract needed to expose future investment surfaces without destabilizing current routes.

**Dependencies:** UI-01; decision whether Investment Brief is a new route or Market Intelligence view; stable backend route ownership.

**Surfaces:** sidebar/command discovery, `/investments` or equivalent, security deep-link contract, compatibility redirects, breadcrumbs.

**Backend:** no new provider calls; read-only route existence and authorization contract.

**Open-source dependencies:** none; reuse `informationArchitecture.ts`, Lucide, PageTabs, PageLayout.

**Tests:** route/redirect contract, active navigation, keyboard navigation, mobile menu, unauthorized/error route behavior, no execution vocabulary.

**Acceptance:** Existing routes remain usable; new destinations activate only when complete; no duplicate portfolio or recommendation lifecycle.

**Rollback:** disable destination activation and retain compatibility redirects.

## UI-03 — Daily Investment Brief

**Objective:** Give users a concise morning review of portfolio changes, market/macro context, attention items, evidence coverage, and later recommendations.

**Dependencies:** stable immutable brief/report envelope; ideally INV-08 findings and INV-10 report profile; existing Market Intelligence evidence patterns.

**Surfaces:** brief header/as-of, portfolio movement, attention rail, macro/market context, opportunities placeholder only when data exists, archive link.

**Backend:** report envelope, coverage, freshness, warnings, source/evidence references, owner-scoped portfolio sections.

**Open-source dependencies:** none initially; retain Recharts for compact trends.

**Tests:** fixture rendering, loading/empty/partial/stale/error states, citation links, keyboard disclosure, mobile order, screen-reader summary, privacy redaction.

**Acceptance:** “What changed?” is answered before action language; limitations are visible; no recommendation appears without evidence and user-control copy.

**Rollback:** hide the brief destination and retain existing Market Intelligence pages/archive.

## UI-04 — Portfolio Intelligence

**Objective:** Extend `/portfolio` with deterministic snapshot, allocation, concentration, performance, data quality, and position drill-down views.

**Dependencies:** INV-03 owner-scoped snapshot/analytics read models; INV-02 observation freshness; stable security links.

**Surfaces:** overview summary, allocation, largest exposures, concentration, performance/drawdown, position table, account-safe drill-down.

**Backend:** snapshot ID/as-of/hash, positions, exposure buckets, missing/stale/unknown states, provenance, pagination.

**Open-source dependencies:** existing semantic tables and Recharts; evaluate TanStack Table only after measured scale.

**Tests:** fixture arithmetic display, unknown currency/cost basis, stale price, empty portfolio, multi-account privacy, table keyboard behavior, responsive overflow, accessibility.

**Acceptance:** Portfolio remains source-facing and owner-scoped; UI does not infer missing values or expose raw account identifiers unnecessarily.

**Rollback:** feature-gate intelligence panels while keeping current holdings/import/refresh flows.

## UI-05 — Security Research workspace

**Objective:** Present one security workspace with identity, market context, fundamental, technical, quant, macro, event, and evidence lenses.

**Dependencies:** INV-02–07 stable projections; public security projection separated from private portfolio context.

**Surfaces:** security header, Atlas View summary, tabbed research lenses, chart slot, events/filings, risks and limitations.

**Backend:** security ID, as-of/freshness, research sections, bounded evidence, methodology/version, no provider payloads.

**Open-source dependencies:** Recharts first; evaluate Lightweight Charts for OHLCV only through a dedicated spike.

**Tests:** unresolved/ambiguous/inactive identity, stale and insufficient history, adjustment basis, tab keyboard behavior, deep links, privacy separation, chart fallback.

**Acceptance:** No look-ahead or provider-specific data is implied by the UI; mixed signals stay mixed; research is not a recommendation by default.

**Rollback:** remove route activation and preserve links to Market Intelligence/Portfolio.

## UI-06 — Financial visualization adapter

**Objective:** Standardize chart payloads, labels, source/freshness context, and accessible textual fallbacks.

**Dependencies:** UI-03–05 requirements and stable time-series contracts.

**Surfaces:** price/volume, allocation, performance, drawdown, macro series, benchmark comparison.

**Backend:** normalized time-series payloads with basis, timestamps, omissions, and provenance.

**Open-source dependencies:** retain Recharts for current chart families; run a compatibility/license/accessibility spike for Apache-2.0 Lightweight Charts before any adoption; no Fincept/TradingView clone.

**Tests:** visual/data snapshots where useful, no-data and invalid-series states, keyboard/text fallback, reduced motion, 200% zoom, mobile readability, bundle impact.

**Acceptance:** Financial meaning is not color-only; adjusted/unadjusted basis is visible; chart output cannot become a source of truth.

**Rollback:** use existing chart wrappers/tables and disable the adapter path.

## UI-07 — Evidence and provenance

**Objective:** Make the path from claim to source observation or deterministic calculation understandable without overwhelming normal users.

**Dependencies:** INV-01 evidence contract and domain-specific provenance fields.

**Surfaces:** EvidenceCard, EvidenceDrawer, provenance badge, methodology disclosure, source links, revision/as-known-at details.

**Backend:** bounded evidence packet, source IDs, timestamps, hashes, calculation/version references, access scope.

**Open-source dependencies:** none; use existing dialogs/drawers and Lucide.

**Tests:** disclosure levels, focus management, source sanitization, missing provenance, stale/revised/derived labels, owner isolation, screen-reader semantics.

**Acceptance:** Every material UI claim has a traceable evidence path or is explicitly labeled interpretation/assumption.

**Rollback:** collapse to inline source/freshness labels while retaining existing evidence links.

## UI-08 — Recommendation review and user decision

**Objective:** Present INV-09 recommendations as explainable review objects and connect them to the existing append-only decision lifecycle.

**Dependencies:** INV-08 typed findings/challenge, INV-09 recommendation contract, existing Decisions routes and preconditions.

**Surfaces:** recommendation review card, signal conflict panel, risks/invalidation, portfolio impact, evidence drawer, record-decision controls.

**Backend:** recommendation identity/version, confidence semantics, thesis, evidence, dissent, risks, decision ETag/preconditions, no mutation beyond user decision record.

**Open-source dependencies:** none; reuse existing RecommendationExplainedCard/Decision components where compatible.

**Tests:** stale preconditions, decision lifecycle, mixed signals, missing evidence, no execution labels/actions, ownership, keyboard/focus, mobile review flow.

**Acceptance:** User can understand and record a decision; no button places an order or changes brokerage state.

**Rollback:** disable investment recommendation views and retain existing Decisions behavior.

## UI-09 — Opportunity discovery and comparison

**Objective:** Provide a bounded, explainable research queue rather than a hype feed.

**Dependencies:** future screening/ranking/comparison contracts; security and evidence projections.

**Surfaces:** filters, results table, compare tray, candidate detail, watch state, limitations.

**Backend:** explicit universe/as-of, ranking methodology, omissions, pagination, comparison basis, public/private scope.

**Open-source dependencies:** semantic tables first; evaluate TanStack Table only for measured scale.

**Tests:** filter determinism, pagination, comparison compatibility, empty/unavailable universe, unsafe identifiers, privacy, mobile filter sheet.

**Acceptance:** Results are research candidates with methodology and timestamp, never unlabeled recommendations.

**Rollback:** hide discovery route; preserve manually opened security research.

## UI-10 — AI investment workspace

**Objective:** Let Scout answer contextual investment questions from structured Atlas evidence.

**Dependencies:** INV-08 typed committee/context contracts; read-only assistant boundary; UI-07 evidence drawer.

**Surfaces:** global, page-context, and evidence-context prompts; cited response; fact/calculation/assumption separation; follow-up questions.

**Backend:** server-owned context reference, bounded tool calls, typed response, evidence citations, sanitized failures.

**Open-source dependencies:** retain existing orchestrator and Pydantic contracts; no LangGraph/PydanticAI until separately approved.

**Tests:** prompt injection, invented-number detection, citation correctness, ownership isolation, offline behavior, no execution vocabulary/capability.

**Acceptance:** AI explains validated evidence and cannot authoritatively create facts, recommendations, or mutations.

**Rollback:** disable investment context actions while retaining general Scout.

## UI-11 — Risk and scenario views

**Objective:** Make portfolio risk, hypothetical impact, and scenario uncertainty understandable.

**Dependencies:** INV-03 risk projections and later scenario/impact contracts.

**Surfaces:** risk radar, drawdown, concentration, liquidity, scenario comparison, assumptions and limits.

**Backend:** baseline snapshot/hash, hypothetical result, constraints, data quality, no persistence unless explicitly authorized.

**Open-source dependencies:** existing charts; no optimizer UI before backend methodology is stable.

**Tests:** deterministic preview, no mutation, stale/missing inputs, scenario labeling, accessibility, owner isolation.

**Acceptance:** Hypothetical results are clearly hypothetical and cannot be mistaken for execution or a guaranteed outcome.

**Rollback:** remove scenario panels and keep existing Scenario Lab.

## UI-12 — Integration hardening and trust review

**Objective:** Verify the complete investment experience remains coherent, accessible, private, performant, and evidence-backed.

**Dependencies:** UI-02–11 as applicable; INV-10/11/12 outputs.

**Surfaces:** cross-route navigation, archive, decision/outcome timeline, evaluation/methodology view, responsive matrix.

**Backend:** stable contracts, replay/evaluation metadata, retention/deletion behavior, operational freshness.

**Open-source dependencies:** dependency/license/SBOM review for any adopted chart/table library.

**Tests:** full frontend Vitest, TypeScript, lint, production build, Playwright widths 390/768/1024/1440/1728, reduced motion, axe scans, route privacy, no-execution audit, performance budgets.

**Acceptance:** No new regression; all material claims expose evidence/status/as-of; UI is usable on consumer devices; release remains within the human decision boundary.

**Rollback:** feature-gate individual investment surfaces; never delete or rewrite financial history.

## Relationship to backend INV-08–INV-12

Backend investment phases may continue independently from this roadmap. UI implementation should start only when each required Atlas-owned read model and authorization contract is stable. UI-08 depends most directly on INV-08/09, UI-03 on INV-10, UI-08/12 on INV-11, and UI-12 on INV-12. No UI phase authorizes a backend phase or alters canonical investment authority.
