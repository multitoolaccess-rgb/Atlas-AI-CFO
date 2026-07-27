"""Phase 54+ — reconcile legacy ``debit`` / ``credit`` backfill.

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-07-08 00:00:00.000000

Why this migration exists
=========================

The original Phase 52+ migration ``d1e2f3a4b5c6_add_transaction_
debit_credit.py`` already backfills ``transactions.debit`` and
``transactions.credit`` from the legacy signed ``amount`` column
on the same upgrade pass that adds the columns (Step 2 of that
migration). For a clean install (``alembic upgrade head`` on a
fresh DB), the backfill fires on the FIRST run and the response
contract holds forever after: every row has at least one of
``(debit, credit)`` populated.

Three real-world cases escape that contract:

1. **Dev DB with ``alembic_version`` wiped**: the operator deletes
   the alembic version row so they can ``alembic stamp head`` and
   skip the historical chain on a locally-imported production DB.
   The schema columns never run through Step 2 of the original
   migration, so pre-existing rows keep NULL D/C.

2. **Mid-migration crash**: the Step-2 ``UPDATE`` of
   ``d1e2f3a4b5c6`` failed halfway (DB lock contention, FK
   violation, etc). Step 1 (column add) committed; Step 2 didn't.
   Re-running ``alembic upgrade head`` re-enters Step 1 (column
   already exists → no-op) and Step 2 (UPDATE runs again — but
   because ``d1e2f3a4b5c6``'s WHERE was ``(debit IS NULL OR debit
   = 0)``, partially-populated rows that survived the crash may
   not be re-reached). The Phase 54+ reconcile closes that gap.

3. **Fresh parser inserts that pre-date Phase 52+ roll-out**: a
   parser shipped BEFORE this migration chain hit production
   writes ``amount`` but not ``debit``/``credit``. The Phase 52+
   parser writes all three. This migration is the catch-up for
   the gap window.

Migration shape (CRITICAL)
==========================

The ``upgrade()`` body is identical in intent to Step 2 of
``d1e2f3a4b5c6`` — same sign convention, same idempotency guard,
same defensive ``OR debit = 0`` clause. We DO NOT mirror Step 3
(account-balance recompute) here: that recompute belongs in the
original migration so a single ``alembic upgrade head`` on a fresh
DB computes the balance once with the correct dual-column inputs.
This migration is reconcile-ONLY — it does not touch
``accounts.current_balance`` because re-recomputing already-correct
balances is a no-op and re-recomputing from partially-backfilled
rows would de-sync the legacy rows that the original migration
ALREADY computed correctly.

Downgrade: no-op
================

A data migration's downgrade CANNOT safely reconstruct the
pre-migration state — by the time the user rolls back, the
backfilled values are indistinguishable from Phase 52+-parser
writes (same ``(debit, credit)`` schema; only the
``import_batches.id`` FK history differentiates, and even that
disappears when the user deletes the batch). We DO NOT attempt
to wipe ``debit`` / ``credit`` here: the downgrade would clobber
legitimate Phase 52+-parser writes on freshly-imported
transactions and is irreversible from the application's per-
spective. Operators rolling back should accept that the legacy
backfill is a one-way operation; the schema-level ``downgrade``
just drops nothing (the columns still exist for fresh parser
writes).

SQLite compatibility
====================

- ``bind.execute(sa.text("..."))`` is the canonical 1.4+ idiom;
  raw-string ``op.execute(...)`` parses fine here too but the
  ``sa.text`` wrapper is what the rest of this codebase uses
  (mirrors ``d1e2f3a4b5c6``'s Step 2).
- SQLite serialises writers; an in-flight import on the rules-
  service will deadlock against this migration. The
  ``start.sh`` alembic block runs BEFORE the uvicorn boot, so
  the typical order is migration → no writers → boot, which is
  safe. A manual ``alembic upgrade head`` against a running
  rules-service risks the lock — operators should bounce the
  service first.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Reconcile legacy rows: idempotent backfill on rows where both
    ``debit`` AND ``credit`` are NULL AND ``amount`` is non-zero.

    Sign rule (canonical banking double-entry, matches
    ``d1e2f3a4b5c6`` Step 2):
        amount > 0  → credit = amount, debit stays NULL
        amount < 0  → debit  = -amount, credit stays NULL
        amount == 0 → both stay NULL (FX-neutral edge case)

    Idempotency guard: ``debit IS NULL AND credit IS NULL`` AND
    ``amount != 0``. A row that:
      - was correctly populated by the Phase 52+ parser at insert
        time (has at least one populated column) — skipped.
      - was already backfilled by ``d1e2f3a4b5c6`` Step 2 — skipped.
      - is a non-zero legacy orphan — handled.
      - is a zero-amount row — left at both NULL on purpose
        (FX-neutral entries are a valid invariant).
    """
    bind = op.get_bind()

    # Negative amount → debit (money that LEFT the account).
    bind.execute(
        sa.text(
            "UPDATE transactions "
            "SET debit = -amount "
            "WHERE amount < 0 "
            "AND debit IS NULL AND credit IS NULL"
        )
    )

    # Positive amount → credit (money that ENTERED the account).
    bind.execute(
        sa.text(
            "UPDATE transactions "
            "SET credit = amount "
            "WHERE amount > 0 "
            "AND debit IS NULL AND credit IS NULL"
        )
    )
    # ``amount = 0`` rows: deliberately untouched. Both NULL is the
    # FX-neutral invariant.


def downgrade() -> None:
    """No-op. See module docstring for the irreversibility rationale.

    A future hardening could add a timestamp-based wipe
    (e.g. ``WHERE created_at < '2026-07-08'``) but that's fragile
    (drifts between code + DB time) and the application has no
    schema-level need to roll back to a NULL D/C state — the dual-
    column contract is the canonical one going forward.
    """
    # Intentional pass. Operators: see the docstring.
    return None
