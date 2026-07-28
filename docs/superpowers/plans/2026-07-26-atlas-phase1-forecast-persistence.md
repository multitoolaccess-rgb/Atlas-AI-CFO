# Atlas Phase 1 Forecast Persistence Implementation Plan

> Planning artifact only. Do not implement any task until ADR-006 and this
> sequence are reviewed and explicitly authorized.

**Goal:** Add immutable, user-scoped forecast persistence and versioned read
APIs around the authoritative Phase 0 projection calculation.

**Scope:** Rules Service forecast persistence, one idempotent generation
command, and versioned read APIs.

**Non-goals:** UI migration, recommendation models, decision journal,
household migration, Monte Carlo probability, autonomous execution, dependency
modernization, and legacy product-name cleanup.

## Architecture summary

`Forecast` is a stable user-and-goal-scoped identity. `ForecastVersion` is an
append-only result with canonical snapshots and model/calculation identity.
The pure projection module remains unchanged and is invoked by an application
service. Routes authorize and validate requests; repositories own transactions
and persistence; Pydantic schemas define string-safe Decimal API contracts.

Phase 1 adds no Finlynq table reads and no production UI consumer.

## Planned data contract

### `forecasts`

| Field | Contract |
| --- | --- |
| `id` | Canonical UUID string primary key |
| `user_id` | Transitional FK to `users.id`, indexed, restrictive delete |
| `goal_id` | FK to `goals.id`, indexed, restrictive delete |
| `forecast_kind` | `goal_projection` in Phase 1 |
| `currency` | Uppercase ISO 4217; `USD` only in Phase 1 |
| `lifecycle_state` | Mutable identity-level state; `active` only in Phase 1 |
| `latest_version_number` | Mutable optimistic-concurrency pointer |
| `created_at`, `updated_at` | UTC timestamps |

Unique identity: `(user_id, goal_id, forecast_kind, currency)`.

### `forecast_versions`

| Field | Contract |
| --- | --- |
| `id` | Canonical UUID string primary key |
| `forecast_id` | FK to `forecasts.id`, indexed, restrictive delete |
| `version_number` | Positive monotonic integer per forecast |
| `input_state_hash` | Lowercase SHA-256 canonical-state digest |
| `idempotency_key_hash` | SHA-256 digest; never store the raw key |
| `snapshot_schema_version` | Snapshot wire-format version |
| `hash_schema_version` | Canonicalization/hash version |
| `model_version` | Forecast domain-contract version |
| `calculation_version` | Phase 0 projection `MODEL_VERSION` |
| `currency` | Explicit currency copied into the immutable version |
| `calculated_at`, `data_as_of`, `created_at` | Calculation/freshness/history |
| `max_data_age_days`, `data_age_days` | Freshness policy and observed age |
| `input_snapshot_json` | Canonical normalized input JSON |
| `assumption_snapshot_json` | Canonical explicit assumption JSON |
| `output_snapshot_json` | Canonical scenarios, drivers, and results JSON |
| `provenance_snapshot_json` | Canonical source references and timestamps |
| query fields | Selected `NUMERIC(38, 2)` ending balances and target gap |

Constraints:

- unique `(forecast_id, version_number)`;
- unique `(forecast_id, input_state_hash, model_version,
  calculation_version)`;
- unique `(forecast_id, idempotency_key_hash)`;
- positive version and data-age checks;
- immutable version update/delete guards.

Snapshot money is a canonical fixed-scale decimal string. Queryable money uses
`Numeric(38, 2, asdecimal=True)`. Rates, inflation, and other fractional
assumptions remain unrounded canonical Decimal strings in versioned snapshots;
they must not use a scale-2 monetary column. A later queryable fractional field
requires `NUMERIC(38, 18)` or a separately reviewed higher-scale contract. No
`Float` enters the new model or schemas.

`forecast_versions` contains immutable reasoning. Any future lifecycle state
belongs on the stable `forecasts` row or a separate lifecycle table; it never
rewrites a historical version.

## Canonical projection-state envelope

The explicit adapter boundary is `atlas-projection-state/v1`:

```text
Finlynq canonical state -> typed adapter -> Rules Service forecast service
```

Finlynq owns ingestion and canonical financial state. The adapter owns
normalization into the envelope. Rules Service owns forecast calculation and
persistence. Rules Service must not query Finlynq database tables directly.

The versioned, bounded envelope contains:

- `schema_version` and canonicalization/hash metadata;
- transitional `user_id` and `goal_id`;
- UTC `as_of_timestamp` and explicit uppercase currency;
- typed current-value components and contribution/investable-cash-flow inputs,
  with canonical Decimal strings;
- freshness policy and observed age;
- bounded source-system identifiers, stable record/aggregate identifiers,
  timestamps, counts, and hashes;
- missing-data indicator codes; and
- deterministic confidence or reconciliation-state enums when available.

It excludes raw statements, raw transaction payloads, uploaded files,
credentials, unbounded free-form source data, and unnecessary personal
information. A source-state hash covers normalized components and provenance;
the forecast stores only that hash and the bounded references.

For v1 component and contribution money strings, accept at most 38 digits
excluding sign and decimal point, at most 18 fractional digits, and at most 40
encoded characters. These are unrounded input/hash bounds; validation rejects
rather than rounds or truncates. Fractional assumptions are not accepted by
this envelope and retain their separate later-slice contract.

No v1 envelope collection is order-meaningful. Canonicalization sorts
current-value and contribution entries by `(kind, source_reference,
observed_at)`, provenance by `(source_system, reference_id, observed_at)`,
and missing-data codes lexically. Duplicate identity keys are rejected.

## API contracts

### Generate a version

`POST /api/v1/goals/{goal_id}/forecasts`

Required headers:

- `Idempotency-Key`
- `If-None-Match: *` for first creation, or `If-Match: "<etag>"` when the
  caller has observed an existing forecast
- correlation ID using the repository's established request contract when
  available

The end-user request has no client-supplied financial-state body in Phase 1.
Its only control inputs are `Idempotency-Key`, the conditional header, and the
repository's established correlation header when available. `forecast_kind` is
fixed to `goal_projection`; the server selects the approved, versioned
assumption profile. User-selected profiles and field-level assumption overrides
are not accepted in Phase 1. A later reviewed contract must enumerate any
allowed override fields, strict numeric bounds, server-side canonicalization,
and a separate `user_selected_assumptions` snapshot before accepting them.

Strict request validation rejects unknown JSON fields rather than silently
ignoring them. The client cannot submit `user_id`, `household_id`, current
balance or net worth, financial-state-derived contributions, canonical snapshot
content, account-derived currency, freshness timestamps, source identifiers,
provenance, transaction or statement data, reconciliation state, input-state
hash, or model/calculation version. The client neither supplies nor signs an
envelope.

The server derives user scope from authentication, authorizes and loads the
goal, then invokes the trusted adapter exactly once. The adapter obtains the
authoritative canonical state through the sanctioned Finlynq boundary and
creates `atlas-projection-state/v1`; Rules Service validates its schema and
freshness, hashes it server-side, calculates, and persists. A cross-user or
missing goal returns 404 before adapter invocation. No separate trusted
service-generation API exists in Phase 1.

Responses:

- `201 Created` for a newly persisted version;
- `200 OK` for an idempotent replay or identical state already persisted;
- `400`/`422` for malformed or unsupported inputs;
- `404` for a missing or non-owned goal/forecast;
- `409 forecast_version_conflict` for stale `If-Match`;
- `409 idempotency_conflict` for key reuse with a different normalized input;
- `503` when forecast persistence is disabled.

The response includes stable forecast/version IDs, version number, ETag,
location links, model/calculation versions, currency, freshness, and snapshots.

### Read forecasts

- `GET /api/v1/forecasts?goal_id=&cursor=&limit=`
- `GET /api/v1/forecasts/{forecast_id}`
- `GET /api/v1/forecasts/{forecast_id}/versions?cursor=&limit=`
- `GET /api/v1/forecasts/{forecast_id}/versions/{version_number}`

Collections order by stable `(created_at, id)` or
`(version_number, id)` keys and use opaque cursor tokens. Every read filters by
the authenticated `user_id`; cross-user resources return 404. The stable
forecast response links the latest version but never overwrites history.

## Canonical hashing procedure

1. Convert source money to validated `Decimal`; convert legacy goal floats
   with `Decimal(str(value))`, record `source_representation: "float"`, and
   set `precision_restored: false`. This conversion cannot restore Float
   precision already lost.
2. Preserve canonical unrounded Decimal strings needed for calculation and
   hashing; quantize only persisted/display monetary outputs with
   `ROUND_HALF_EVEN`.
3. Normalize currency, dates, contribution timing, assumptions, freshness,
   source references, and goal ID.
4. Serialize Decimal values as canonical strings, dates as ISO date strings,
   and instants as timezone-aware UTC RFC 3339 strings with a `Z` suffix.
5. Serialize JSON with sorted keys, UTF-8, and compact separators.
6. Hash the bytes with SHA-256.
7. Store `hash_schema_version` beside the digest.

Changing calculation or model version creates a new version even when the
input-state hash is unchanged.

The output snapshot stores the target-status boolean with its unrounded
canonical decision operands. API and UI display formatting must never recompute
or alter target status. Fixtures include Float-to-canonical-string and
rounding-boundary cases proving those constraints.

## Exact implementation sequence

### 0. Canonical envelope contract

**Create:**

- `services/rules-service/app/forecasts/canonical_state.py`
- `services/rules-service/tests/test_canonical_projection_state.py`

Define typed `atlas-projection-state/v1` dataclasses or Pydantic models and a
narrow adapter protocol. Validate bounded component kinds, UTC timestamps,
currency, Decimal strings, freshness, provenance references, missing-data
codes, and deterministic reconciliation state. Reject raw payload fields and
unknown unbounded source data. The adapter is invoked only after goal
authorization, obtains authoritative canonical state through the sanctioned
Finlynq boundary, and creates provenance from trusted server-side references.
The test fixture must prove Rules Service can calculate from the envelope
without a Finlynq database query.

### 1. Contract tests and canonical snapshot fixtures

**Create:**

- `services/rules-service/tests/fixtures/atlas_forecast_snapshots_v1.json`
- `services/rules-service/tests/test_forecast_contract.py`
- `services/rules-service/tests/test_forecast_hashing.py`

Define fixed UUIDs, timestamps, Decimal strings, canonical JSON, SHA-256
digests, API error envelopes, ETags, pagination ordering, freshness, and
provenance cases. Include large values, half-even boundaries, stale inputs,
idempotent replay, conflicting keys, cross-user access, legacy
Float-to-canonical-string inputs, and target-status rounding boundaries.

Add request-boundary tests proving a client cannot submit balances, provenance,
freshness timestamps, or another user identifier; unknown fields are rejected;
and user-selected assumption overrides cannot change authoritative state.
Route/service tests must prove a cross-user goal returns 404 before adapter
invocation, a valid request invokes the adapter exactly once, adapter output
supplies the hashed canonical state, and idempotent replay neither obtains nor
persists a conflicting client snapshot.

### 2. Models and migration

**Create:**

- `services/rules-service/app/models/forecast.py`
- `services/rules-service/alembic/versions/<revision>_add_forecast_history.py`
- `services/rules-service/tests/test_forecast_models.py`
- `services/rules-service/tests/test_forecast_migration.py`

**Modify:**

- `services/rules-service/app/models/__init__.py`

Branch from Alembic head `Q5h1i2j3k4l5`. Create the identity table before the
version table, then indexes, uniqueness/check constraints, and
dialect-appropriate immutability guards. Test empty upgrade/downgrade,
upgrade-at-head idempotency, Decimal round trips, FK restriction, duplicate
rejection, update/delete rejection, and downgrade refusal when history exists.

Do not change `goals.target_amount` in this migration.

### 3. Serialization, hashing, and repository layer

**Create:**

- `services/rules-service/app/forecasts/snapshots.py`
- `services/rules-service/app/forecasts/repository.py`
- `services/rules-service/tests/test_forecast_repository.py`

Implement deterministic JSON and SHA-256 without adding dependencies. Keep
transaction ownership in the repository. Add PostgreSQL row-lock behavior and
SQLite short-transaction/unique-conflict recovery. Prove concurrent identical
requests converge and concurrent changed-state requests return a conflict.

### 4. Generation application service

**Create:**

- `services/rules-service/app/forecasts/service.py`
- `services/rules-service/tests/test_forecast_service.py`

After the route authorizes and loads the goal, invoke the trusted adapter once,
validate the returned envelope, enforce USD/freshness, call the existing
`project_scenarios`, build immutable snapshots, and persist through the
repository. Keep projection mathematics pure and unchanged. Reject generation
while the persistence flag is disabled. The service receives the adapter's
explicit canonical state; it does not query Finlynq-owned tables or accept a
client-provided envelope.

### 5. Pydantic API schemas

**Create or modify:**

- `services/rules-service/app/schemas/forecast.py` if schemas are split first,
  otherwise the existing schema package
- `services/rules-service/tests/test_forecast_schemas.py`

Expose response Decimal money as strings with documented patterns. The Phase 1
generation request model accepts no JSON financial-state fields and uses
`extra="forbid"` or the framework-equivalent strict rejection. It must reject
owner identifiers, balances, contributions, snapshots, freshness, provenance,
source records, reconciliation state, input hashes, version numbers, outputs,
and model/calculation versions. Define stable errors, links, ETag, freshness,
provenance, and cursor envelopes.

No dependency reorganization is required merely to split schemas.

### 6. Authenticated generation and read routes

**Create:**

- `services/rules-service/app/routes/forecasts.py`
- `services/rules-service/tests/test_routes_forecasts.py`

**Modify:**

- `services/rules-service/app/main.py`

Register only the bounded `/api/v1` endpoints. Reuse `require_user` and
`get_or_create_local_user`, derive scope server-side, authorize and load the
goal before adapter invocation, and apply `user_id` to every repository query.
Cover missing auth, wrong subject, cross-user 404 before adapter invocation,
rejection of balances/provenance/freshness/user-ID/unknown request fields,
single adapter invocation for a valid generation, archived-goal history,
idempotent replay without a conflicting client snapshot, conditional generation,
409 envelopes, pagination, and flags. Add no PUT, PATCH, or DELETE route.

### 7. Feature flags, rollout observability, and operator documentation

**Modify:**

- `services/rules-service/app/config.py`
- safe example environment files
- Rules Service operating documentation

Add two default-off flags without changing requirements. Log forecast/version
IDs, version/hash schema, calculation version, latency, outcome, and
correlation ID; do not log snapshots, money values, idempotency keys, tokens,
or financial inputs.

Define shadow comparison counters for generated/not-persisted, idempotent
reuse, conflicts, validation failures, stale inputs, and read errors.

### 8. Bounded pre-enable operator validation

**Create:**

- `services/rules-service/app/forecasts/shadow_validate.py`
- `services/rules-service/tests/test_forecast_shadow_validate.py`
- operator documentation for `shadow_validate`

Implement only the explicitly invoked command:

`python -m app.forecasts.shadow_validate --user-id <id> --goal-id <id> --limit 1 --dry-run`

Require one user and one goal, require `--limit 1`, invoke the canonical-state
adapter, calculate/compare a proposed forecast, and emit structured output.
Default to dry-run; never enable, bypass, or override feature flags. Output may
contain identifiers, version metadata, hashes, freshness/comparison outcomes,
flag state, correlation ID, and duration, but never raw financial values,
snapshots, statements, credentials, or tokens. Do not invoke it during reads
or schedule/background it. Any non-dry persistence behavior requires a later
authorization after the relevant flag is enabled.

### 9. Verification and rollout gate

Run, in order:

1. focused hashing/snapshot/model/migration/repository/service/route tests;
2. Phase 0 projection tests;
3. complete Rules Service suite;
4. cross-service tests proving no Finlynq ownership regression;
5. Python compilation;
6. migration upgrade, current-head check, guarded downgrade, and re-upgrade;
7. security review of user scoping, errors, logs, and snapshot minimization;
8. schema/API review for Decimal strings, currency, freshness, and provenance;
9. feature flags off on a clean database;
10. bounded operator validation using synthetic data only.

Rollout proceeds only when deterministic replay, cross-user isolation,
immutability, Decimal round-trip, and conflict tests pass. Phase 2 UI work
requires a separate authorization after Phase 1 exit criteria are complete.
External multi-user production enablement remains blocked until a retention and
user-deletion policy is approved.

## Phase 1 exit criteria

- ADR-006 accepted.
- Additive migration reviewed and rollback rehearsed.
- Stable forecast identity and immutable version history enforced.
- Decimal/currency and canonical hashing contracts pass on SQLite and
  PostgreSQL.
- Idempotent generation and optimistic concurrency behavior pass.
- All forecast reads are user-scoped and versioned.
- Freshness/provenance snapshots are complete and minimized.
- Flags default off; bounded operator validation and rollback evidence are
  documented.
- External multi-user production enablement is blocked pending an approved
  retention and user-deletion policy.
- Complete Rules Service and cross-service suites pass.
- No UI, recommendation, decision-journal, household, or probability behavior
  changed.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Existing `Goal.target_amount` is `Float` | Convert through `Decimal(str(...))`, record the Float source representation and non-restored precision, add boundary fixtures, and plan canonical goal-money migration separately. |
| SQLite and PostgreSQL differ in numeric/locking behavior | Add cross-dialect Decimal round-trip and concurrency tests; use unique constraints as final arbiter. |
| App-only immutability could regress | Add database guards and tests that direct update/delete fail. |
| Hash changes could create silent duplicates | Version canonicalization and use golden digest fixtures. |
| Idempotency races could allocate duplicate versions | Lock identity row where supported, enforce uniqueness, and re-read after conflicts. |
| Provenance snapshots could copy excessive financial data | Store source references, timestamps, and hashes—not raw transactions or statements. |
| Transitional user scope could be mistaken for household tenancy | Keep explicit `user_id`, cross-user tests, and no household naming/backfill. |
| Append-only growth has no approved purge policy | Retain history, add no purge or cascade, block external multi-user production enablement, and defer deletion policy approval. |

## Resolved planning decisions

1. Finlynq provides canonical financial state through the typed,
   versioned `atlas-projection-state/v1` adapter envelope; Rules Service never
   reads Finlynq tables directly.
2. Pre-enable comparison uses the bounded, explicitly invoked
   `shadow_validate` operator command in dry-run mode. It is not synchronous,
   scheduled, or invoked by read requests.
3. Forecast history is provisionally retained during development and default-off
   validation. It has no purge/cascade path, and external multi-user production
   enablement is blocked until retention and user-deletion policy is approved.

## Deferred decisions

- Permanent retention, legal hold, account deletion, backup deletion, and
  household migration policy.
- Scheduled or background validation after bounded operator validation proves
  safe and useful.
- A reviewed canonical Goal Decimal migration.
