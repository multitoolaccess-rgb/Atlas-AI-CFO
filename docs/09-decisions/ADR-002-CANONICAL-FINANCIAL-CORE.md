# ADR-002: Canonical Financial Core

**Status:** Accepted

## Decision

Canonical financial facts and calculations live outside language models.

## Rationale

Financial accuracy, reproducibility, provenance, and testing require deterministic services.

## Consequences

Agents request calculations and cite results; they cannot directly mutate canonical truth.
