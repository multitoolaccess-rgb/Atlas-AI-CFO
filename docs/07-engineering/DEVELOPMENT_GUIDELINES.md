# Development Guidelines

## Financial correctness

Use decimal money, explicit currency, deterministic rounding, tested date conventions, and versioned assumptions.

## Architecture

Keep domain logic pure where possible. External systems sit behind interfaces. Models cannot directly write canonical records or execute actions.

## Testing

Unit tests for calculations and policies; contract tests for connectors; integration tests for workflows; end-to-end tests for critical journeys; golden evaluations for agent behavior.

## Reliability

Idempotency, retries with backoff, reconciliation, observability, and safe degradation.

## Review

Security and domain review are required for permissions, execution, taxes, investing, and sensitive data.
