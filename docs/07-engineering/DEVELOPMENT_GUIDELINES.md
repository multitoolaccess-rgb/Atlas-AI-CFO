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

Classify work before starting. Use the `atlas-project-tracker` skill for
classification and status operations.

### Low risk

Documentation, comments, formatting, styling-only changes, test cleanup,
generated documentation. Process: direct commit to `main`; run focused
validation; no branch, PR, independent review, CI evidence, or active
tracker item required.

### Medium risk

UI features, read-only API composition, mappers, schemas, explanations,
non-financial application logic. Process: one cohesive feature branch;
focused and relevant regression tests; PR and independent review optional;
squash-merge after validation; CI required only when the change affects
shared application behavior. Do not split one vertical slice into mapper /
schema / route micro-PRs without a concrete dependency or safety reason.

### High risk

Financial mathematics, persisted financial state, database migrations,
authentication / authorization, write APIs, privacy / security boundaries,
external execution. Process: one cohesive branch and PR; required relevant
CI; one fresh independent review; maximum two correction-and-review
cycles. If material findings remain after two cycles, stop with the
exact unresolved decision. Record test, CI, review, and commit evidence
before completion.

## Tracking policy

- Update project status only when material work starts, completes,
  changes phase, or becomes genuinely blocked.
- Do not create tracker-evidence commits after every implementation
  correction. Fold final tracker evidence into the implementation commit
  when practical, or use one final evidence commit.
- Do not require issues for routine work.
- Do not require PR comments duplicating tracker evidence.
- Phase exit criteria remain enforced.
- Existing historical evidence must remain intact.

## Personal-use boundary

- Phase 2 personal single-user development may proceed under the tiered
  workflow above.
- Open retention / user-deletion risks block external multi-user
  production rollout only.
- Currency uncertainty must continue to fail closed.
- Advisor access, household tenancy, and autonomous financial execution
  remain out of scope.
