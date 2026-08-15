# Atlas Solo Development Policy v2

**Status:** Canonical governance policy
**Applies to:** Atlas personal, single-user, pre-production development

## Purpose and product boundary

Atlas is currently a personal, single-user application in pre-production. It
is not managing or moving real money autonomously. Documented non-critical bugs
are acceptable while the product is being built. Development is optimized for
useful progress, reasonable safety, and low agent and CI cost.

This policy changes delivery ceremony, not product safety. Financial
calculations, forecast and recommendation authority, authentication and
authorization, ownership isolation, immutable history, privacy boundaries,
credentials, migrations, external delivery, and execution boundaries remain
protected by their applicable contracts and focused tests.

## Risk classifications

### Low risk

Examples: documentation, copy, styling, visual tokens, generated tracker or
handoff updates, isolated test corrections, and non-behavioral refactors.

Required process:

- Run focused validation only.
- Direct commit to `main` is allowed.
- No PR, independent review, hosted CI, or active tracker work item is
  required unless the change is part of a phase exit.

### Medium risk

Examples: UI pages, navigation, redirects, client state, shared visual
components, non-financial API clients, accessibility or responsive corrections,
and normal developer tooling.

Required process:

- Add tests directly covering changed behavior.
- Run TypeScript and lint for frontend changes.
- Run focused browser journeys only when user interaction, navigation, or URL
  behavior changes.
- A feature branch is recommended.
- One cohesive PR is recommended for shared components or multi-file behavior.
- Independent review is optional.
- Known critical or high findings block merging. Medium and low findings may
  be documented as follow-up debt when they do not threaten data integrity,
  privacy, authorization, or financial correctness.
- Complete backend, frontend, cross-service, or Playwright matrices are not
  required by default.
- Hosted CI is not required when equivalent focused local validation has
  passed.
- A product PR must not expand into shared CI or test-infrastructure
  remediation. Defer infrastructure defects or handle them in a separate
  tooling task unless they prevent all meaningful validation.
- Frontend-owned route-mocked browser tests do not require Rules Service,
  Finlynq, OCR, or the live-stack harness.
- Live-stack browser validation is reserved for genuine backend/UI
  integration, authentication, cross-service behavior, phase certification,
  or explicit manual validation.

These rules keep normal UI delivery frontend-owned and avoid installing
unrelated service environments merely to exercise mocked navigation.


### High risk

Examples: financial calculations, forecast or recommendation authority,
authentication or authorization, ownership isolation, immutable history,
database migrations, privacy or sensitive-data handling, credentials or
external delivery, and money movement or execution boundaries.

Required process:

- Add focused tests covering changed behavior.
- Test directly affected contracts and integration boundaries.
- Use a feature branch and PR.
- Obtain a fresh independent review.
- Known critical or high findings block merging. Medium and low findings may
  be deferred unless they threaten data integrity, privacy, authorization, or
  financial correctness.
- Run relevant focused CI; a complete repository regression is not automatic.

## Full certification

Run complete repository and browser matrices only for:

- Phase completion.
- Release or completion tags.
- Repository-wide authentication or test-infrastructure changes.
- Shared startup or build infrastructure changes.
- A focused failure that provides concrete evidence of wider regression risk.
- An explicit user request for full certification.

## Test-selection rule

For every task:

1. Inspect the diff.
2. Identify changed behavior.
3. Identify its direct dependency radius.
4. Run the smallest test set that proves that behavior.
5. Expand testing only when evidence justifies expansion.
6. Record exactly what ran.
7. Never claim skipped checks passed.
8. Do not rerun unrelated green suites.

## Autonomy and stop conditions

Within an authorized task, agents may inspect and modify in-scope files, run
focused validation, create branches, commit and push, open or update PRs, use
internal reviewer subagents, apply valid corrections, merge when the applicable
risk gate passes, clean branches, synchronize `main`, and update tracker and
handoff evidence. Routine authorization is not required for another correction
cycle, PR maintenance, waiting for CI, valid review corrections, an approved
merge, governance reconciliation, or the next already-authorized bounded task.

Stop only for a material financial-policy or authority decision, scope
expansion, credentials or secrets, production deployment, destructive or
irreversible external action, persistent filesystem/Git/network/quota failure,
or the same blocker recurring three times without meaningful progress.

## Merge policy

- Low: focused checks pass.
- Medium: focused checks pass and no known critical or high defect remains.
- High: focused boundary checks pass and a fresh independent review reports no
  critical or high defect.
- Medium and low findings become follow-up debt rather than automatic blockers.
- Hosted heavy CI may be skipped when this policy allows; record it as skipped,
  never as passed.

## Maintenance

This file is the single authoritative human-readable policy. Agent
instructions, tracker skills, tracker schema references, development
guidelines, pull-request templates, and CI workflows should reference this
policy and describe only their local enforcement details. Do not copy the full
policy into those files.
