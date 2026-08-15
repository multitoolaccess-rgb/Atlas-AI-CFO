# ADR-010: Authoritative Account Currency and Non-Destructive Local Recovery

- **Status:** Wave 2A implemented; Wave 2B/2C remain separately authorized
- **Date:** 2026-08-15
- **Audited baseline:** `2a25d3eba9d71e4132b332790a0536392d62288c`
- **Scope:** Personal-use readiness, authoritative account currency, SQLite backup/recovery, and activation prerequisites
- **Related:** ADR-006, ADR-008, `SCENARIO_LAB_CONTRACT.md`, `WAVE2_CURRENCY_BACKUP_RECOVERY_PLAN.md`, `RISK_REGISTER.md`

## Decision summary

Atlas will keep the current forecast and Scenario Lab contract USD-only and
fail closed unless every included active account has explicit, current,
server-owned currency evidence. User preference, locale, institution name,
account name, currency symbols, application defaults, and an account type are
never currency authority.

Wave 2 is split into three separately authorized slices:

1. **Wave 2A — Currency authority:** contract, evidence lifecycle, adapter
   gating, migration only if required, and focused tests.
2. **Wave 2B — Backup and recovery:** non-destructive SQLite backup/check,
   verified restore, migration checks, and synthetic destructive tests.
3. **Wave 2C — Personal activation acceptance:** a separately authorized,
   backed-up personal-database operation that inventories and explicitly
   confirms evidence before enabling local flags.

No slice enables a capability automatically. No slice changes projection
mathematics, rewrites immutable history, introduces multi-user tenancy, or
starts Phase 7.

## Current evidence

The baseline contains:

- `accounts.currency_code`, `currency_source`, `currency_observed_at`, and
  `currency_source_reference` in both service model copies;
- the additive `S7a1b2c3d4e5_add_account_currency_provenance` migration, with
  no historical backfill and SQLite/PostgreSQL guards;
- the additive `X7a1b2c3d4e5_add_account_currency_evidence` migration and
  mirrored `AccountCurrencyEvidence` models, with no historical backfill,
  owner checks, idempotency uniqueness, and database-level immutability;
- `GoalProjectionConfig` with explicit USD configuration and provenance;
- `services/finlynq/app/projection_state/provider.py`, which includes only
  active accounts and rejects missing, mixed, stale, malformed, or non-USD
  evidence;
- structured OFX currency extraction and statement-declared evidence in the
  upload path;
- a bounded `confirm_currency` helper that is dry-run by default and appends
  explicit operator evidence atomically, with correction/revocation support;
- immutable forecast/scenario snapshots that retain their recorded USD and
  provenance values.

The implementation baseline does **not** prove that a personal database has authoritative
currency for every active account. The database was not opened or inspected
for this plan. Therefore the exact row-level cause of the current Doctor
failure remains intentionally unobserved; the safe root cause is that the
repository cannot establish the complete current evidence set without an
explicitly authorized operator action. Wave 2A closes the repository-level lifecycle gap with append-only evidence
history, actor category, hashed source reference, idempotency, correction, and
revocation. It does not inspect or activate any personal database.

## Currency authority contract

### Supported representation

The current projection and Scenario Lab systems support only `USD`.
Evidence codes use uppercase three-letter ISO-style form `^[A-Z]{3}$`, while
activation requires exactly `USD`. The contract must keep the general code
validation separate from the current USD capability gate so future currency
support cannot silently broaden this phase.

### Accepted evidence categories

| Category | Acceptable only when | Current repository status |
| --- | --- | --- |
| `structured_provider` | A trusted provider payload explicitly reports an account ISO currency, with a bounded server-side reference and observation time. | No Plaid provider mapping currently proves this path. `plaid_id` alone is not evidence. |
| `structured_statement` | A structured statement format declares an ISO code; the parser preserves the declaration and provenance without inferring from symbols. | OFX has a structured declaration path. General CSV/PDF symbol/header parsing is not sufficient today. |
| `operator_confirmed` | A bounded local operator confirms one owned active account with explicit scope and confirmation; actor and event are auditable. | Implemented by the dry-run-first helper/CLI. |
| `correction` / `revocation` | New immutable events supersede or revoke the current event; neither mutates prior evidence. | Implemented in the Wave 2A lifecycle. |

Every accepted record requires the code, source category, UTC observation
time, bounded non-PII source reference, authenticated owner scope, actor type,
recorded-at time, and an evidence digest or stable provenance identity. Raw
statements, tokens, account numbers, balances, and provider payloads do not
enter the currency evidence contract.

### Authority rules

- Never infer USD from preference, locale, institution, account name, symbol,
  default, or account type.
- Missing, malformed, stale, conflicting, unsupported, or mixed currency is
  an unavailable/blocked state, never a best-effort USD result.
- Every active account included by projection must pass the same authority and
  freshness policy. Inactive accounts are excluded only by an explicit,
  documented lifecycle rule; an unknown lifecycle or duplicate active account
  must block rather than disappear.
- Closed or archived accounts must not be silently reactivated or backfilled.
  Their historical forecast/scenario records remain readable with their
  recorded currency and provenance.
- Duplicate active rows, ambiguous provider identity, or an account that cannot
  be mapped to a stable source identity must block the projection set until
  reconciled.
- A browser may request a readiness view but may not supply or sign currency
  evidence.

### Evidence correction and revocationThe current four account columns remain a compatibility projection cache;
authority is derived from the additive `account_currency_evidence` table. It
contains an owned account link, evidence UUID, code, source category, source
reference hash, observed/recorded timestamps, actor category, event type,
superseded event link, idempotency hash, and bounded reason code. Database
triggers/constraints reject ownership violations and update/delete mutation.


A correction appends a new event and changes only current account authority.
A revocation appends a `revoked`/`reconciled` event and makes current currency
unknown until replacement evidence is accepted. Neither operation edits an
immutable forecast or scenario version. New forecast/scenario generation is
blocked while current authority is unknown; historical reads remain intact.

The operation must be authenticated, owner-scoped, bounded in account count,
idempotent, explicitly confirmed, and observable through sanitized event
metadata. Raw evidence and personal identifiers are excluded from logs and
API responses.

## Projection and activation gates

The Finlynq projection provider remains the only source-state boundary. It
must verify, in order:

1. authenticated owner and goal;
2. migration/storage readiness;
3. active-account lifecycle and duplicate/identity checks;
4. complete current currency evidence and freshness;
5. explicit USD projection configuration and freshness; and
6. supported account types and Decimal-safe balance conversion.

Forecast persistence/read APIs, decision history, and Scenario Lab remain
server-owned and default-off. Currency readiness is necessary but not
sufficient: immutable baseline, retention acknowledgement, migration head,
ownership, and synthetic acceptance gates remain required. Existing snapshots
are never recalculated merely because current account evidence changes.

Stable recovery categories include `currency_unknown`, `currency_mixed`,
`currency_conflict`, `currency_stale`, `currency_unsupported`,
`currency_revoked`, and `currency_evidence_incomplete`, alongside
`projection_baseline_unavailable` and `migration_state_unavailable`.
Messages must remain sanitized and actionable.

## Storage and recovery decision

Rules Service owns the Alembic graph. The current repository reports one
Rules head, `X7a1b2c3d4e5`; Finlynq mirrors the SQLAlchemy models and does not
own a second migration graph. In the documented `start.sh` lifecycle,
`DATABASE_URL` is set to the Rules Service SQLite file and both services share
that database. A standalone Finlynq process can otherwise resolve its default
relative SQLite file separately; the future tool must require an explicit
Atlas-owned database identity and must never guess between these modes.

SQLite connections set `busy_timeout=30000` and `journal_mode=WAL`. A plain
copy of only the main database file is not supported because committed state
may involve `-wal`/`-shm` siblings. The supported Wave 2B design is the Python
standard-library `sqlite3.Connection.backup` API, producing a standalone
backup database while preserving a consistent SQLite snapshot. The command
must refuse ambiguous paths, verify no Atlas-owned writers are active for the
operator-approved backup lifecycle, run integrity checks, write a restrictive
manifest, and never upload or overwrite an existing backup.

Restore requires all Atlas-owned services stopped and verified absent from the
resolved database path. It verifies the manifest and checksum, creates a
pre-restore safety backup, restores to a temporary file in the same directory,
checks integrity and schema compatibility, then atomically replaces the target
while preserving the old database and sidecars as a recovery artifact. It
starts no service automatically. Any migration downgrade that would remove
immutable records is refused.

## Security and privacy

The Doctor, readiness API, backup manifest, and recovery logs may expose only
safe metadata: service/database identifier, schema revision, Git SHA, state,
counts of checks, timestamps, checksums, and bounded reason codes. They must
not expose database paths beyond the minimum recovery label, connection
strings, credentials, tokens, account IDs, balances, transactions, holdings,
forecast/scenario snapshots, or provider payloads.

The following actions require explicit user authorization and are not implied
by this ADR: reading personal account identifiers; listing accounts requiring
currency confirmation; applying or revoking currency evidence; backing up or
restoring the personal database; running migrations against it; enabling any
forecast/history/scenario flag; or starting an enabled live-stack acceptance.
Synthetic planning and tests use only disposable databases and need no personal
permission.

## Goal Float disposition

`Goal.target_amount` remains a known high-risk legacy Float boundary. ADR-006
already converts it with `Decimal(str(value))` and records that precision is
not restored. It is not changed in Wave 2 planning. A canonical Goal Decimal
migration should be a separate high-risk prerequisite before Wave 2C if
operator acceptance would make target precision part of a real personal
activation decision. Wave 2A/2B may proceed without it only while activation
continues to disclose the limitation and refuses to claim restored precision.

## Consequences and non-goals

Positive consequences:

- Unknown currency remains visibly and safely blocked.
- Current evidence can eventually be corrected without rewriting history.
- Backups become verifiable, local-only, WAL-safe recovery artifacts.
- Personal activation has explicit authorization and rollback boundaries.

Non-goals:

- No backup/restore, activation, personal database access, or Wave 2C
  operation in this Wave 2A task.
- No currency conversion, multi-currency projection, tax, probability,
  optimization, execution, brokerage, money movement, email, scheduler, LLM,
  tenancy, retention/deletion policy, or Phase 7 work.

## Implementation gate

Wave 2A is implemented only through the evidence model, migration, trusted
Finlynq gating, structured statement mapping, operator helper, readiness
aggregation, and focused synthetic tests. It did not access personal data,
change financial mathematics, enable flags, or implement backup/restore.
Wave 2B and Wave 2C each still require separate authorization and bounded
validation records. No implementation of those slices may be inferred from
this document.
