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
