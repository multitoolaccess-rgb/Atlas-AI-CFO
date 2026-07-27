# Integration Architecture

## Sources

Banks, brokerages, payroll, tax systems, property data, market data, insurance, and user uploads.

## Pattern

Connector → authentication vault → ingestion job → raw immutable payload → normalization → reconciliation → canonical entities → derived intelligence.

## Requirements

Idempotency, rate-limit handling, refresh state, backoff, source timestamps, schema-version tracking, consent, and revocation.

## Execution integrations

Use separate credentials and permissions from read access. Material actions require policy checks, explicit scope, preview, confirmation where required, audit events, and status reconciliation.

## Failure principle

Stale or incomplete integration data must be visible and must reduce recommendation confidence.
