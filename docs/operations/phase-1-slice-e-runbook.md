# Phase 1 Slice E.3 — Runbook

> Status: dry-run only. External multi-user production enablement
> remains **BLOCKED** pending Phase 1 retention / user-deletion
> policy approval.

## Overview

The slice E.3 shadow-validation CLI is the **only** sanctioned
operator entry point for ad-hoc shadow validation of the
`CanonicalProjectionState` pipeline. It:

1. Loads a deterministic synthetic `CanonicalProjectionState` via the
   SAME pydantic validation surface (`CanonicalProjectionState.model_validate`)
   that the trusted adapter uses in production.
2. Computes the canonical-state SHA-256 digest (`hash_input_state`).
3. Emits a sanitized comparison envelope to **stdout** as JSON.
4. Records the lifecycle event via `app.forecasts.observability.record_event`
   so the bounded sanitization runs on every payload.

It **never** instantiates `ForecastRepository` and **never** writes to
the immutable forecast repository. There is nothing to roll back if
the operator invocation is mistargeted — the CLI is read-only against
the canonical-state validation surface.

## Operator invocation

The **only** approved invocation is:

```bash
python -m app.forecasts.shadow_validate \
    --user-id <id> --goal-id <id> --limit 1 --dry-run
```

Where:

- `--user-id`: a single bounded user_id (positive integer).
- `--goal-id`: a single bounded goal_id (positive integer).
- `--limit`: structural invariant — **must equal exactly 1**.
- `--dry-run`: required marker; the CLI always runs in dry-run mode.

Concrete (synthetic) example used in CI / staging:

```bash
python -m app.forecasts.shadow_validate \
    --user-id 1 --goal-id 2 --limit 1 --dry-run
```

## Expected output

A successful invocation writes a deterministic, sanitized comparison
envelope to **stdout**. Example:

```json
{"canonical_state_digest":"<64-char-sha256-lowercase-hex>","dry_run":true,"limit":1,"sanitized_state_view":{"currency":"USD","reconciliation_state":"reconciled","schema_version":"atlas-projection-state/v1"},"schema_version":"atlas-projection-state/v1"}
```

This envelope:

1. ONLY contains the four top-level keys + the bounded `sanitized_state_view`.
2. Has no financial values, no PII, no balance snapshots, no
   contributions, no targets, no provenance, no tokens, no idempotency keys.
3. The `canonical_state_digest` is the SHA-256 of the canonical JSON
   v1 envelope of the synthetic state; it can be diffed against
   previous runs to detect canonicalization drift.

## Safe failure handling

The CLI exits with bounded, sanitized envelopes on every failure
mode:

| Mode                              | Exit code | Stderr envelope                                                         |
|-----------------------------------|-----------|--------------------------------------------------------------------------|
| ``--limit`` is not exactly 1      | 2         | `{"code":"shadow_validation_parser_error","detail":"..."}`               |
| ``--user-id`` or ``--goal-id`` invalid | 2    | `{"code":"shadow_validation_parser_error","detail":"..."}`               |
| Adapter scope mismatch            | 1         | `{"code":"shadow_validation_failed","detail":"shadow_user_scope_mismatch"}` |
| Unhandled exception               | 2         | `{"code":"shadow_validation_unhandled_exception","detail":"<ExceptionType>"}` |

**What to do if exit code != 0:**

1. Read the sanitized `code` + `detail` from stderr.
2. Re-run with the SAME operator invocation (dry-run is idempotent).
3. If the failure persists, capture the sanitized envelope (do NOT
   unpack raw canonical-state values) and escalate to the
   Phase 1 retention / user-deletion policy owner.

## Safe failure: NEVER log or echo

- Raw canonical-state values.
- Raw projection snapshots.
- Raw snapshot JSON from the immutable forecast repository.
- Raw idempotency keys or their SHA-256 hashes.
- Raw Finlynq authorization headers.

The shadow CLI never has access to any of these because it does not
talk to a production trusted adapter or to the immutable forecast
repository. If you see any of these values echo'd, that is a
**BLOCKING bug** and MUST be reported immediately per the Phase 1
incident-response procedure.

## Rollback

**Nothing to roll back.** The shadow CLI is read-only against the
canonical-state pipeline. It does NOT mutate any persistent state, does
NOT create any version, does NOT log raw financial state. Operators are
free to invoke the CLI as many times as necessary without concern.

## Rollout (BLOCKED pending retention + user-deletion policy)

The shared CLI is operated **only from single-operator dev / staging
contexts** until the Phase 1 retention + user-deletion policy is
approved.  Concretely:

1. Production multi-user invocation: **NOT AUTHORIZED** in Phase 1.
2. CI invocation: **AUTHORIZED** (pytest-driven, ephemeral).
3. Local operator invocation: **AUTHORIZED** (synthetic state, digests only).

If retention + user-deletion policy approval arrives in a later slice,
the rollout checklist is:

1. Replace the in-memory `_ShadowTrustedAdapter` stub with the real
   `HttpFinlynqProjectionStateAdapter` against an isolated HTTP fixture.
2. Add a CI integration test that proves the real adapter wiring is
   correct against known canonical envelopes.
3. Add CSO + privacy review for the broader operator surface.
4. Update this runbook to document the prod-mode invocation pattern.

Until then: **do not** wire the shadow CLI to a production-trusted
adapter or pass real user IDs beyond the synthetic 1 / 2 ranges.
