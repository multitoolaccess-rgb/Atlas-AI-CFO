# API Specification

## Style

Versioned resource APIs with authenticated household scope, idempotency for writes, stable errors, and correlation IDs.

## Core resources

Profiles, households, goals, accounts, transactions, holdings, scenarios, recommendations, decisions, opportunities, policies, approvals, and audit events.

## Requirements

Authorization on every request, currency-safe decimal representation, ISO timestamps, pagination, optimistic concurrency, provenance, and data-freshness metadata.

## Actions

Material actions use preview and commit semantics. Commit requests require an idempotency key and current approval token.

## Errors

Distinguish validation, authorization, stale state, integration failure, policy rejection, and temporary unavailability.

## Phase 6 Slice 1 — Scenario Lab backend

The server-owned, default-off Scenario Lab is exposed under `/api/v1` only:

- `POST /goals/{goal_id}/scenarios` — generate/persist or idempotently replay a
  bounded scenario against the latest owned immutable forecast baseline.
- `GET /goals/{goal_id}/scenarios` — bounded owner/goal list with cursor and
  optional archive inclusion.
- `GET /scenarios/{scenario_id}` — owner-scoped latest identity/version.
- `GET /scenarios/{scenario_id}/versions/{version_number}` — immutable version.
- `GET /scenarios/{scenario_id}/compare` — baseline comparison for one saved
  scenario.
- `POST /scenarios/compare` — compare one to three compatible saved scenarios.
- `POST /scenarios/{scenario_id}/archive` — archive without deleting history.

Generation and archive require `Idempotency-Key`; scenario request bodies use
`extra="forbid"`. The client supplies only explicit monthly contribution
change/date controls and one dated positive outflow. Owner, goal authorization,
canonical state, currency, freshness, baseline identity/version, hashes,
assumptions, results, and calculation versions are server-derived. Unsupported,
stale, mixed, unknown, unreconciled, or non-USD canonical state fails closed.

A date maps to the first eligible monthly boundary on or after the date. A
one-time outflow is deducted once after that boundary's return and scheduled
contribution using unrounded Decimal arithmetic; insufficient liquidity is a
validation failure, not inferred debt. Results contain deterministic bands and
must not use probability language. Cross-owner resources return the same 404
contract as missing resources. Compare accepts at most three compatible
scenarios; list limits are at most 50.
