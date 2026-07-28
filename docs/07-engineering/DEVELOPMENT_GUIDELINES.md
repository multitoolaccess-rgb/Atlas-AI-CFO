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

## Solo-development governance

Classify work before starting. Low-risk documentation, comments, formatting,
naming, and coverage-preserving test improvements may go directly to `main`
after relevant checks and diff review; no issue, branch, PR, or status update is
needed. Medium-risk UI, internal refactoring, developer scripts, read-only
endpoints, observability, and non-sensitive integrations should be validated;
a branch is recommended and a PR is optional. High-risk financial logic,
migrations, authentication, privacy, recommendations, financial integrations,
money movement, autonomy, or destructive behavior requires a branch, PR, CI,
independent review, and material status/risk evidence. Use
`atlas-project-tracker` for classification and status operations. Do not update
project status for every prompt—only for phase milestones, material
deliverables, blockers, significant risks, or next-task changes.
