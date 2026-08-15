# Phase 4 Decision Journal Plan

## Authority and boundary

Phase 4 starts only after the certified Phase 3 recommendation contract.  Its
single exit criterion is the Phase Plan criterion:

> Decisions, alternatives, outcomes, permissions, audit history, and recovery
> are tested.

This plan is limited to the personal, single-user Rules Service and its
existing `/goals` surface.  It does not add household tenancy, advisors,
external execution, account credentials, retention/deletion policy, or a
currency authority beyond the existing fail-closed USD contract.

## Reused substrate

Phase 2 already provides immutable, owner-scoped `recommendations` and
`decision_journal_entries`, deterministic identifiers, hashed idempotency
keys, SQLite/PostgreSQL mutation and ownership guards, and an authenticated
accept/reject/defer write route.  Phase 3 adds immutable outcome evaluations
for accepted decisions and an owner-scoped recommendation contract linking
goal, forecast provenance, risks, confidence, approvals, and evaluation
summaries.  Its evidence reference remains an opaque, server-derived SHA-256
digest; no new work may accept, persist, log, or reveal a raw evidence
location.

The Phase 2 goals page already has a feature-gated forecast/recommendation
journey with accessible decision controls.  Phase 4 must extend that journey,
not the legacy mutable recommendation queue.

## Gap analysis

The existing ledger records the selected action but has no bounded record of
the alternatives considered, decision rationale, or correction/supersession
relationship.  It has immutable decision and outcome rows, but no unified
owner-scoped decision-history read API or append-only audit event stream that
ties these records together.  The UI only confirms a just-recorded decision;
it cannot show a user their decision history, alternatives, linked outcome
state, or a safe correction path.

## Slice 1 — decision-history substrate (high risk)

Add one additive migration and immutable, user- and goal-scoped decision
history/audit records.  A decision-history record will link exactly one
existing recommendation and decision journal entry, capture a bounded
alternative set (including `do_nothing`) and rationale, and identify an
append-only correction as a new superseding record rather than an update or
delete.  An append-only audit event records only bounded action, actor scope,
target references, timestamp, correlation/idempotency digest, policy result,
and outcome reference.

Expose strict authenticated write/read routes behind a new server-side,
default-off rollout flag.  Every read and write must authorize the goal and
all linked parents before revealing existence.  Requests forbid unknown
fields; values have bounded enums and lengths; raw idempotency keys and raw
evidence references never cross persistence, logs, validation, or response
boundaries.  The history read envelope may reuse Phase 3 lifecycle summaries
and opaque evidence hashes, but never raw outcome payloads or evidence
locations.  Recovery is limited to recording a linked correction with a
reason; acceptance is never execution or proof of a successful outcome.

Focused tests precede implementation and cover idempotency/replay and conflict,
authorization indistinguishability, append-only and ownership database guards,
correction linkage, hash-only exclusions, default-off behavior, bounded API
validation, outcome linkage, SQLite migration round-trip, and PostgreSQL
parity where the repository suite supports it.  The slice uses one branch and
one PR with fresh independent review.

## Slice 2 — decision-history UI and journey (high risk)

Integrate the owner-scoped history API into the existing goals recommendation
surface.  Provide a compact, chronological decision history with chosen
action, alternatives/rationale disclosure, correction relationship, approval
state, and outcome lifecycle.  The UI must clearly say that a recorded
decision is not execution and that a measured outcome is not proof of
causation.  It must render only the safe contract fields and never infer,
display, or reconstruct raw evidence locations.

Add typed API-client coverage, component accessibility tests (semantic
headings, keyboard operation, focus, live/error states, reduced motion, and
axe), and one mocked end-to-end journey for record → view → correction →
linked outcome state.  Disabled, missing, and cross-owner-equivalent responses
remain indistinguishable and safe.  This slice also uses one branch, one PR, relevant focused CI, and a fresh
independent review under the canonical policy.

## Certification evidence

On clean `main` after both slices, certify the exit criterion with the focused
and relevant regression suites, migration/dialect evidence, UI/a11y/e2e
evidence, final independent review, tracker rendering, deterministic-render
validation, and handoff validation.  Existing retention/deletion and currency
authority risks remain open; they block external multi-user rollout but not
this bounded single-user phase.
