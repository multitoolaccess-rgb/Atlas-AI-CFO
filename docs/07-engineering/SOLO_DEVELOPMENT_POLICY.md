# Atlas Solo Development Policy v2

**Status:** Canonical governance policy
**Applies to:** Atlas personal, single-user, pre-production development

## Purpose and product boundary

Atlas is currently a personal, single-user application in pre-production. It
is not managing or moving real money autonomously. Documented non-critical bugs
are acceptable while the product is being built. Development is optimized for
useful progress, reasonable safety, and low agent and local-validation cost.

GitHub is Atlas's private source repository and history backup. GitHub Actions
is intentionally disabled for this repository, so hosted CI is never required
for normal changes, phase completion, releases, or tags. Local validation is
authoritative; no workflow URL is required as evidence. Pull requests remain
optional history and collaboration records for a solo developer.

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
- Use a feature branch when practical; a PR is optional history for solo
  development.
- Perform a local review when an independent reviewer is available; record the
  review when one is performed.
- Known critical or high findings block merging. Medium and low findings may
  be deferred unless they threaten data integrity, privacy, authorization, or
  financial correctness.
- Run relevant focused local contract and integration validation; a complete
  repository regression is not automatic.
- A local review is required when an independent reviewer is available; no
  hosted CI or workflow run is required.

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

## Autonomous completion mode

Autonomous completion mode is the canonical default for authorized
implementation work. It governs Codex, Claude, tracker operations, local
validation, reviews, PR maintenance, merges, cleanup, and final reconciliation.

### Outcome-level authorization

An authorization applies to the requested outcome, not merely the initially
predicted file list or correction count. It includes reasonable subordinate
diagnosis, implementation corrections, focused tests, documentation, review
fixes, branch and PR maintenance, merge, cleanup, and final reconciliation
when they remain within the same objective, risk tier, and dependency radius.
A newly discovered implementation detail or edge case is not automatically
scope expansion.

### Default delivery behavior

Unless the user explicitly requests planning-only, audit-only, review-only,
draft-only, or stop-before-merge behavior, continue through:

`inspect → implement → focused validation → review → correction → revalidation → merge when permitted → cleanup → status/handoff reconciliation`

Do not stop merely to request another correction cycle, review pass, permission
to maintain the same PR, or permission to complete an already-authorized
merge.

Use one branch and one cohesive PR per outcome when a PR is warranted. Do not
create micro-PRs for intermediate corrections or tracker-only evidence. Update
the tracker and handoff only at meaningful milestones: start, material blocker,
merge/completion, or safe resource stop.

### Automatic decision and review rule

When several safe implementations satisfy the authorized outcome, choose the
least destructive and most reversible option that preserves financial authority,
privacy, ownership, provenance, and recoverability. Document the choice in the
final report instead of asking the user.

Valid critical/high review findings must be corrected and freshly reviewed
automatically; no fixed correction-cycle cap applies. Medium/low findings may
be deferred under this policy unless they threaten a protected boundary.

### Testing during completion

During correction loops, run only directly affected focused tests and boundary
tests. Run full repository or browser certification only at a phase boundary,
release or tag, shared infrastructure change, demonstrated broad regression,
or explicit user request. Do not rerun unrelated green suites after
documentation-only or evidence-only commits. Never report skipped checks as
passed.

### Mandatory stop conditions

Stop only when continuation requires one of the following:

- Inventing an unknown financial fact or changing financial policy or authority
  not covered by the authorization.
- Accessing or mutating personal data without an explicit mutation envelope.
- Destructive restore, deletion, irreversible migration, or external production
  action.
- Acquiring or exposing credentials.
- Enabling external providers, email, scheduler, trading, brokerage, execution,
  or money movement without authorization.
- Expanding into another phase or a materially separate product objective.
- A failed backup, integrity, ownership, privacy, or recovery precondition.
- Persistent filesystem, network, authentication, quota, or tool failure after
  bounded retries.
- Insufficient remaining resources to finish the next atomic operation safely.

Ordinary bugs, failed focused tests, review findings, migration implementation
details, fixture corrections, and predictable edge cases are not
user-authority blockers.

### Personal-data mutation envelope

When the user explicitly authorizes a bounded personal-data operation, the
agent may perform all stated prerequisite backups, disposable-clone rehearsals,
additive migrations, validations, approved writes, restarts, and post-write
verification without asking again. The agent must stop if observed personal
state differs materially from the authorized assumptions.

### Safe resource stop and user control

If context, credits, time, or tool availability is nearly exhausted, finish or
roll back the current atomic operation, never stop between a mutation and its
verification, commit and push a coherent checkpoint when possible, leave the
worktree clean when practical, and update `CURRENT_HANDOFF.md` with exact
state, completed evidence, blocker, and one resume command or prompt. Never
claim completion.

Explicit user instructions always override autonomous completion mode. The user
may request a pause at any time. Autonomous completion does not authorize phase
advancement, materially different features, destructive operations, or broader
personal-data access.

## Merge policy

- Low: focused checks pass.
- Medium: focused checks pass and no known critical or high defect remains.
- High: focused boundary checks pass and local review reports no critical or
  high defect when an independent reviewer is available.
- Medium and low findings become follow-up debt rather than automatic blockers.
- Hosted CI is intentionally unavailable and is never a completion gate. Record
  local commands and results as structured validation evidence; historical
  hosted-CI evidence remains valid and unchanged.

## Local validation evidence

New material work records concrete local evidence with its commit SHA,
command or bounded suite name, result, timestamp, and environment where
material. Generic claims without a command or suite and commit are invalid.
Historical `ci_evidence` records remain accepted for provenance but are not
required for new work.

## Maintenance

This file is the single authoritative human-readable policy. Agent
instructions, tracker skills, tracker schema references, development
guidelines, pull-request templates, and CI workflows should reference this
policy and describe only their local enforcement details. Do not copy the full
policy into those files.
