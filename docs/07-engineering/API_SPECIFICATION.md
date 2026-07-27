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
