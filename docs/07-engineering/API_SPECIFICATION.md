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

## Phase 5 Market Brief reliability correction

The owner-scoped Market Brief APIs remain default-off and server-authoritative.
New generated records preserve the existing immutable/idempotent storage contract
and include additive `coverage`, `market_data_basis`, `provider_readiness`, and
`portfolio_daily_change` fields. Existing v1 records remain readable.

Quote policy is deterministic and uses `America/New_York` from a standard-library
calendar abstraction. During Monday–Friday regular US market sessions, defined
as 09:30 inclusive through 16:00 exclusive Eastern time excluding the documented
full-day US market holidays (New Year’s Day, Martin Luther King Jr. Day,
Presidents’ Day, Good Friday, Memorial Day, Juneteenth, Independence Day,
Labor Day, Thanksgiving Day, and Christmas Day), a quote is `live` only when its observed timestamp
is not future-dated, falls in the current session, and is no older than 15
minutes. Outside regular sessions (premarket, after-hours, weekends, and
holidays), the most recent close observed at or after the 16:00 close boundary
is accepted as `prior_close` only when it is no more than three completed
trading sessions old. Prior-close data is never labelled live. Early closes are
not modeled and therefore do not expand the accepted window.

Every active non-cash holding is evaluated independently. Coverage is
`value_weighted` when every eligible holding has a finite non-negative current
value and the total is positive; otherwise it is `position_count`. Generation
requires at least `0.80` coverage on the selected basis, and always fails closed
when no holding is covered, currency is mixed/ambiguous, or required quote
inputs are invalid. New records persist eligible, covered, omitted counts,
coverage percentage/basis, omitted symbols, and bounded omission reason codes.
The coverage and price basis are included in the canonical input/universe
hashes, so an idempotent replay cannot silently change its data basis.

Generation failures use the sanitized envelope
`{code, reason_code, message, recovery}`. Stable reason codes are:
`provider_configuration_missing`, `provider_transport_failure`,
`provider_authentication_failed`, `provider_rate_limited`, `unsupported_symbol`,
`live_quote_stale`, `prior_close_too_old`, `invalid_quote`,
`ambiguous_currency`, `insufficient_portfolio_coverage`,
`no_market_addressable_holdings`, and `market_brief_generation_unavailable`.
Messages never include credentials, provider payloads, account identifiers,
internal exception text, or raw holdings.
