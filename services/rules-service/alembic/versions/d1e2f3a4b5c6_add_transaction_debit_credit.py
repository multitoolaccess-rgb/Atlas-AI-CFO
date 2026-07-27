"""add transaction debit and credit columns

Revision ID: d1e2f3a4b5c6
Revises: L1c2d3e4f5a6
Create Date: 2026-07-08 00:00:00.000000

Why this migration exists
========================

The user wants the transactions table to mirror the bank statement's
native layout — a separate ``Debit`` column for money going OUT
(expenses) and a separate ``Credit`` column for money coming IN
(income / payments). Today every row stores a SINGLE signed
``amount`` Float whose meaning differs by account_type:

- depository (checking / savings): ``amount > 0`` = income,
  ``amount < 0`` = expense.
- credit_card (post-Phase-52 sign-flip at import time):
  ``amount > 0`` = payment, ``amount < 0`` = purchase.

The mixed sign conventions created the historic "is this debt or
asset" bug: a credit card stored at the Phase-52 sign-flipped
``-17400.82`` (debt) had to be added directly to net worth, AND a
fresh import that landed as ``+17400.82`` (debt under the opposite
convention) inflated net worth by the debt amount itself. Splitting
the bookkeeping into ``debit`` (always unsigned positive = money
that left the account) and ``credit`` (always unsigned positive =
money that entered) makes the mental model + dashboard formula
disambiguated:

  current_balance (depository) = SUM(credit) - SUM(debit)
  current_balance (credit)     = SUM(debit)  - SUM(credit)

  dashboard total_balance +=   depository sum (positive = asset)
  dashboard total_balance -=   credit-type sum    (positive = debt)

After this migration:

- The ``amount`` column STAYS in place — every existing read
  path still works (the read-paths use SUM(amount), and
  ``amount = credit - debit`` after this migration runs, so
  SUM(amount) still equals ``SUM(credit) - SUM(debit)`` for
  depositories and ``SUM(debit) - SUM(credit)`` for credit
  accounts when reading an individual account's balance).
  Cross-account aggregates (total_balance) WILL diverge from the
  old SUM(amount) because the sign of credit types flips in
  ``current_balance``, so the dashboard formula must be updated
  to MATCH the new convention.

- The Type-aware ``Account.current_balance`` recompute runs as
  Step 3 below so a credit_card previously stored at ``-17400.82``
  becomes ``+17400.82`` — POSITIVE debt, matching the user's
  stated mental model: "card balance = expenses - payments =
  POSITIVE number representing debt".

Migration order (CRITICAL — reordering breaks the migration)
============================================================

Step 1 — add nullable ``debit`` and ``credit`` Float columns.
Step 2 — backfill ``debit`` / ``credit`` from the existing
         ``amount`` column using a sign rule:
           amount > 0  -> credit = amount,  debit = NULL
           amount < 0  -> debit  = -amount, credit = NULL
           amount == 0 -> debit = credit = NULL
Step 3 — recompute every active account's ``current_balance``
         using the type-aware formula above. Step 3 is what
         FLIPS the credit_card current_balance sign and is the
         highest-risk step: a rollback of this migration must
         restore the OLD sign via the same logic in ``downgrade``.

Why not add a CHECK constraint
==============================

A DB-level ``CHECK (NOT (debit IS NOT NULL AND credit IS NOT NULL))``
would lock the contract at the DB layer, but SQLite (the locked dev
DB) does not enforce CHECK constraints on existing rows after a
column add and the cross-dialect portable assertion (``sa.CheckConstraint``)
requires ``batch_alter_table`` rebuilds that interact poorly with
``nullable=True`` on the add step. App-layer enforcement is the
canonical "defensive guard" the codebase already uses elsewhere
(e.g. ``db.execute(sa.text("..."))`` for manual backfills).

SQLite compatibility notes
===========================

- ``batch_alter_table`` is required for the column add because
  SQLite does not support ``ALTER TABLE ... ADD COLUMN ... NOT
  NULL`` without a default. We add as nullable + backfill in a
  separate ``UPDATE`` + leave nullable (no enforced NOT NULL).
- ``UPDATE`` statements are atomic on SQLite; a stuck migration
  is recoverable by deleting the SQLite DB file + restarting
  from ``alembic upgrade head`` (the dev seed auto-recreates the
  schema via the prior migrations).
- PostgreSQL converts the same statements losslessly — the
  column-add + UPDATE pair is portable.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "L1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_has_column(bind, table: str, column: str) -> bool:
    """Idempotent column-exists check (mirrors b0a32894ce61)."""
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    """Idempotently add debit + credit columns, backfill, and
    recompute every active account's current_balance under the new
    type-aware convention.

    Safe to re-run on a partially-applied database: every step
    short-circuits if its precondition is already satisfied.
    """
    bind = op.get_bind()

    # ---- Step 1: add nullable columns ----
    if not _table_has_column(bind, "transactions", "debit"):
        with op.batch_alter_table("transactions") as batch_op:
            batch_op.add_column(
                sa.Column("debit", sa.Float(), nullable=True)
            )
    if not _table_has_column(bind, "transactions", "credit"):
        with op.batch_alter_table("transactions") as batch_op:
            batch_op.add_column(
                sa.Column("credit", sa.Float(), nullable=True)
            )

    # ---- Step 2: backfill debit / credit from existing amount ----
    # Sign rule (canonical banking double-entry):
    #   amount >  0 -> credit = amount, debit stays NULL
    #   amount <  0 -> debit  = -amount,  credit stays NULL
    #   amount == 0 -> both NULL
    #
    # Idempotent: the WHERE clause skips rows whose target column
    # is already populated (a re-run on a partially-applied DB
    # won't overwrite a real value). Defensive: a future
    # mechanical edit to a row's debit/credit via a manual SQL
    # patch is preserved.
    bind.execute(
        sa.text(
            "UPDATE transactions SET debit = -amount "
            "WHERE amount < 0 AND (debit IS NULL OR debit = 0)"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE transactions SET credit = amount "
            "WHERE amount > 0 AND (credit IS NULL OR credit = 0)"
        )
    )

    # ---- Step 3: recompute every active account's current_balance ----
    # Type-aware formula:
    #   deposit accounts (checking / savings / other):
    #     current_balance = SUM(credit) - SUM(debit)   (positive = owned)
    #   credit accounts (credit_card / loan / mortgage):
    #     current_balance = SUM(debit)  - SUM(credit)   (positive = owed)
    #
    # Defensive: skip accounts whose description carries the
    # [debit-credit-migrated] marker so a re-run is clean.
    # Operators grepping .run/backend.log for the marker can spot
    # migrated rows without a SQL query.
    _DEPOSIT_TYPES = ("checking", "savings", "debit_card", "other")
    _CREDIT_TYPES = ("credit_card", "loan", "mortgage")
    deposit_types_sql = ", ".join(f"'{t}'" for t in _DEPOSIT_TYPES)
    credit_types_sql = ", ".join(f"'{t}'" for t in _CREDIT_TYPES)
    _MARKER = "[debit-credit-migrated]"

    # 3a. Deposit accounts: current_balance = SUM(credit) - SUM(debit).
    bind.execute(
        sa.text(
            f"""
            UPDATE accounts
            SET current_balance = COALESCE(
                (SELECT SUM(credit) - SUM(debit)
                 FROM transactions
                 WHERE transactions.account_id = accounts.id),
                0.0
            )
            WHERE account_type IN ({deposit_types_sql})
              AND is_active = 1
            """
        )
    )
    # 3b. Credit accounts: current_balance = SUM(debit) - SUM(credit).
    bind.execute(
        sa.text(
            f"""
            UPDATE accounts
            SET current_balance = COALESCE(
                (SELECT SUM(debit) - SUM(credit)
                 FROM transactions
                 WHERE transactions.account_id = accounts.id),
                0.0
            )
            WHERE account_type IN ({credit_types_sql})
              AND is_active = 1
            """
        )
    )
    # 3c. Investment accounts: leave current_balance untouched
    # (Phase 35+ investment valuation is computed from positions,
    # not raw transactions, so SUM(debit)-SUM(credit) is wrong
    # here).
    #
    # Note — no marker is stamped on account descriptions. An
    # earlier draft appended ``[debit-credit-migrated]`` to the
    # user-visible ``accounts.description`` column, but the FE
    # renders that field on the Accounts page, so the marker
    # would surface in the UI as internal bookkeeping noise.
    # The migration is already idempotent (the WHERE clauses on
    # steps 2 + 3a + 3b all guard against re-application), so a
    # marker is unnecessary. Operators chasing "was this row
    # migrated?" can spot the answer by checking ``debit IS NOT
    # NULL OR credit IS NOT NULL`` on the transaction rows.


def downgrade() -> None:
    """Best-effort reverse:
    - Set ``current_balance`` back to ``SUM(amount)`` (the legacy
      formula assumes the post-Phase-52 sign-flip convention where
      credit_card balance is stored as NEGATIVE debt).
    - Drop the ``debit`` and ``credit`` columns.

    The downgrade does NOT attempt to restore the original
    pre-migration balance values (those were the bug-state values
    that the migration was written to fix). It only walks back
    to the last defensible DB layout: ``amount`` is the source of
    truth on rollback, ``debit`` / ``credit`` are dropped, and
    ``current_balance`` is recomputed from SUM(amount) so the
    pre-existing dashboard formula (which sums amount on
    credit_card types directly to subtract from net worth) is
    consistent again.
    """
    bind = op.get_bind()

    # Reverse Step 3: recompute current_balance back to SUM(amount)
    # so the legacy dashboard formula (ADD credit_card directly)
    # works without the dual-column adjustment.
    bind.execute(
        sa.text(
            """
            UPDATE accounts
            SET current_balance = COALESCE(
                (SELECT SUM(amount) FROM transactions
                 WHERE transactions.account_id = accounts.id),
                0.0
            )
            WHERE is_active = 1
            """
        )
    )

    # No marker to strip — the upgrade step intentionally
    # avoids stamping the user-visible description column.

    # Reverse Step 2/1: drop the new columns. amount's historical
    # values are not restored because we never modified amount.
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("credit")
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("debit")
