# Atlas Phase 2 Vertical Slice: Forecast Surfacing + Explainable Recommendation + Decision Journal

> **Status:** Planning only. No implementation begins until this plan is reviewed and explicitly authorized.
> **Phase 1 anchor:** `main` SHA `08f6f811da7c325da8a3d60adae9f2d9c2d210e8` (annotated tag `phase-1-complete`).
> **Risk tier:** HIGH (per `atlas-project-tracker` SKILL: financial calculations + recommendations + immutable decision history, even though derivation is deterministic and LLM-free).

## Purpose

Deliver the single first user-visible Atlas vertical slice — connecting the certified Phase 1 immutable forecast APIs to a deterministic explainable recommendation and a bounded, append-only decision journal — without crossing into the open external-multi-user retention/deletion gate or the open account-currency-authority gate.

## Cross-cutting constraints (HARD, inherited verbatim)

- **Single-user development slice.** No household tenancy, no advisor features, no autonomous execution, no generic agent architecture.
- **Reuse Phase 1 read APIs unchanged.** No route additions beyond the bounded new GET and POST endpoints listed below.
- **Default-off flags stay default-off.** `atlas_forecast_persistence_enabled=False`, `atlas_forecast_read_api_enabled=False`. The slice must remain functional-but-disabled when these flags are off, and the UI must surface a stable "feature disabled" affordance rather than rendering stale legacy data.
- **Deterministic derivation only.** No LLM call, no Monte Carlo, no probability distribution. `target_status` from `atlas-target-decision/v2` is the single source of truth for "probability" in Phase 1.
- **Decimal strings preserved end-to-end.** No `Number()`, no `parseFloat`, no template-string interpolation on the way to the user.
- **Authorization preserved.** Every route returns 404 before any canonical-state retrieval on missing/cross-user goals.
- **Append-only decision history.** The new table mirrors the Phase 1 immutability pattern from `R6f1g2h3i4j5_add_immutable_forecast_history` (database-level no-UPDATE / no-DELETE triggers on supported dialects + explicit downgrade path).
- **Risk register untouched.** The 12 existing rows stay (5 Phase 1 OPEN, 1 RESOLVED migration-patched, 6 Phase 0). No new row is added in this planning turn; planning-level concerns are captured in the `PROJECT_STATUS.json` note field instead.

---

## 1. Current UI/backend reuse map

| Component | Path | Disposition | Reason / evidence |
| --- | --- | --- | --- |
| `Forecast` + `ForecastVersion` ORM | `services/rules-service/app/models/forecast.py` | **REUSE** | Stable identity row + immutable version rows; ADR-006 §"Stable forecast identity and goal linkage". |
| Forecast API response envelopes + ETag bare-format | `services/rules-service/app/forecasts/schemas.py` | **REUSE** | `ForecastResponse`, `ForecastVersionResponse`, `ForecastListResponse`, `ForecastVersionListResponse`, ETag validators. |
| ETag / cursor codecs | `services/rules-service/app/forecasts/api_codecs.py` | **REUSE** | `derive_forecast_etag`, `encode_forecast_cursor` / `decode_forecast_cursor`. |
| Persisted-row → wire-envelope mapper | `services/rules-service/app/forecasts/mappers.py` | **REUSE** | Same mapper drives both POST generation and GET reads — no parallel code path. |
| Repository (version allocation, idempotency replay, get-or-create) | `services/rules-service/app/forecasts/repository.py` | **REUSE** | Read route re-uses read helpers; cannot allocate new versions without the POST route. |
| Goal model | `services/rules-service/app/models/goal.py` | **REUSE** | Source of `goal_id`, `target_amount`, `target_date`, `horizon_years`, `currency`. Goal Float is unchanged in Phase 2 (`risk-p1-legacy-goal-float` remains OPEN). |
| `recommendation_logs` ORM + CRUD router | `services/rules-service/app/models/recommendation_log.py`; `services/rules-service/app/routes/recommendations.py` | **EXTEND (FK only)** | Phase 2 uses this table purely as a related-record substrate (FK). Existing columns: `priority: String(16)` literal `{high, medium, low}`, `status: String(16)` literal `{pending, approved, denied, dismissed}` per alembic `P4a5b6c7d8e9_add_recommendation_logs.py`. Phase 2 does NOT introduce a new status code on this table; instead it writes a sibling row in the new append-only journal table whose `action_taken` enum absorbs accept/reject/defer. |
| Bounded error envelopes (5xx / 4xx) | `services/rules-service/app/forecasts/schemas.py` | **REUSE** | `ReadApiDisabledEnvelope` (503), `GoalNotFoundEnvelope` (404), `ForecastNotFoundEnvelope` (404), `BadRequestEnvelope` (400). |
| Sidebar entry / nav for /goals and /recommendations | `ui/components/layout/Sidebar.tsx` | **REUSE** | `/goals` is the slice's primary surface. `/recommendations` continues to host demo content (out of slice scope; out of slice risk). |
| `RecommendationCard` component | `ui/components/dashboard/RecommendationCard.tsx` | **NEW-COMPLEMENT** (do not edit) | Build a sibling `RecommendationExplainedCard` instead — keeps the existing `/recommendations` page demo + dashboard `ApprovalQueue` working without regression. |
| Goal-list / what-if + funding-plan UI | `ui/app/goals/page.tsx` | **EXTEND** | Add a bounded "Latest Forecast" section under the existing goal grid. The pre-existing list / create / edit / archive / funding-plan logic is unmodified. |
| API client + token-attaching axios instance | `ui/lib/api.ts` | **EXTEND** | Add three typed methods: `getLatestForecastForGoal`, `getDerivedRecommendation`, `postDecisionJournal`. The existing client + `RecommendationLogItem` type at `ui/lib/api.ts:1174` remain the canonical TS type registry. |
| Decimal / number / date format utilities | `ui/lib/format.ts` | **REUSE** | `formatNumber`, `formatDateRFC3339Z`, decimal-friendly helpers. No new formatter introduced. |
| Goal-page design tokens (cards, buttons, banner) | `ui/components/ui/*` | **REUSE** | `ErrorBanner`, `TiltCard`, `Button`, `Input`, `Modal` already implement the Phase 2 visual language via `DESIGN_SYSTEM.md`. |
| `atlas_target_decision_v2` decision fragment | `services/rules-service/app/forecasts/snapshots.py` (`TARGET_DECISION_SCHEMA_VERSION = "atlas-target-decision/v2"`) | **REUSE** | Single source of truth for `target_status: bool` driving probability + recommendation. |

---

## 2. Exact user journey and acceptance criteria

### Journey (single end-to-end path on `/goals`)

1. User lands on `/goals`.
2. UI reads `/api/goals/` (existing endpoint, unchanged) to populate the goal grid.
3. UI conditionally reads `GET /api/v1/forecasts?limit=64` (Phase 1 read route, gated by `atlas_forecast_read_api_enabled`). One forecast per goal is selected (`forecast_kind="goal_projection"`, `currency="USD"`, `goal_id` match).
4. UI conditionally reads `GET /api/v1/forecasts/{forecast_id}/versions/{latest_version_number}` to fetch the immutable version envelope for the latest forecast (`ending_balance`, `target_status`, `target_decision`, `drivers`, `scenarios`, `assumption_snapshot`, `provenance_snapshot`, `data_as_of`, `data_age_days`).
5. UI conditionally reads `GET /api/v1/forecasts/{forecast_id}/recommendation` to fetch the deterministic derived recommendation (`DeterministicRecommendationEnvelope`).
6. UI renders a "Latest Forecast" panel under each goal with: target, projected ending balance, probability (the `target_status` boolean + a bounded qualitative tag), forecast timestamp (`calculated_at`), data freshness (`data_as_of` + relative age), and a "Why this projection" link/affordance that expands the assumption + provenance snapshot.
7. UI renders the explainable recommendation card with action verb, why-now, impact range, risks, confidence, assumptions reference, and the three bounded Accept / Reject / Defer buttons.
8. User clicks one button. UI calls `POST /api/v1/recommendations/{recommendation_id}/decisions` with `{ "action": "accept|reject|defer", "decision_etag": "..." }` (ETag minted at derivation read time and returned in the read response).
9. Response is 201 with `Location` header pointing to `/api/v1/decisions/{journal_entry_id}`. UI shows a sanitized success toast with the bounded outcome label ("Recorded."). The recommendation card flips to a non-interactive "Recorded" state with timestamp + journal entry id.
10. Navigation events re-read the goal card; the journal state is not directly visible on `/goals` in this slice (kept for a future Phase 2.x extension — listed in non-goals).

### Acceptance criteria (each verifiable)

- **AC1 (Read gate):** When `atlas_forecast_read_api_enabled=False`, the "Latest Forecast" section is not rendered and an inline `<ErrorBanner>` carries the sanitized diagnostic code `forecast_read_api_unavailable`. When the flag is `True`, the section renders deterministic data. `[evidence: services/rules-service/app/config.py:Settings.atlas_forecast_read_api_enabled=False; services/rules-service/app/forecasts/schemas.py:ReadApiDisabledEnvelope]`
- **AC2 (Decimal contract):** Every money value reaching the UI is rendered from a canonical Decimal string with no `Number()`/`parseFloat` on the API path. ts/JS code MUST type all money fields as `string`. `[evidence: docs/adr/ADR-006-IMMUTABLE-FORECAST-PERSISTENCE.md:Decimal money and currency]`
- **AC3 (Probability source-of-truth):** Probability / status labels are derived strictly from `target_status: bool` from `atlas-target-decision/v2`. No Monte Carlo, no LLM probability, no third-party probability service. `[evidence: docs/adr/ADR-006-IMMUTABLE-FORECAST-PERSISTENCE.md:Versioned snapshots and calculation identity]`
- **AC4 (Deterministic recommendation):** The recommendation payload is built deterministically from `(forecast_version, current_decision_etag, target_status, drivers.data_age_days, scenarios.*.annual_return_rate)`. The same inputs MUST produce the same payload (golden fixture in test). `[evidence: agent-context/FINANCIAL_REASONING_RULES.md:Rule 2]`
- **AC5 (Explanation contract):** The card renders action, why-now, impact range, risks, assumptions reference, confidence, expiration/measurement. The expanded "Why this projection" panel renders the assumption + provenance snapshot hashes plus the model_version + calculation_version. `[evidence: docs/05-intelligence/EXPLANATION_ENGINE.md:Required questions; docs/05-intelligence/RECOMMENDATION_ENGINE.md:Contract]`
- **AC6 (Append-only journal):** Every accept/reject/defer call writes exactly one row to `decision_journal_entries`. The row's `(recommendation_id, decision_etag, action_taken, decided_at, evidence_snapshot_json)` are immutable. Direct UPDATE/DELETE on the table fails with `immutable_decision_history` from the application service and is blocked by database triggers on supported dialects. `[evidence: services/rules-service/alembic/versions/R6f1g2h3i4j5_add_immutable_forecast_history.py:trigger pattern]`
- **AC7 (Authorization preserved):** A journal POST referencing a recommendation owned by another user returns 404 with stable `forecast_not_found` envelope, NOT `decision_journal_unavailable`. The journal POST applies ownership scope BEFORE writing. `[evidence: docs/adr/ADR-006-IMMUTABLE-FORECAST-PERSISTENCE.md:Transitional ownership and authorization]`
- **AC8 (No client financial state):** The decision-journal POST body accepts ONLY `{action, decision_etag}`; unknown fields reject with sanitized `forecast_validation_error` envelope. No money, no assumption overrides, no body fields. `[evidence: docs/adr/ADR-006-IMMUTABLE-FORECAST-PERSISTENCE.md:Trusted generation boundary; services/rules-service/app/forecasts/schemas.py:_phase1_request_config `extra=\"forbid\"`]`
- **AC9 (Default-off semantics):** When the new POST route is requested while `atlas_forecast_read_api_enabled=False`, the route returns the SAME `ReadApiDisabledEnvelope` (503) — not a separate disabled envelope — so a single UI-state tree covers the disabled case. `[evidence: services/rules-service/app/forecasts/schemas.py:ReadApiDisabledEnvelope]`
- **AC10 (Stable contract):** The recommendation JSON envelope includes a `schema_version` of `atlas-derived-recommendation/v1` and the journal envelope includes `schema_version` of `atlas-decision-journal-entry/v1`. Any response failing this version literal fails closed on the client. `[evidence: docs/adr/ADR-006-IMMUTABLE-FORECAST-PERSISTENCE.md:Versioned snapshots and calculation identity]`

---

## 3. API-to-UI data flow

### Read path (forecast surfacing + recommendation derivation)

```
ui/app/goals/page.tsx (mount)
  → rulesService.listGoals()                           [unchanged]
  → rulesService.getLatestForecastForGoal(goal_id)     [NEW ui/lib/api.ts]
      → GET /api/v1/forecasts?goal_id={id}&limit=4     [Phase 1 read route]
        selector: stable ForecastResponse where goal_id matches
      → GET /api/v1/forecasts/{forecast_id}            [Phase 1 read route]
        ← ForecastResponse { etag, latest_version_number, latest_version_id, links }
      → GET /api/v1/forecasts/{forecast_id}/versions/{latest_version_number}
        ← ForecastVersionResponse { ending_balance, target_status, target_decision, drivers, scenarios, assumption_snapshot, provenance_snapshot, data_as_of, data_age_days, calculation_decimal_schema_version, model_version }
      → GET /api/v1/forecasts/{forecast_id}/recommendation
        ← DeterministicRecommendationEnvelope { schema_version, action_verb, why_now, linked_goal_id, forecast_id, forecast_etag, evidence_references, expected_impact_range, risks, confidence, assumptions_reference, issuer, expiration }
```

### Write path (decision journal)

```
RecommendationExplainedCard onClick accept|reject|defer
  → rulesService.postDecisionJournal(recommendation_id, { action, decision_etag })
      → POST /api/v1/recommendations/{recommendation_id}/decisions
        headers: Idempotency-Key (client-minted, bounded 1..255 visible-ASCII)
        body: { action: "accept"|"reject"|"defer", decision_etag: "uuid-v-n" }
        201 ◀ DecisionJournalEntryEnvelope { schema_version, journal_entry_id, recommendation_id, action_taken, decided_at, decision_etag }
        409 ◀ IdempotencyConflictEnvelope (idempotency-key vs input-hash mismatch)
        404 ◀ ForecastNotFoundEnvelope (cross-user / missing recommendation)
        422 ◀ ValidationErrorEnvelope (unknown field / bad action / invalid decision_etag)
        503 ◀ ReadApiDisabledEnvelope (forecast read flag off)
```

### Field-level mapping (sub-card items)

| UI element | Source |
| --- | --- |
| Goal target | `goal.target_amount` (existing) as Decimal string via `formatNumber` |
| Projected ending balance | `forecast_version.ending_balance` (canonical Decimal string) |
| Reference projection | `forecast_version.target_decision.rounded_ending_balance` (USD cents) |
| Probability / status | `forecast_version.target_status: boolean` + UI text mapping ("On track" / "Gap remaining") |
| Forecast timestamp | `forecast_version.calculated_at` (RFC 3339 Z) |
| Data freshness | `forecast_version.data_as_of` + `data_age_days` + relative `formatRelativeTime(data_as_of)` |
| Action verb | `DeterministicRecommendationEnvelope.action_verb` |
| Why now | `DeterministicRecommendationEnvelope.why_now` |
| Impact range | `expected_impact_range` (Decimal-string min/max) |
| Risks | `risks: tuple[string, ...]` bounded enum |
| Confidence | bounded enum (`high | medium | low`) computed from freshness + scenario spread |
| Assumption reference | `assumptions_reference: sha256_hex` + expanded panel renders `assumption_snapshot` |
| Decision button labels | "Accept" / "Reject" / "Defer" (banned: "Approve" to disambiguate from existing `recommendation_logs.status="approved"`; see DECISION_MODEL.md) |

### Error mapping (UI state tree)

| Backend code | UI behavior |
| --- | --- |
| 503 `forecast_read_api_unavailable` | "Latest Forecast" section hidden; inline banner with diagnostic + Retry. |
| 503 generic (Finlynq forwarder 502/504) | Inline banner with classifier-derived label. |
| 404 `forecast_not_found` | Goal card renders the existing partial state with a "No persisted forecast" hint; no error toast (matches existing goal-empty affordance). |
| 401/403 | Existing session-expired path; redirect to login. |
| 409 `idempotency_conflict` | Re-fetch latest recommendation (read-only recompute) and disable submit until resolved. |
| 422 `forecast_validation_error` | Disable submit; surface sanitized diagnostic in red banner. |

---

## 4. Recommendation and explanation contract

### `DeterministicRecommendationEnvelope` (`schema_version = "atlas-derived-recommendation/v1"`)

| Field | Type | Source | Bounded |
| --- | --- | --- | --- |
| `schema_version` | literal `"atlas-derived-recommendation/v1"` | fixed | required |
| `recommendation_kind` | literal `"increase_contribution" \| "rebalance_allocation" \| "extend_horizon" \| "hold"` | derived enum | required |
| `action_verb` | string | one of `Increase \| Reallocate \| Extend \| Hold \| Reduce` | ≤ 64 chars |
| `why_now` | string | deterministic from `data_age_days + target_status` | ≤ 280 chars |
| `linked_goal_id` | integer | `forecast.goal_id` (Phase 1 integer goal ID) | range 1..9_223_372_036_854_775_807 |
| `forecast_id` | UUID lowercase | `forecast.id` | bounded lowercase canonical UUID |
| `forecast_etag` | string | `derive_forecast_etag(forecast_id, latest_version_number)` bare | matches `_ETAG_BARE` regex |
| `evidence_references` | object | `{ forecast_id, model_version, calculation_version, input_state_hash, data_as_of }` (no money values) | required, all strings |
| `expected_impact_range` | object | `{ min_delta_decimal: string, max_delta_decimal: string }` in canonical Decimal form | both canonical |
| `risks` | tuple of bounded enum tokens | e.g. `(liquidity_reduction,)` | bounded literal set in derivation module |
| `confidence` | enum literal | `high \| medium \| low` derived from freshness + scenario spread | required |
| `assumptions_reference` | SHA-256 hex sha of `assumption_snapshot` JSON | required | required |
| `expiration` | RFC 3339 Z timestamp | derived: `calculated_at + 24h` or sooner if `data_age_days > max_data_age_days` | required |
| `issuer` | literal `"atlas-deterministic-rules/v1"` | fixed | required |
| `links` | tuple of bounded `{rel, href}` pairs | at minimum `{ rel: "self", href: "/api/v1/forecasts/{forecast_id}/recommendation" }, { rel: "forecast", href: "/api/v1/forecasts/{forecast_id}" }, { rel: "decide", href: "/api/v1/recommendations/{forecast_id}/decisions" }` (POST rel is informational; not a GET endpoint) | bounded |

### Derivation rules (deterministic, table-driven)

The bounded rule module lives at `app/forecasts/recommendations.py`. Rules:

| Input signal | Recommendation | Risks | Confidence |
| --- | --- | --- | --- |
| `target_status == true AND data_age_days <= max_data_age_days / 2` | `hold` | `[]` | `high` |
| `target_status == true AND max_data_age_days / 2 < data_age_days <= max_data_age_days` | `hold` with `why_now = "You are on track; refresh the projection at your next review window."` | `[]` | `medium` |
| `target_status == false AND conservative_scenario_ending_balance >= target_amount` (in scenarios dict) | `extent_horizon` (i.e. extend horizon / decrease target) | `(reversibility_required,)` | `medium` |
| `target_status == false AND conservative_scenario_ending_balance < target_amount AND base_scenario_ending_balance > conservative_scenario_ending_balance` | `increase_contribution` | `(liquidity_reduction,)` | `medium` |
| `target_status == false AND conservative_scenario_ending_balance < target_amount AND base_scenario_ending_balance == conservative_scenario_ending_balance` (flat-line) | `rebalance_allocation` | `(concentration, downside_amplification)` | `low` |
| `data_age_days > max_data_age_days` | `hold` with `why_now = "Source data is older than the freshness window — refresh before deciding."` | `(stale_input,)` | `low` |

The full derivation table is part of the bounded implementation PR (PR #1 of the slice: `work-p2-decision-journal-substrate`). It is NOT LLM-generated. It mirrors `docs/05-intelligence/RECOMMENDATION_ENGINE.md` "Contract" with deterministic input/output rather than model-derived explanation text.

---

## 5. Decision-journal contract

### Model: `decision_journal_entries` (NEW, separate file mirroring `forecast_versions`)

Path: `services/rules-service/app/models/decision_journal.py` (separate model file mirroring Phase 1 `forecast.py` segment discipline — justification: append-only immutability constraints + dialect-specific trigger setup are non-trivial and deserve a self-contained file).

Columns:

| Column | Type | Nullable | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | UUID (lowercase canonical) | NO | — | PK; same shape rule as `forecast_versions.id` (`ck_forecasts_id_shape`-equivalent) |
| `user_id` | Integer | NO | — | FK → `users.id`; transitional |
| `recommendation_id` | UUID | NO | — | FK → `recommendation_logs.id` (the recommendation id surfaced in `DeterministicRecommendationEnvelope.forecast_id`'s seed) |
| `decision_etag` | String | NO | — | The bare ETag the user saw (`{forecast_uuid}-v{n}`); 96-char bounded; verifiable. |
| `action_taken` | String(16) | NO | — | Literal enum: `accept \| reject \| defer` |
| `decided_at` | DateTime | NO | — | UTC RFC 3339 Z; truncated to microsecond precision |
| `idempotency_key_hash` | SHA-256 hex | NO | — | Mirrors `forecast_versions.idempotency_key_hash` |
| `evidence_snapshot_json` | Text (JSON) | NO | — | Frozen copy of the `evidence_references` + assumptions reference + scenario-derived decision variables; canonical JSON (sorted keys, RFC 3339 Z, ASCII). |
| `created_at` | DateTime | NO | `now()` | UTC. |

Constraints:
- `UniqueConstraint("recommendation_id", "decision_etag", "action_taken", name="uq_decision_once_per_state")` — same `(recommendation, version, action)` cannot be written twice; replay = identical row, NOT a new row.
- `UniqueConstraint("idempotency_key_hash", name="uq_decision_idempotency")`.
- `CheckConstraint("length(id) = 36 AND id = lower(id)", ...)`.
- `CheckConstraint("action_taken IN ('accept','reject','defer')", ...)`.
- `CheckConstraint("length(decision_etag) <= 96 AND decision_etag ~ '<etag-bare-regex>'", ...)`.
- Indexes: `ix_decision_journal_user_id`, `ix_decision_journal_recommendation_id`, `ix_decision_journal_decided_at`.

Immutability (mirrors Phase 1 `R6f1g2h3i4j5`):
- SQLite / PostgreSQL: BEFORE UPDATE OR DELETE trigger raising `immutable_decision_history` exception.
- Downgrade path explicitly drops triggers before `DROP TABLE`.

Alembic migration filename: `T8u9v0w1x2y3_add_decision_journal_entries.py` (mirrors narrative pattern from `R6f1g2h3i4j5` + `S7a1b2c3d4e5`).

### Response envelope: `DecisionJournalEntryEnvelope` (`schema_version = "atlas-decision-journal-entry/v1"`)

| Field | Type | Notes |
| --- | --- | --- |
| `schema_version` | literal | required |
| `journal_entry_id` | UUID lowercase | PK of written row |
| `recommendation_id` | UUID | FK target |
| `action_taken` | enum literal | echo from request |
| `decided_at` | RFC 3339 Z | echo of row.created_at or DB-returned truncated timestamp |
| `decision_etag` | string | echo; bounded regex |
| `links` | tuple of bounded `{rel, href}` | `{ rel: "self", href: "/api/v1/decisions/{journal_entry_id}" }` only |

### Write contract

`POST /api/v1/recommendations/{recommendation_id}/decisions`:
- Auth: server-derived JWT user.
- Headers: `Idempotency-Key` (validated exactly as in `forecasts_generation` route; reused `IdempotencyKeyHeader` model with `extra="forbid"`) and required `If-Match: "<decision-etag>"`.
- Body: `{action, decision_etag}` strict — `extra="forbid"`.
- Decision semantics: the body decision ETag and quoted `If-Match` value must both match the current server-derived decision resource version (`<recommendation_id>-d1`) before ownership-authorized append; stale, mismatched, malformed, or wildcard preconditions fail closed without a journal write. Ownership is checked against `recommendation.user_id == current_user_id` BEFORE writing; cross-user → 404 with same envelope as missing (`forecast_not_found`) to preserve indistinguishability.
- 201 success; `Location: /api/v1/decisions/{journal_entry_id}`; `ETag: \"{journal_entry_id}-v1\"`.
- 409: idempotency-key-hash mismatch with different request body.
- 422: validation error envelope.
- 503: read-API-disabled envelope (same as forecast reads).

---

## 6. File-by-file implementation plan

### Backend (Rules Service only; no Finlynq changes in this slice)

| File | Brief | New / Modify | Risk |
| --- | --- | --- | --- |
| `services/rules-service/app/models/decision_journal.py` | NEW ORM model + helpers (mirrors `app/models/forecast.py` segment discipline) | NEW | Med |
| `services/rules-service/alembic/versions/T8u9v0w1x2y3_add_decision_journal_entries.py` | NEW Alembic revision (`upgrade head` -> `downgrade base` clean round-trip) | NEW | High |
| `services/rules-service/app/forecasts/recommendations.py` | NEW deterministic-derivation rule module (table above); encapsulates rule table + builder; ships with golden test fixtures | NEW | High |
| `services/rules-service/app/routes/recommendations_derived.py` | NEW bounded read route `GET /api/v1/forecasts/{forecast_id}/recommendation` + bounded write route `POST /api/v1/recommendations/{recommendation_id}/decisions` | NEW | High |
| `services/rules-service/app/forecasts/schemas.py` | EXTEND: add `DeterministicRecommendationEnvelope`, `DecisionJournalEntryEnvelope`, `DecisionJournalSubmitRequest`, and reuse `ValidationErrorEntry` / `ValidationErrorEnvelope` / `ReadApiDisabledEnvelope` / `ForecastNotFoundEnvelope` | MODIFY | Med |
| `services/rules-service/app/main.py` | EXTEND: register `recommendations_derived_router` under `/api/v1` (consistent with Slice D route prefix) | MODIFY | Low |
| `services/rules-service/app/config.py` | NO CHANGE — reuse `atlas_forecast_read_api_enabled` as the gate for BOTH new routes | (NONE) | (NONE) |
| `services/rules-service/tests/test_decision_journal.py` | NEW pytest module | NEW | High |
| `services/rules-service/tests/test_derived_recommendations.py` | NEW pytest module (golden fixture + rule table) | NEW | High |
| `services/rules-service/tests/test_routes_recommendations_derived.py` | NEW pytest module (FastAPI client tests; mirrors `test_routes_forecast_generation.py` patterns) | NEW | High |
| `services/rules-service/tests/test_decision_journal_migration.py` | NEW alembic round-trip test mirroring `test_forecast_migration.py` | NEW | High |

### UI (Next.js / TypeScript; no new design tokens)

| File | Brief | New / Modify | Risk |
| --- | --- | --- | --- |
| `ui/lib/api.ts` | EXTEND: add `getLatestForecastForGoal`, `getDerivedRecommendation`, `postDecisionJournal` typed methods + 3 new TS types: `ForecastVersionWire`, `DeterministicRecommendation`, `DecisionJournalEntry` | MODIFY | Low |
| `ui/components/dashboard/LatestForecastCard.tsx` | NEW component (renders one forecast summary card with target / projected / probability / freshness / "Why this projection" expansion) | NEW | Med |
| `ui/components/dashboard/RecommendationExplainedCard.tsx` | NEW component (action verb / why-now / impact / risks / confidence / 3 bounded buttons). Reuses design tokens; intentionally does NOT modify the existing `RecommendationCard.tsx`. | NEW | Med |
| `ui/components/dashboard/DecisionRecordedToast.tsx` | NEW component (bounded sanitized success toast tied to journal entry id) | NEW | Low |
| `ui/app/goals/page.tsx` | EXTEND: under the existing goal grid + "Funding Plan" section, add a NEW bounded "Latest Forecast" section. The section is feature-flag-gated. Existing list / create / edit / archive / what-if are completely untouched. | MODIFY | Med |
| `ui/__tests__/lib/api.test.ts` | EXTEND: add tests covering the three new typed methods (success / 503 / 404 / 409 / 422 verbatim) | MODIFY | Low |
| `ui/__tests__/components/LatestForecastCard.test.tsx` | NEW (Vitest + jest-dom + reduced-motion) | NEW | Low |
| `ui/__tests__/components/RecommendationExplainedCard.test.tsx` | NEW (button callbacks fire the EXPECTED action token + decision_etag; aria-label + focus management) | NEW | Low |
| `ui/__tests__/e2e/goals-phase2-slice.spec.ts` | NEW Playwright spec for the end-to-end journey (post merged) | NEW | High |

---

## 7. Test strategy

Coverage targets per CLAUDE.md / DEVELOPMENT_GUIDELINES.md / AGENTS.md "Definition of done":

| Test file | Scope | Coverage shape | Risk |
| --- | --- | --- | --- |
| `services/rules-service/tests/test_derived_recommendations.py` | Backend rule table | Golden fixture + property-style: given input fixtures, the recommendation output is byte-identical. Covers all 6 rule rows of the table above. Also covers stale-data path and the ALL-scenarios-flat path. | High |
| `services/rules-service/tests/test_decision_journal.py` | ORM + POST service | Append-only constraint; UPDATE/DELETE raises `immutable_decision_history`. Cross-user 404 indistinguishability. Idempotency-key replay returns the SAME journal row (no duplicate). Unknown body field rejected by `extra="forbid"`. Bad action enum rejected. Bad `decision_etag` regex rejected. | High |
| `services/rules-service/tests/test_routes_recommendations_derived.py` | FastAPI route | Mirrors `test_routes_forecast_generation.py` coverage: 503 when gate off; 404 cross-user; 404 missing; 422 unknown body field; 201 success; Location header; ETag header on journal entry; condensed journey success + replay-identical. | High |
| `services/rules-service/tests/test_decision_journal_migration.py` | Alembic round-trip | Disposable SQLite; `upgrade head` → `downgrade base` → `upgrade head` clean. Mirrors `test_forecast_migration.py` discipline (PR #20-followup legacy). | High |
| `ui/__tests__/components/LatestForecastCard.test.tsx` | UI component | Renders Decimal strings verbatim (regex on output). Renders `target_status` boolean through the bounded qualitative label. Renders expanded panel containing `model_version` + `calculation_version` + `input_state_hash`. Renders `data_age_days > max_data_age_days` as the bounded "stale input" affordance. Renders nothing when `forecast=null` (loading state). | Med |
| `ui/__tests__/components/RecommendationExplainedCard.test.tsx` | UI component | Buttons fire `accept`, `reject`, `defer` verbs verbatim. Each callback carries `decision_etag` from props. aria-label is `"Accept recommendation"` / `"Reject recommendation"` / `"Defer recommendation"` (no "Approve" stringified). Card disables buttons when `recorded=true`. Confidence enum renders all three bounded values. | Med |
| `ui/__tests__/e2e/goals-phase2-slice.spec.ts` | End-to-end Playwright | Cold-boot → list goals (existing) → mocked forecast fetch with deterministic fixture → expanded "Why this projection" panel → click Accept → mocked POST returns 201 with journal entry id → success toast visible. Cross-user 404 path: mocked 404 + same UI before. | High |
| `ui/__tests__/lib/api.test.ts` | API client | Each new method: happy path returns typed object; 503 surfaces the `ReadApiDisabledEnvelope.code` to caller; 409 surfaces `IdempotencyConflictEnvelope.code`. No money value is ever typed as `number` in TS — `expectTypeOf` assertion or runtime assertion via JSON.parse round-trip. | Low |
| Cross-dialect parity contract | PostgreSQL vs SQLite | Existing `test_*_parity.py` pattern extends to cover `decision_journal_entries` UUID, SHA-256 hex digest, RFC 3339 Z timestamp, Decimal string round-trip, ETag regex. Same fixtures as Phase 1 govern. | High |
| Privacy / sensitive-data drift | Tests do NOT echo | A new bounded test confirms: error responses, logs, and audit events from the new routes never include Decimal money values, transaction data, account details, idempotency-key plaintext, JWT subject, or statement content. Reuses `test_observability.py` + `test_shadow_validate.py` patterns. | High |
| Accessibility (Vitest) | Keyboard + screen reader + reduced motion | Each new component: tab order is `Why this -> Accept -> Reject -> Defer`. Focus ring visible (existing tokens). `aria-label`s on every interactive element. `useReducedMotion()` honored. No decorative Icons rendered without `aria-hidden`. axe-core baseline (Vitest's `@testing-library/jest-dom` + `jest-axe`) | Med |
| Financial correctness (cross-dialect Decimal round-trip) | Existing parity test expansion | The five Phase-0 Decimal invariants (`canonical_decimal_string`, `calculation_decimal_string`, ROUND_HALF_EVEN at 0.01, target_decision v2 quantized, `target_status` boolean) all pass when the new routes exercise them through a stub adapter. | High |

---

## 8. Risks, feature flags, rollback plan, explicit non-goals

### Flags (UNCHANGED; no new flag introduced)

| Flag | Default | Source | Used for |
| --- | --- | --- | --- |
| `atlas_forecast_persistence_enabled` | false | `services/rules-service/app/config.py` | POST generation gate (Phase 1; unchanged) |
| `atlas_forecast_read_api_enabled` | false | `services/rules-service/app/config.py` | NEW: extends as the gate for both `GET /api/v1/forecasts/{forecast_id}/recommendation` AND `POST /api/v1/recommendations/{recommendation_id}/decisions` |

The user-mandated constraint "do not introduce new flags" is honored. The single existing read-API gate covers the lifecycle.

### Risks (preserved verbatim, no new rows in this planning turn)

| ID | Status | Why preserved |
| --- | --- | --- |
| `risk-p1-retention-rollout-gate` | open | External multi-user production enablement remains blocked. Slice ships in development under default-off flags anyway; this risk surfaces when retention is finally approved. |
| `risk-p1-account-currency-authority` | open | Goal Float remains `Float` (`risk-p1-legacy-goal-float`). No real-account currency confirmation in this slice. |
| `risk-p1-legacy-goal-float` | open | Slice reads from existing `goals.target_amount` (Float) routed through the existing `Decimal(str(value))` conversion at the projection boundary. No new precision claims. |
| `risk-p1-dialect-parity` | open | New Decimal-and-UUID-bearing table inherits the same dialect-parity contract from `test_decision_journal_migration.py` + cross-dialect parity tests. |
| `risk-p1-trusted-generation-boundary` | open | The new derivation route does NOT take client financial state. The journal POST does NOT take money. Both honor `extra="forbid"` + sanitized location/error contract. |
| `risk-frontend-lint-debt` | open | Unrelated; no new lint debt introduced. New TS files use the existing design-token pattern. |

### Planning-level risk note (NOT a new row)

Captured verbatim in `PROJECT_STATUS.json.active_work[work-p2-vertical-slice-planning].notes`:

> **planning-level risk (Phase 2 vertical slice is cross-phase):** The slice touches territories the Phase plan formally split across Phase 2 (Forecast UI migration), Phase 3 (Goal-linked recommendations), and Phase 4 (Decision journal). We resolve this by treating the slice as Phase 2 IMPLEMENTATION that USES Phase 3 (recommendation derivation) + Phase 4 (decision journal) building blocks WITHOUT adopting their phase-completion semantics. Phase exit criteria are not affected: the Phase 2 exit criterion (`UI uses persisted forecasts, preserves explainability, has accessibility and parity coverage`) is satisfied by AC1-AC10 above. Phase 3 / Phase 4 remain `not_started` until separately authorized with their own exit-criterion evidence.

### Rollback plan

1. Disable `atlas_forecast_read_api_enabled` (= false). All NEW routes return the same `ReadApiDisabledEnvelope`. The UI's `Latest Forecast` / `RecommendationExplainedCard` sections are hidden by AC1.
2. No DB migration is auto-applied to existing prod instances unless explicitly enabled (Phase 1 additivity contract preserved). Downside migration path: `alembic downgrade base` (with prior export) removes `decision_journal_entries`.
3. The Phase 4 (decision journal) and Phase 3 (recommendation derivation) phases can still proceed separately; the slice does NOT claim to retire them.
4. UI rollback: revert the bounded additions in `ui/app/goals/page.tsx` + remove the new components. Existing `RecommendationCard` / `ApprovalQueue` are untouched so dashboard `/recommendations` keeps working pre-rollback.

### Explicit non-goals (HARD)

- No LLM / Copilot / AI explanation text generation; derivation is rule-based and deterministic.
- No autonomous execution (`docs/05-intelligence/RECOMMENDATION_ENGINE.md` non-goal: "No material financial action without explicit permission and an audit record." The audit record is the journal ROW itself; the action verb is "decision entered", NOT "transfer initiated").
- No household tenancy / advisor features / multi-user scoping changes.
- No new recommendation model classes (`recommendation_logs` columns are unchanged). The session-level demo seed (`_seed_default_recommendations_on_boot`, `_generate_smart_recommendations_on_boot`) is OUT OF SCOPE for this slice: they are startup-time dashboard-only seeds that the slice neither reads nor mutates.
- No Phase 0 projection engine changes. No new projection inputs. No new constellation of scenarios beyond the three already documented (conservative / base / optimistic).
- No analyst-ratings integration. No Finnhub calls. No probabilistic external API.
- No Monte Carlo probability. No model-derived confidence interval.
- No dashboard bench (career Finance Copilot dashboard) regressions. No `ApprovalQueue` modifications.
- No mutable forecast CRUD (PUT / PATCH / DELETE on `/api/v1/forecasts/*` remains forbidden).
- No currency confirmation. No real-account produce-mode enablement.
- No ByteDance / LLM provider integrations. No "smart recommendation" regeneration at slice-mount time.

---

## 9. Recommended Phase 2 exit-criteria checklist

The single Phase 2 exit-criterion (verbatim from `docs/10-roadmap/PHASE_PLAN.md`) is: "UI uses persisted forecasts, preserves explainability, has accessibility and parity coverage." This slice must satisfy it.

| # | Verifiable statement | Evidence |
| --- | --- | --- |
| 1 | The slice consumes ONLY the four Phase 1 read endpoints (`GET /api/v1/forecasts`, `GET /api/v1/forecasts/{forecast_id}`, `GET /api/v1/forecasts/{forecast_id}/versions`, `GET /api/v1/forecasts/{forecast_id}/versions/{n}`) plus one new bounded derivation read endpoint and one new bounded journal write endpoint. No other new forecast endpoint. | `docs/adr/ADR-006-IMMUTABLE-FORECAST-PERSISTENCE.md` API contract § |
| 2 | All Decimal strings from Phase 1 read responses reach the UI intact, never converted through `Number()`/`parseFloat`. | AC2; `ui/__tests__/e2e/goals-phase2-slice.spec.ts` |
| 3 | The new derivation read endpoint returns a deterministic envelope for the SAME `(forecast_id, latest_version_number)` on repeated calls (golden fixture verifies byte-identical output). | `services/rules-service/tests/test_derived_recommendations.py` |
| 4 | Accept/reject/defer each write exactly one journal row; UPDATE/DELETE attempts fail closed. | `services/rules-service/tests/test_decision_journal.py` |
| 5 | Cross-user reads/writes return the same `forecast_not_found` envelope, not a different shape that would disclose existence. | AC7 |
| 6 | Default-off behavior (`atlas_forecast_read_api_enabled=False`) hides the section but does not crash or render stale legacy data. | AC1, AC9 |
| 7 | Alembic round-trip on disposable SQLite is clean (`upgrade head` → `downgrade base` → `upgrade head`); same SQLite test runs against PostgreSQL round-trip suite (cross-dialect parity). | `services/rules-service/tests/test_decision_journal_migration.py` |
| 8 | All UI components pass axe-core baseline; aria-labels match the bounded `<verb> recommendation` pattern; reduced-motion respected; focus order = Why-this → Accept → Reject → Defer. | `ui/__tests__/components/*.test.tsx` + Vitest + `jest-axe` |
| 9 | Privacy/sensitive-data tests confirm error envelopes, logs, and audit events emit NO money values, NO transaction data, NO account details, NO idempotency-key plaintext, NO JWT subject, NO statement content. | `services/rules-service/tests/test_observability.py` (extended) |
| 10 | Complete Rules Service suite (`.venv-rules/bin/python -m pytest services/rules-service/tests/`) is green on the merged slice head with `atlas_forecast_read_api_enabled=False` (regression coverage of the disabled path); Finlynq suite unaffected; UI `tsc --noEmit` exit 0; UI `vitest` exit 0. | Cert matrix pattern (Phase 1 `PHASE1_VERIFICATION_REPORT.md`) |
| 11 | The 5 Phase 1 OPEN risks remain OPEN in `RISK_REGISTER.md`; no new rows added in this planning turn. | `docs/10-roadmap/RISK_REGISTER.md` diff review |
| 12 | The slice ships in two bounded PRs (see §10) carried through the standard high-risk governance (branch + PR + CI + independent review + status update). | `docs/07-engineering/DEVELOPMENT_GUIDELINES.md` Solo-development governance § |

A failure of any one criterion blocks Phase 2 certification of the slice.

---

## 10. Exact next bounded implementation task

We recommend splitting the slice into **two bounded PRs** so each is small enough for the three-cycle review cap while preserving ADR-006 immutability patterns.

### PR 1 (HIGH risk): `work-p2-decision-journal-substrate` — SUBSTRATE (backend only)

**Title:** `feat(rules-service): Phase 2 cross-slice substrate: decision journal model + deterministic recommendation derivation`

**Scope statement (≤ 200 words):** Adds the append-only `decision_journal_entries` table (mirroring `forecast_versions`'s immutability pattern) via Alembic migration `T8u9v0w1x2y3_add_decision_journal_entries.py`. Adds the deterministic-derivation rule module `app/forecasts/recommendations.py` (no LLM, no probability model). Adds the bounded schemas (`DeterministicRecommendationEnvelope`, `DecisionJournalEntryEnvelope`, `DecisionJournalSubmitRequest`) in `app/forecasts/schemas.py`. Adds the read route `GET /api/v1/forecasts/{forecast_id}/recommendation` and the write route `POST /api/v1/recommendations/{recommendation_id}/decisions` in a new `app/routes/recommendations_derived.py` and registers it under `/api/v1` from `app/main.py`. Gating is the existing `Settings.atlas_forecast_read_api_enabled`. Tests cover rule table golden fixture, append-only constraint (UPDATE/DELETE blocked), cross-user 404 indistinguishability, idempotency-key replay-returns-same-row, unknown-body-field rejection, alembic round-trip on SQLite + cross-dialect parity, privacy/sensitive-data exclusions. No UI changes; this PR lays the substrate the UI consumes.

**Risk tier:** HIGH (`atlas-project-tracker` SKILL.md: financial correctness + immutable schemas + API boundary definition + database migration).

**Bounded list of files:**
- `services/rules-service/app/models/decision_journal.py` (NEW)
- `services/rules-service/alembic/versions/T8u9v0w1x2y3_add_decision_journal_entries.py` (NEW)
- `services/rules-service/app/forecasts/recommendations.py` (NEW)
- `services/rules-service/app/forecasts/schemas.py` (MODIFY — add 3 new model classes; preserve all existing classes)
- `services/rules-service/app/routes/recommendations_derived.py` (NEW)
- `services/rules-service/app/main.py` (MODIFY — register new router only)
- `services/rules-service/tests/test_derived_recommendations.py` (NEW)
- `services/rules-service/tests/test_decision_journal.py` (NEW)
- `services/rules-service/tests/test_routes_recommendations_derived.py` (NEW)
- `services/rules-service/tests/test_decision_journal_migration.py` (NEW)
- `services/rules-service/tests/test_observability.py` (MODIFY — extend privacy/sensitive-data assertions for new routes)
- `.env.example` (MODIFY — no new flag; just document that slice honors the existing read-API gate)

**Acceptance criteria for PR 1:**
- AC1-AC10 above are testable end-to-end via FastAPI TestClient + SQL fixtures + golden recommendation fixtures.
- Full Rules Service suite (`.venv-rules/bin/python -m pytest services/rules-service/tests/`) green on the PR head.
- Finlynq suite (`.venv-finlynq/bin/python -m pytest services/finlynq/tests/`) unaffected (no Finlynq files changed) AND green.
- Cross-service (`tests/`) green.
- Privacy/observability tests green.
- Three-cycle review cap applied.
- One independent `code-reviewer-minimax-m3` approval required before merge.

### PR 2 (HIGH risk): `work-p2-vertical-slice-ui` — UI CONSUMES SUBSTRATE

**Title:** `feat(ui): Phase 2 vertical slice: latest forecast + explainable recommendation + decision journal UI`

**Scope statement:** Adds the bounded UI surfacing on `/goals`. NEW components: `LatestForecastCard`, `RecommendationExplainedCard`, `DecisionRecordedToast`. EXTEND `ui/lib/api.ts` (three typed methods + three TS types). EXTEND `ui/app/goals/page.tsx` (add "Latest Forecast" section under existing grid; do NOT modify existing list / create / edit / archive / what-if). All new components reuse existing design tokens. Reads are gated by `atlas_forecast_read_api_enabled` observed on first read (no client gate of its own). Vitest tests for each new component + axe-core accessibility baseline. Playwright e2e spec (gated by `npm run test:e2e`) verifies the journey. NO dashboard `/recommendations` changes; NO `ApprovalQueue` changes; NO `RecommendationCard` changes. Phase 1 backend contract preserved verbatim.

**Risk tier:** HIGH (UI work touching financial explanation = financial correctness implications; accessibility governed by `DESIGN_SYSTEM.md`).

**Bounded list of files:** see §6 UI table.

**Acceptance criteria for PR 2:** AC1, AC2, AC3, AC5, AC6, AC8, AC9, AC10 above verified via Vitest + Playwright + axe-core. The backend substrate tests from PR 1 stay green (regression).

**Governance:** Both PRs follow the high-risk workflow (branch → PR → CI → independent `code-reviewer-minimax-m3` → 3-cycle cap → merge → squash + cleanup → synced `main`, then move to next Phase 2 task). Status updates land on `PROJECT_STATUS.json` after each PR merges.

---

## Authority + sign-off

- **Planning window:** 2026-07-31 → review.
- **Implementation window:** DOES NOT BEGIN until this document is reviewed and PR 1 above is explicitly authorized.
- **Authoritative anchors:** Phase 1 ADR (`docs/adr/ADR-006-IMMUTABLE-FORECAST-PERSISTENCE.md`); Phase 1 cert (`docs/10-roadmap/PHASE1_VERIFICATION_REPORT.md`); Phase Plan (`docs/10-roadmap/PHASE_PLAN.md`); atlas-project-tracker (`.agents/skills/atlas-project-tracker/SKILL.md`).
- **Reviewer checklist for sign-off:**
  1. Reuse map (§1) honors every Phase 1 contract cited in ADR-006.
  2. Acceptance criteria (§2) are testable end-to-end via the test files in (§7).
  3. Recommendation contract (§4) is deterministic, not model-derived.
  4. Decision-journal contract (§5) mirrors the Phase 1 append-only pattern verbatim.
  5. File plan (§6) is bounded and reviewable.
  6. Risk register remains untouched (§8).
  7. Exit criteria (§9) are 12 verifiable statements.
  8. PR split (§10) keeps each PR reviewable in three cycles.
