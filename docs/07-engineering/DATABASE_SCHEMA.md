# Database Schema

## Core aggregates

Users, households, memberships, profiles, goals, institutions, connections, accounts, transactions, securities, holdings, assets, liabilities, businesses, scenarios, forecasts, findings, recommendations, decisions, opportunities, policies, approvals, executions, and audit events.

## Conventions

UUID identifiers, UTC timestamps, explicit currency, decimal money, source provenance, soft deletion where appropriate, and version columns.

## History

Use snapshots or temporal records for balances, valuations, allocations, profiles, forecasts, and recommendations.

## Security

Tenant scope is mandatory. Sensitive fields are encrypted. Access paths are indexed without leaking secret values.

## AI data

Store structured evidence references and model metadata; do not treat free-form output as canonical truth.

## Phase 6 Scenario Lab persistence

The additive `W6a1b2c3d4e5` migration creates:

- `scenarios`: stable UUID identity, restrictive owner/goal/baseline-forecast
  links, USD lifecycle (`active`/`archived`), and latest-version pointer.
- `scenario_versions`: append-only immutable UUID rows with monotonic version,
  baseline forecast/version/hash, scenario hash, hashed idempotency key,
  schema/model/calculation versions, currency/freshness, canonical input JSON,
  complete result JSON, comparison JSON, and optional recommendation reference.

All UUID and SHA-256 fields are lowercase-constrained. Foreign keys use
`RESTRICT`; database triggers enforce owner/goal/baseline consistency and reject
version updates/deletes on SQLite and PostgreSQL. Downgrade refuses while either
scenario table contains history. Archive changes only the identity lifecycle;
it never cascades or deletes immutable versions.

Scenario JSON is canonical sorted JSON with bounded depth/collections/strings,
no binary floats, no raw transactions/statements/credentials/tokens, and no
client-supplied authoritative values. Monetary values remain exact canonical
Decimal strings until final USD-cent output using `ROUND_HALF_EVEN`.
