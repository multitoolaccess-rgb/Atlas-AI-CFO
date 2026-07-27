# ADR-006: Immutable Forecast Persistence and Versioned Read APIs

- **Status:** Proposed
- **Date:** 2026-07-26
- **Scope:** Phase 1 forecast persistence and read APIs
- **Related:** ADR-004, ADR-005, issue #3

## Context

ADR-005 made Rules Service authoritative for deterministic projections and
deferred forecast storage and APIs. Phase 1 must persist reproducible results
without migrating the UI, changing projection mathematics, introducing
probabilities, or pretending that the current single-user authorization model
is household tenancy.

The current service has one Alembic head (`Q5h1i2j3k4l5`), supports SQLite in
local development and CI, and is designed for PostgreSQL. Goals are scoped by
`user_id`; their existing `target_amount` uses a legacy `Float`. The Phase 0
projection module accepts explicit Decimal-compatible strings and returns
immutable dataclasses with deterministic scenario outputs.

## Decision

### Stable forecast identity and goal linkage

A `forecast` is a stable logical series, not one calculation. Its public ID is
an application-generated UUID encoded as a lowercase canonical string. A
forecast is uniquely identified by:

- transitional `user_id`;
- `goal_id`;
- `forecast_kind` (`goal_projection` in Phase 1); and
- `currency`.

The database enforces that tuple as unique. The goal link is fixed for the
life of the forecast. Goal archive does not remove forecasts, and foreign keys
use restrictive deletion semantics so history cannot disappear implicitly.
Phase 1 supports one goal per forecast. Multi-goal forecasts require a later
ADR because they change calculation and conflict semantics.

### Immutable versions

Each calculation creates a `forecast_version` beneath the stable forecast.
Versions have a UUID, a monotonically increasing integer `version_number`, and
unique `(forecast_id, version_number)`. Version rows are never updated or
deleted by application code. Database-level update and delete guards protect
them on supported dialects; the migration removes those guards before an
explicit schema downgrade.

The mutable forecast identity row may advance `latest_version_number` inside
the same transaction that inserts a version. Historical versions remain
addressable and retain their original goal, input, assumption, output,
freshness, and provenance snapshots.

### Decimal money and currency

No Phase 1 persistence or API field accepts or emits binary floating-point
money.

- Python uses `Decimal`.
- JSON snapshots and API responses encode money as canonical fixed-scale
  decimal strings.
- Queryable monetary columns use `NUMERIC(38, 2)` through SQLAlchemy
  `Numeric(..., asdecimal=True)` and are checked by cross-dialect round-trip
  tests.
- Every snapshot and response carries an uppercase ISO 4217 currency code.
- Phase 1 accepts only `USD`, matching ADR-005. It does not infer currency
  from user preferences or source accounts.
- Persisted outputs are quantized to cents with `ROUND_HALF_EVEN`.

The legacy goal `Float` is not silently rewritten in this phase. Its value is
converted with `Decimal(str(value))`, validated, quantized, and recorded in
the immutable input snapshot. The precision limitation is an explicit risk
until a separately reviewed canonical-goal money migration occurs.

### Versioned snapshots and calculation identity

Every version stores:

- `snapshot_schema_version`;
- `hash_schema_version`;
- `model_version`, identifying the forecast contract;
- `calculation_version`, copied from the projection module's
  `MODEL_VERSION`;
- canonical normalized input snapshot;
- complete assumption snapshot;
- complete output and driver snapshot;
- source-data freshness snapshot;
- provenance references; and
- `calculated_at`, `data_as_of`, `created_at`, and currency.

Snapshots are deterministic canonical JSON: UTF-8, sorted keys, no
insignificant whitespace, ISO dates/timestamps, and Decimal values encoded as
canonical strings. They do not contain raw transactions, uploaded statements,
credentials, or tokens.

### Input-state hashing and idempotent generation

`input_state_hash` is lowercase SHA-256 over the canonical normalized input,
assumption, freshness, and provenance snapshot. Hash construction is versioned
by `hash_schema_version`. Calculation and model versions are separate columns,
so the same financial state under a new calculation or contract creates a new
version.

The database enforces uniqueness on:

`(forecast_id, input_state_hash, model_version, calculation_version)`.

The sole Phase 1 write action is authenticated forecast generation. It
requires an `Idempotency-Key`; only its SHA-256 digest is stored. Repeating the
same key and request returns the existing result. Reusing the key for a
different input hash returns HTTP 409 `idempotency_conflict`. A different key
with identical normalized state and versions resolves to the existing version
rather than creating a duplicate.

### Data freshness and provenance

Generation preserves the Phase 0 freshness validation before any write. The
snapshot records the calculation date, source `data_as_of`, permitted maximum
age, actual age, source type, source stable identifier or aggregate identifier,
source update timestamp, and a source-state hash.

Rules Service receives explicit canonical state. It does not query
Finlynq-owned tables directly. Provenance references describe inputs without
copying user statements or transaction histories into forecast rows.

### Transitional ownership and authorization

Phase 1 retains `forecasts.user_id -> users.id`. Every generation and read
query first resolves the authenticated JWT subject to the local user and then
filters by `user_id`. A missing or cross-user forecast returns 404 to avoid
confirming another user's resource.

`user_id` remains transitional. No field, route, or index is named or
documented as permanent household scope, and Phase 1 performs no household
backfill or dual-read migration.

### API contract

The bounded API surface is:

- `POST /api/v1/goals/{goal_id}/forecasts:generate`
- `GET /api/v1/forecasts`
- `GET /api/v1/forecasts/{forecast_id}`
- `GET /api/v1/forecasts/{forecast_id}/versions`
- `GET /api/v1/forecasts/{forecast_id}/versions/{version_number}`

The POST is the persistence command, not mutable forecast CRUD. There are no
PUT, PATCH, or DELETE forecast routes. Read collections use stable cursor
pagination and deterministic ordering. Responses include schema version,
currency, freshness, provenance, model/calculation versions, canonical money
strings, links, and an ETag derived from forecast ID and latest version.

Generation accepts `If-Match` for an existing forecast and
`If-None-Match: *` for first creation. A stale expected version returns HTTP
409 with stable code `forecast_version_conflict`, the current ETag and latest
version number, and no financial payload. Constraint races are translated to
the same stable contract after the transaction is rolled back and current
state is re-read.

### Transaction and concurrency model

Generation runs in one database transaction:

1. authorize and load the user-owned goal;
2. normalize, validate, hash, and calculate outside any long-held write lock;
3. get or create the stable forecast;
4. lock or otherwise serialize the forecast identity row;
5. re-check idempotency and `If-Match`;
6. allocate the next version number;
7. insert the immutable version and advance the latest pointer; and
8. commit.

PostgreSQL uses row locking. SQLite uses a short write transaction plus unique
constraints and conflict retry. A unique-race loser re-reads the winning row;
it returns that row if idempotent, otherwise HTTP 409.

### Migration, retention, and rollback

One Phase 1 Alembic revision follows `Q5h1i2j3k4l5` and creates the forecast
identity table before the version table, indexes, uniqueness constraints, and
immutability guards. It contains no backfill and does not modify existing
goals, recommendations, or financial tables.

Normal application rollback disables generation, disables new read routes,
and deploys the previous application while leaving the additive tables intact.
Schema downgrade is permitted only when the forecast tables are empty or an
approved export and deletion procedure has run. Downgrade removes immutability
guards, then the version table, then the forecast table.

Forecast versions have no Phase 1 purge endpoint or cascade delete. They are
retained until an approved retention/deletion policy supplies authorization,
audit, export, and legal requirements.

### Feature flags and rollout

Two server-side flags default off:

- `ATLAS_FORECAST_PERSISTENCE_ENABLED`
- `ATLAS_FORECAST_READ_API_ENABLED`

Rollout order is migration with both flags off, internal shadow generation and
comparison, read API enablement for authorized test users, persistence
enablement, and measured expansion. The production UI does not consume these
routes in Phase 1. Rollback first disables generation and then reads.

## Consequences

- Forecast history becomes reproducible and independently readable.
- Storage grows append-only and requires explicit retention policy later.
- The current user-scoped authorization boundary remains visible and tested.
- SQLite/PostgreSQL Decimal and concurrency behavior need explicit parity
  tests.
- The existing goal `Float` can limit source precision even though persisted
  forecast snapshots never use floats.
- ADR-005's forecast schema/API deferral is resolved by this ADR when accepted;
  all other ADR-005 deferrals remain.

## Non-goals

- UI migration
- Recommendation models
- Decision journal
- Household migration
- Monte Carlo probability
- Autonomous execution
- Dependency modernization
- Legacy product-name cleanup

## Unresolved questions for implementation review

1. What is the approved canonical source-state contract supplied by Finlynq or
   an aggregation boundary, given that direct table reads are prohibited?
2. Should shadow generation be synchronous in the request path or invoked by a
   bounded operator command before API generation is enabled?
3. What production retention and user-deletion policy will ultimately govern
   immutable forecast history?

