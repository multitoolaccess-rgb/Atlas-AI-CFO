# Development Guidelines

## Canonical development policy

Apply `docs/07-engineering/SOLO_DEVELOPMENT_POLICY.md` for Atlas’s risk
classification, focused test selection, review and merge gates, autonomy,
stop conditions, local-only validation, and full-certification rules. This
document describes engineering practices and must not duplicate or strengthen
that policy. GitHub Actions is intentionally disabled; local commands and
bounded suites are the authoritative evidence.

## Financial correctness

Use decimal money, explicit currency, deterministic rounding, tested date
conventions, and versioned assumptions.

## Architecture

Keep domain logic pure where possible. External systems sit behind interfaces.
Models cannot directly write canonical records or execute actions.

## Testing

Use unit tests for calculations and policies, contract tests for connectors,
integration tests for workflows, end-to-end tests for critical journeys, and
golden evaluations for agent behavior. Select the smallest local test set that
proves the changed behavior and expand only when evidence shows a wider
dependency; run the complete local matrix at phase and release boundaries.

## Reliability

Use idempotency, retries with backoff, reconciliation, observability, and safe
degradation.

## Review

Security and domain review remain required for permissions, execution, taxes,
investing, and sensitive data. The applicable risk tier and finding threshold
come from the canonical policy.

## Personal-use boundary

Atlas remains a personal, single-user, pre-production application. Open
retention and user-deletion risks block external multi-user rollout only.
Currency uncertainty must fail closed, and advisor access, household tenancy,
and autonomous financial execution remain out of scope.
