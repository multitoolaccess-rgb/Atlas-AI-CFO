# Wave 2 Plan: Authoritative Currency and Non-Destructive Local Recovery

- **Plan date:** 2026-08-15
- **Planning baseline:** `2a25d3eba9d71e4132b332790a0536392d62288c`
- **Phase:** Remediation after certified Phase 6; Phase 7 is not started
- **Status:** Wave 2A and Wave 2B implemented; Wave 2C authorized and partially executed but blocked at final local activation/readiness acceptance
- **Related:** [ADR-010](../adr/ADR-010-ACCOUNT-CURRENCY-AND-LOCAL-RECOVERY.md), [ADR-006](../adr/ADR-006-IMMUTABLE-FORECAST-PERSISTENCE.md), [Scenario Lab Contract](../07-engineering/SCENARIO_LAB_CONTRACT.md), [Remediation Backlog](./REMEDIATION_BACKLOG.md), [Risk Register](./RISK_REGISTER.md), [Personal Mode Proposal](../07-engineering/PERSONAL_MODE_PROPOSAL.md)

## 1. Executive decision

Wave 2 is a high-risk financial/data-integrity remediation even though this
turn changes documentation only. The repository already contains a nullable
account-currency provenance schema and a fail-closed projection adapter. Wave
2A now supplies the missing repository-level operational authority lifecycle;
current personal-account evidence, safe local backup, and recovery
compatibility remain unproven and out of scope.

Do not backfill existing rows, infer USD, inspect the personal database, enable
flags, or run migrations as part of this plan. Execute only the separately
authorized slice whose prompt names the exact scope.

### Three-slice order

| Slice | Purpose | Scope | Must precede |
| --- | --- | --- | --- |
| **2A** | Authoritative currency | Evidence contract/lifecycle, adapter gate, provider/statement mapping, bounded operator confirmation, Doctor/readiness integration, focused tests, migration only if required | 2C and any enabled financial acceptance |
| **2B** | Local recovery | WAL-safe backup/check/restore, manifest, writer ownership, pre-restore safety copy, migration/integrity verification, synthetic destructive tests, runbook | 2C personal activation |
| **2C** | Personal acceptance | Explicit personal authorization, backup first, read-only inventory, evidence confirmation, flag enablement, restart journey, rollback | No later work is implied |

2A and 2B may be developed independently after this plan, but 2C depends on
both. No slice includes Phase 7.

## 2. Current-state evidence

### Currency and financial authority

Confirmed from repository inspection at the planning baseline:

- `services/finlynq/app/models/account.py` and the Rules Service model copy have
  nullable `currency_code`, `currency_source`, `currency_observed_at`, and
  `currency_source_reference` fields.
- Migration `S7a1b2c3d4e5_add_account_currency_provenance.py` adds those fields
  and `goal_projection_configs`, rejects partial/invalid provenance on SQLite
  and PostgreSQL, and refuses downgrade when currency/configuration data exists.
- The migration deliberately performs no historical backfill.
- `GoalProjectionConfig` is server-owned, USD-only, freshness-bound, and
  provenance-bound.
- Finlynq `build_projection_state` considers active accounts only and rejects
  missing evidence, non-USD evidence, unsupported account types, stale/future
  observations, missing contribution configuration, and missing accounts.
- The provider converts legacy Float balances with `Decimal(str(value))` but
  records that precision was not restored.
- OFX has a structured declared-currency reader. The general CSV/PDF parser
  strips symbols for amount parsing and does not, by itself, establish an ISO
  currency declaration. A `$`/`£`/`€` symbol is not evidence.
- `plaid_id` and the `plaid` account-source label exist, but there is no current
  trusted Plaid response adapter that maps an explicit account currency into
  the projection evidence contract. Plaid can be considered usable only after
  such a mapping, provenance, replay, and privacy contract exists; it is not
  usable as authority merely because a Plaid identifier exists.
- Wave 2A adds `account_currency_evidence` as an append-only event table,
  mirrored service models, deterministic effective-state derivation, and
  database immutability/owner guards. `confirm_currency` remains bounded and
  dry-run by default while now appending explicit operator assertions with
  idempotency; correction and revocation are represented as new events.
- Existing forecasts and scenarios store USD and their own source/baseline
  provenance. Current-account evidence changes must not edit those rows.

**Root cause of current unavailable currency authority:** the repository
cannot prove that every current active account in the personal database has
complete, fresh, authoritative USD evidence without an explicitly authorized
personal-data inspection. Wave 2A does not inspect that database; the Doctor
must therefore remain blocked until Wave 2C authorization and evidence review.
The exact account-level defect (missing, stale, mixed, ambiguous, or
migration-unavailable) remains intentionally undetermined.

### Database and migration ownership

| Database mode | Resolution | Owner | Evidence/status |
| --- | --- | --- | --- |
| Documented shared local stack | `start.sh` exports `DATABASE_URL=sqlite:///$RULES_SERVICE/finance.db` to both services | Rules Service Alembic; Finlynq shares the engine URL | Current supported local lifecycle; WAL enabled by both SQLAlchemy engines |
| Standalone Finlynq fallback | Finlynq default `sqlite:///./finance.db`, relative to its process working directory | No separate Finlynq Alembic graph | Must not be confused with the shared stack; future tools require explicit database identity |
| Rules default outside `start.sh` | Rules config default is PostgreSQL `wealthiq` URL | Rules Service Alembic | Design target, not a personal-data operation in this plan |
| Hermetic tests | Per-process temporary SQLite files under `/tmp` | Test harness | Disposable synthetic data only |
| E2E harness | Temporary `atlas-ai-cfo-e2e-*.db` with explicit migrations | Rules Service Alembic/test runner | Disposable and deleted by runner cleanup |

The repository has one Rules Alembic head, `X7a1b2c3d4e5` after Wave 2A.
Finlynq mirrors
models and does not own migration execution. `start.sh` intentionally does not
run migrations; the operator or an isolated harness must perform the approved
migration step. A future backup/restore tool must resolve the configured Atlas
owned database explicitly and must never search arbitrary filesystem locations.

### WAL and recovery evidence

Both service database shims set `PRAGMA journal_mode=WAL` and a 30-second busy
timeout. Existing comments explicitly warn that copying only `finance.db` is
inconsistent while `-wal`/`-shm` contain committed state. No supported Atlas
backup or restore command currently exists. No personal database backup,
restore, or restart acceptance was run for this plan.

## 3. Currency authority contract

### Evidence record

The implementation target for 2A is an append-only evidence lifecycle around
the existing current-account fields. A likely additive record is:

| Field | Contract |
| --- | --- |
| `id` | Lowercase UUID, immutable |
| `account_id`, `user_id` | Required owner-scoped foreign keys; account owner must match |
| `currency_code` | Uppercase three-letter code; 2A activation accepts only `USD` |
| `source_kind` | `provider_reported`, `statement_declared`, or `user_confirmed` |
| `source_reference` | Bounded stable non-PII reference or server-side digest |
| `observed_at` | UTC evidence timestamp, not client-supplied |
| `recorded_at` | Server UTC timestamp |
| `actor_type` | `provider`, `authenticated_operator`, or `system_ingest` |
| `state` | `active`, `superseded`, `revoked`, or `conflicted` |
| `supersedes_id` | Nullable immutable predecessor link |
| `reason_code` | Bounded stable reconciliation reason |
| `evidence_hash` | Server-derived digest over safe normalized metadata |

The existing four account columns can remain a current projection cache or be
replaced by a current-evidence pointer only in an approved migration. The
append-only record is authoritative for auditability; cache updates happen in
the same transaction and never rewrite historical forecast/scenario rows.

### Decision table

| Situation | Current projection state | New forecast/scenario generation | Recovery |
| --- | --- | --- | --- |
| Every included active account has fresh explicit USD evidence | Ready | Allowed only if all independent flags/gates pass | None |
| One active account has no evidence | Blocked | Refused | Identify account through an authorized operator inventory; obtain evidence |
| Evidence is malformed or partially populated | Blocked | Refused | Repair through a bounded evidence workflow; never patch one field |
| Any active account is non-USD | Unsupported/blocked | Refused for USD-only contract | Preserve evidence; future multi-currency work requires a new ADR |
| Active accounts disagree on currency | Mixed/blocked | Refused | Reconcile identity/evidence; no conversion or averaging |
| Evidence is older than the configured freshness bound | Stale/blocked | Refused | Re-ingest or explicitly reconfirm through approved source |
| Two active rows may represent one source account | Ambiguous/blocked | Refused | Reconcile source identity; do not deduplicate silently |
| Evidence is revoked or superseded without replacement | Unknown/blocked | Refused | Keep history; accept replacement evidence explicitly |
| Account inactive/closed under a documented lifecycle rule | Excluded from current projection | No new inclusion | Preserve historical records; do not infer or reactivate |
| Historical forecast/scenario has prior valid USD evidence | Historical record remains readable | No rewrite | Display recorded snapshot currency/provenance |

### Authority flow

```text
provider or structured statement
  -> trusted Finlynq ingestion boundary
  -> normalized bounded evidence (no raw payload)
  -> owner/account identity validation
  -> append-only evidence event
  -> current-account authority pointer/cache
  -> freshness + all-active-account + USD gate
  -> Finlynq atlas-projection-state/v1
  -> Rules Service Decimal forecast/scenario authority
  -> immutable snapshot with original currency/provenance
```

An operator confirmation enters at the evidence-event step and must not be a
browser preference or ordinary account-edit field.

## 4. Wave 2A implementation plan

### Schema and migration decision

The current schema is sufficient for a first fail-closed read, but not for
full correction/revocation auditability. The focused Wave 2A implementation
audit confirmed that an additive migration was required and added it:

- Add an append-only `account_currency_evidence` table as described above.
- Add owner/account indexes and a uniqueness/idempotency key for one evidence
  intent.
- Add SQLite triggers and PostgreSQL constraints/functions for owner
  consistency, code/source/reference format, immutable event rows, and
  bounded state transitions.
- Preserve nullable current fields for legacy rows; no backfill and no default
  USD.
- Add a current evidence pointer or transactionally synchronized cache only if
  it can be proven consistent with the event table.
- Preserve historical forecast/scenario currency and provenance unchanged.
- Make downgrade refuse while evidence events exist, just as immutable
  forecast/scenario migrations refuse to remove history.
- Test an upgrade from the current head and clean downgrade/re-upgrade on an
  empty synthetic database, plus downgrade refusal with evidence/history.
- Exercise SQLite and PostgreSQL constraint/parity tests where a PostgreSQL
  sidecar is available; do not claim PostgreSQL evidence when unavailable.

No existing append-only currency mechanism was found; the new evidence table
is therefore not redundant. The implementation and migration evidence are
recorded in ADR-010 and the Wave 2A implementation record above.

### Ingestion and operator confirmation

1. Map only explicit provider ISO currency fields to `provider_reported`.
2. Preserve only structured statement declarations for
   `statement_declared`; reject symbol-only or locale-only inputs.
3. Keep Plaid disabled as an authority until a real payload fixture and
   server-owned mapping exist; use synthetic provider payloads only in tests.
4. Replace or wrap `confirm_currency` with an authenticated, owner-scoped,
   dry-run-first command/API that produces an inventory, requires explicit
   account scope, accepts bounded batches, is idempotent, and records actor
   type/reason/evidence digest without raw account data.
5. Add correction and revocation as append-only events. Never silently change
   an established code or provenance tuple.
6. Ensure an all-or-nothing batch: a conflict or cross-owner account makes the
   entire apply fail without partial evidence.
7. Add sanitized reason codes and Doctor/readiness summaries that report only
   counts/state, not account identifiers or financial values.

### Adapter and readiness integration

- Keep the projection provider as the sole Rules-to-Finlynq boundary.
- Make current evidence selection deterministic by account identity and
  evidence state.
- Preserve seven-day freshness unless a separately reviewed contract changes
  it.
- Ensure inactive-account policy and duplicate-source identity checks are
  explicit and tested.
- Keep forecast/read/history/scenario flags server-owned and default-off.
- Add readiness fields for evidence completeness, stale/conflict/mixed state,
  migration compatibility, and required recovery action.
- Do not allow client-provided currency, evidence timestamp, source reference,
  account inclusion, or owner IDs.

### Wave 2A test matrix

- Model parity between Rules Service and Finlynq.
- Migration upgrade, no-backfill, guard, downgrade refusal, and re-upgrade.
- Evidence code/source/reference/timestamp validation.
- Provider, statement, and synthetic operator evidence provenance.
- Unknown, stale, mixed, non-USD, malformed, revoked, superseded, and
  conflicting evidence fail closed.
- Active/inactive/closed/duplicate/ambiguous account treatment.
- Cross-owner and unauthorized reads/writes return sanitized auth behavior.
- Idempotent repeated confirmation does not duplicate events.
- Correction never edits a forecast/scenario version.
- Forecast and Scenario Lab gates remain off or blocked until every required
  dependency passes.
- Doctor/readiness never leaks secrets, paths, account identifiers, balances,
  raw provider payloads, or immutable snapshots.
- SQLite/PostgreSQL parity for constraints and timestamps where available.

## Wave 2A implementation record

- Migration: `X7a1b2c3d4e5_add_account_currency_evidence.py` is additive,
  creates no evidence rows, and refuses downgrade while evidence history
  exists.
- Authority: only `structured_provider`, `structured_statement`, and
  `operator_confirmed` assertions are accepted; `correction` and `revocation`
  are explicit immutable event types.
- Gating: active accounts are evaluated from event history, with stable
  `currency_unknown`, `currency_mixed`, `currency_conflict`, `currency_stale`,
  `currency_unsupported`, `currency_revoked`, and
  `currency_evidence_incomplete` failures. Legacy account currency columns
  cannot authorize projection state.
- Privacy: only a SHA-256 source-reference digest enters the evidence table;
  the compatibility cache receives an opaque event reference. No raw
  statement/provider payload, credential, balance, or account number is used.
- Deferred: no Plaid authority mapping, personal database inspection, flag
  enablement, backup/restore, or restart acceptance was performed.

## 5. Wave 2B implementation plan: backup and recovery

### Proposed command set

The implemented bounded interface is:

```bash
python3 scripts/atlas_backup.py --database rules-finlynq-shared --output /absolute/new-backup-directory
python3 scripts/atlas_backup.py --check /absolute/backup-directory
python3 scripts/atlas_restore.py --check /absolute/backup-directory
python3 scripts/atlas_restore.py --database rules-finlynq-shared --to /absolute/new-database.sqlite /absolute/backup-directory
```

In-place restore is intentionally unsupported. The tools never start services,
run migrations implicitly, or overwrite an existing destination.

The real restore command must require an explicit confirmation token/flag in a
non-interactive environment. Neither command may upload, auto-start services,
change feature flags, run migrations implicitly, or touch an unrecognized path.

### Backup format

Use a directory or archive selected by the operator, with no silent overwrite:

```text
atlas-backup-<database-id>-<timestamp>/
  database.sqlite
  manifest.json
```

The SQLite online backup API is the preferred mechanism. It creates a
consistent destination database without relying on unsafe main-file copying
and does not require mutating the source with a WAL checkpoint. The tool still
requires the documented Atlas writer lifecycle to be quiescent so the backup
represents a stable application state across the shared Rules/Finlynq boundary.

`manifest.json` contains only:

- format version;
- creation timestamp;
- Atlas Git SHA;
- database/service identifier;
- source dialect and safe mode label;
- schema current revision and repository head;
- SQLite `integrity_check`/`quick_check` result;
- database byte size;
- SHA-256 of the backup database;
- tool version and runtime identifier; and
- recovery instructions.

The manifest contains no connection string, absolute personal path, account
identifier, financial value, credentials, logs, cache, `.env`, virtualenv,
provider payload, WAL/SHM contents, or unrelated repository files. The output
root and files use restrictive local permissions. A backup is self-contained;
source `-wal`/`-shm` files are not copied into the backup directory.

### Backup preconditions and verification

1. Resolve an explicit supported database identity from operator input.
2. Verify the path is an Atlas-owned SQLite database and not a symlink or
   unrelated file.
3. Verify Rules/Finlynq writers are stopped or that the approved quiescent
   read-only lifecycle is active; never kill unrelated processes.
4. Inspect only safe SQLite metadata: journal mode, schema revision, and
   integrity status.
5. Run `sqlite3.Connection.backup` into a new destination opened with exclusive
   creation semantics.
6. Run integrity checks on the destination and calculate SHA-256.
7. Write and fsync the manifest, then set restrictive permissions.
8. Re-run `--check` and report a bounded recovery instruction.

A failed check leaves the source untouched and removes only the newly created
incomplete output owned by that invocation.

### Restore state machine

```text
DISCOVERED
  -> manifest verified
  -> destination and source ownership verified
  -> services STOPPED_CONFIRMED
  -> pre-restore safety backup created
  -> restored to same-directory temporary file
  -> checksum + SQLite integrity passed
  -> migration current/head compatible
  -> atomic replace committed
  -> post-restore checks passed
  -> RESTORED_READY_FOR_OPERATOR_START
```

Any failure before atomic replace leaves the current database untouched. Any
failure after replacement preserves the failed/current database and manifest
under an explicit recovery artifact; it is never deleted to make an older
schema appear valid.

Restore requirements:

- refuse active Atlas writers and unrelated database paths;
- verify format, manifest, checksum, supported tool version, dialect, and
  expected database identity;
- create a pre-restore safety backup without overwriting existing backups;
- restore into a temporary file in the same filesystem and atomically replace
  only after validation;
- stop and preserve target `-wal`/`-shm` sidecars as safety artifacts rather
  than mixing them with the restored standalone database;
- run `PRAGMA integrity_check` and `quick_check` after replacement;
- verify Alembic current revision equals a supported repository head, without
  running upgrade/downgrade implicitly;
- do not start services automatically; and
- provide exact manual rollback: stop services, preserve the failed target,
  restore the pre-restore safety backup through the same checked flow.

### Retention

Local backup retention is an operator-managed local storage concern, not the
unresolved external multi-user retention/deletion policy. The tool must never
silently delete older backups. Future cleanup may require an explicit operator
selection, age/count policy, manifest verification, and a confirmation step.
Backups containing immutable history must be treated as sensitive local data.

### Wave 2B test matrix

Use only disposable synthetic databases and temporary directories:

- backup with WAL active and with a clean checkpoint;
- backup integrity and checksum verification;
- refusal of overwrite, symlink, ambiguous destination, missing manifest,
  checksum mismatch, unsupported format, wrong database identity, and active
  writer;
- manifest redaction and restrictive permissions;
- restore dry-run with no mutation;
- restore creates pre-restore safety backup;
- atomic restore success and rollback after integrity/schema failure;
- database/WAL/SHM sidecar handling;
- migration current/head mismatch and downgrade refusal with immutable rows;
- concurrent writer refusal/ownership checks; and
- source unchanged after backup/check and no automatic process startup.

## 6. Wave 2C implementation plan: personal activation acceptance

This slice requires a new explicit authorization prompt and must never be
started automatically after 2A or 2B.

Required order:

1. Confirm exact personal database path and database identity with the
   operator; do not derive it from a default.
2. Stop Atlas services and create/verify a Wave 2B backup.
3. Run a read-only inventory of active accounts lacking or conflicting
   currency authority. Do not print account identifiers in logs.
4. Obtain explicit per-account or bounded-batch evidence confirmation. No
   blanket USD backfill.
5. Verify migration current/head and Doctor/readiness; keep flags off on any
   failure.
6. Apply only explicitly authorized evidence events through the audited 2A
   path.
7. Explicitly enable only the approved local forecast/read/history/scenario
   flags; keep email, scheduler, LLM, external delivery, execution, trading,
   brokerage, and money movement disabled.
8. Restart the full stack using the documented lifecycle and safe port
   ownership.
9. Prove forecast → recommendation → decision → history/outcome → Scenario
   Lab, including reload persistence and server-authoritative errors.
10. If any gate fails, disable flags, stop services, preserve the database and
    logs safely, and report the exact blocked state. Do not delete or downgrade
    immutable history.

## 7. Trust boundaries and failure modes

| Boundary/failure | Required behavior |
| --- | --- |
| Browser → currency authority | Browser cannot submit authority; return sanitized authenticated response |
| Provider → Finlynq | Accept only explicit ISO evidence; preserve source and timestamp |
| Statement parser → Finlynq | Symbols and locale are not authority; structured declaration only |
| Finlynq → Rules | Typed projection envelope; mixed/unknown/stale state rejected |
| Current evidence → historical snapshots | New evidence never rewrites forecast/scenario rows |
| SQLite source → backup | Online backup API; source unchanged; integrity/checksum manifest |
| Backup → restore | Manifest/checksum/dialect/schema verified before atomic replace |
| Service lifecycle → database | Active writer refusal; no unrelated process termination |
| Migration version → immutable history | Downgrade refusal when data would be removed |
| Operator error → recovery | Preserve current/failed database and pre-restore backup; give bounded next action |
| Personal data → repository | Never commit database, WAL/SHM, credentials, manifests with sensitive paths, or logs |

## 8. File-by-file implementation map

### 2A likely files

- `services/finlynq/app/models/account.py` and Rules model mirror — parity only;
- `services/finlynq/app/projection_state/currency.py` and
  `confirm_currency.py` — evidence lifecycle and operator boundary;
- `services/finlynq/app/projection_state/provider.py` — deterministic gate;
- `services/finlynq/app/routes/parse.py` and provider adapters — explicit
  declaration mapping only;
- `services/rules-service/app/readiness.py` and readiness schemas — sanitized
  state;
- a new Rules Alembic revision only if the append-only evidence design is
  confirmed necessary;
- focused Finlynq/Rules migration, provider, auth, and parity tests;
- ADR and contract documentation.

### 2B likely files

- new `scripts/atlas_backup.py` and `scripts/atlas_restore.py`;
- lifecycle/operations docs and possibly small safe helpers for ownership;
- synthetic backup/restore tests and shell syntax tests;
- no personal database fixture or committed backup artifact.

### 2C likely files

- separate acceptance command/runbook and narrowly scoped readiness/Doctor
  integration;
- no personal database committed; no change to production defaults without
  separate approval.

## 9. Rollback and recovery strategy

- 2A application rollback: disable all dependent flags and retain additive
  evidence schema/events; do not downgrade while evidence or immutable history
  exists.
- 2A evidence correction: append replacement/revocation event; never edit
  forecast/scenario snapshots.
- 2B tool rollback: remove the tool commit only; existing verified backups remain
  operator-owned artifacts. A failed restore uses the pre-restore safety backup.
- 2C activation rollback: set explicitly enabled flags false, stop services,
  preserve the database, and restore only through the checked restore flow if
  data recovery is necessary.
- No rollback path deletes immutable history, weakens ownership, or silently
  changes currency.

## 10. Exit criteria

### 2A exits

- Evidence contract and provenance are approved and documented.
- Current active-account policy is deterministic, including inactive,
  duplicate, ambiguous, stale, mixed, and conflicting rows.
- No historical backfill or preference inference occurs.
- Provider/statement/operator evidence paths are tested with synthetic data.
- Correction/revocation is append-only and immutable history is unchanged.
- Forecast and Scenario Lab remain blocked unless every gate passes.
- Auth, ownership, privacy, SQLite/PostgreSQL, migration, and idempotency
  evidence is recorded locally.

### 2B exits

- Backup/check/restore commands are explicit-path, WAL-safe, non-destructive,
  checksum/manifest verified, and local-only — **passed**.
- Active writers, symlinks, unexpected paths, unsupported schema, and overwrite
  attempts are refused — **passed**.
- Seven synthetic safety tests passed, including WAL, concurrent readers,
  corruption/checksum, path safety, active-holder refusal, permissions, and
  disposable restore equivalence.
- A personal backup created outside the repository at `2026-08-15T19:17:27Z`
  verifies as `atlas-sqlite-backup/v1`, schema `X7a1b2c3d4e5`, WAL, integrity
  `ok`, SHA-256 `31a69327ebe7f4452ab9d3379001d51b07c3112428a26783ca68d8e2eb545e23`.
- No service starts automatically and no backup is silently overwritten/deleted
  — **passed**. In-place restore and pre-restore replacement are intentionally
  unsupported by this bounded new-path-only tool; any future in-place recovery
  must add a separately reviewed pre-restore safety flow before it is authorized.

### 2C exits

- Explicit user authorization is recorded before any personal-data action —
  **passed**.
- Backup is verified before inspection or mutation — **passed**.
- Four active accounts were evaluated; all were initially unknown and received
  one append-only operator-confirmed USD event. No conflicting/non-USD evidence
  existed and no blanket overwrite occurred — **passed**.
- Migration reached `X7a1b2c3d4e5`; integrity/quick checks and the non-disclosing
  goal precision gate passed — **passed**.
- Doctor/readiness currency state passed, but the enabled personal stack did
  not remain available for authenticated readiness. Personal projection
  configuration/baseline is also absent — **BLOCKED**.
- The clone operator path correctly records `500.00` as a Decimal-safe USD
  `net_worth` configuration and is idempotent. The new balance-observation
  operator confirms all four clone accounts atomically, hash-binds the current
  state, preserves the stored balances, and the provider loads projection
  state — **passed**.
- Forecast generation remains blocked because the provider emits the existing
  `legacy_float_balance_representation` warning with
  `reconciliation_state=partial`, while Rules Service requires a reconciled
  state with no missing-data codes. This is a separate financial-authority
  gate; it must not be bypassed by relabeling or weakening the state —
  **BLOCKED**.
- The corrected disposable lifecycle keeps UI/Rules/Finlynq health at 200 and
  authenticated readiness reachable across repeated probes — **passed**.
- No personal projection configuration, baseline, flags, or balance-observation
  write was made in this retry; the existing personal database and backups
  remain preserved — **passed**.

Wave 2C is therefore not complete. The next bounded task is to resolve the
legacy-float partial projection-state gate through a separately authorized
financial-authority decision, rerun the disposable clone forecast/readiness gate,
then repeat the approved personal readiness gate without creating synthetic
decisions or scenarios in the personal database.

## 11. Explicit future authorization prompts

### Wave 2A only

> Authorize implementation of Wave 2A — authoritative account currency only.
> You may modify the currency contract, evidence lifecycle, provider/statement
> mappings, projection gating, Doctor/readiness integration, and focused
> synthetic tests. Add a migration only if the implementation audit proves it
> is required. Do not access or modify any personal database, enable flags,
> implement backup/restore, start an enabled live stack, change forecast
> mathematics, or begin Wave 2B/2C or Phase 7. Preserve immutable history,
> ownership, privacy, default-off behavior, and the Goal Float limitation.

### Wave 2B only

> Authorize implementation of Wave 2B — non-destructive local backup and
> recovery only, using disposable synthetic databases. Do not access personal
> data, implement currency authority or activation, run migrations against a
> personal database, start an enabled stack, or begin Wave 2C or Phase 7.

### Wave 2C only

> Authorize personal-use activation acceptance for the explicitly identified
> local database after verified Wave 2A and 2B completion. Permit backup-first,
> read-only account inventory, explicitly confirmed currency evidence, approved
> local flag changes, full-stack restart validation, and rollback. Do not permit
> blanket backfill, real providers, email, scheduler, LLM, execution, trading,
> brokerage, money movement, retention/deletion changes, or Phase 7.

## 12. Evidence gaps after Wave 2B/2C execution

- The personal database was opened only under the explicit Wave 2C
  authorization; no balances, transactions, holdings, account numbers, or raw
  evidence were printed. No in-place restore was attempted.
- Plaid explicit-currency ingestion is not implemented or contract-tested.
- General CSV/PDF authoritative currency declaration is not established.
- Personal projection configuration/baseline is absent because the clone
  forecast gate failed before the authorized personal write.
- The balance-observation audit path is implemented and passes on the disposable
  clone for all four active accounts without changing balances. The remaining
  blocker is the existing `legacy_float_balance_representation` partial-state
  financial gate; this is not permission to relabel or weaken canonical state.
- The corrected local lifecycle is proven on a disposable clone: start exits
  successfully, UI/Rules/Finlynq health remains 200, and authenticated
  readiness remains reachable across repeated probes.
- Goal Float precision, retention/deletion, SQLite/PostgreSQL parity, and
  transitional tenancy remain open risks.
- No external provider, email, scheduler, LLM, execution, trading, brokerage,
  or money movement path was enabled.
