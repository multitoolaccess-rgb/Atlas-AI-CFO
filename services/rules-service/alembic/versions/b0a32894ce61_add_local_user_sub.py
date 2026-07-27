"""add local_user_sub

Revision ID: b0a32894ce61
Revises: b0a32894ce60
Create Date: 2026-06-29 21:00:00.000000

Three-step migration (idempotent on partial-applied states) that closes the
duplicate-user bug documented in the Settings-page save error:

1. **Ensure column exists** — ``local_user_sub`` (String) carries the JWT
   ``sub`` claim. We skip the ``add_column`` if the column is already there
   from a previously aborted run; this lets the migration self-heal the
   partial state left by an interrupted apply on SQLite.

2. **Backfill** — every surviving row gets ``local_user_sub = 'alex'``
   (the local-default key). At this point the column is nullable and
   unprotected. We deliberately do NOT enforce uniqueness before the
   scrub sees the data.

3. **Scrub duplicates post-backfill** — for any ``local_user_sub`` value
   that collides across multiple rows, keep the ``MIN(id)`` row as the
   survivor and re-point every FK from the duplicates onto the survivor
   before deleting them. The original Settings-page incident produced
   exactly this conflict: id=1 (email overwritten) and id=2 (re-seeded by
   the email-keyed lookup), both of which would otherwise collide on
   ``local_user_sub='alex'``.

4. **Enforce** — convert the nullable column to NOT NULL and add a UNIQUE
   index so ``get_or_create_local_user`` keys off an exact-match and can
   no longer accidentally create a second row on a future SET.

Why reorder vs. the original buggy draft: scrubbing by ``email`` (BEFORE
backfill) found zero duplicates because the buggy fork left the two rows
with *different* emails. The conflict only manifests AFTER backfill when
both rows hold ``local_user_sub='alex'``. Scrubbing after backfill catches
both the original incident and any future fork pattern where two rows end
up keyed to the same JWT ``sub``.

SQLite compatibility: ``NOT NULL`` conversion and unique-index creation
both go through ``batch_alter_table`` which transparently rebuilds the
table on SQLite.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b0a32894ce61"
down_revision: Union[str, None] = "b0a32894ce60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def _column_nullable(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    for c in insp.get_columns(table):
        if c["name"] == column:
            return bool(c.get("nullable", True))
    return True


def _unique_index_exists(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    for idx in insp.get_indexes(table):
        if idx.get("unique") and column in (idx.get("column_names") or []):
            return True
    for uc in insp.get_unique_constraints(table):
        if column in (uc.get("column_names") or []):
            return True
    return False


def _tables_with_user_fk(bind) -> list[str]:
    """Dynamically enumerate every table whose schema declares a FK column to
    ``users.id``. Hardcoding the table list (e.g.
    ``('accounts', 'budgets', 'import_batches')``) was the original bug: any
    unanticipated user_id-bearing table (Phase 5-7 added ``transactions``)
    blocks the subsequent ``DELETE`` with FOREIGN KEY constraint, and the
    try/except only absorbs ``ProgrammingError`` (missing table), not
    ``IntegrityError``. The live set is read from the schema on every run so
    future tables don't silently break the migration.
    """
    insp = sa.inspect(bind)
    out: list[str] = []
    for table in insp.get_table_names():
        try:
            fks = insp.get_foreign_keys(table)
        except sa.exc.ProgrammingError:
            # View or non-standard table — skip, can't carry a user FK anyway.
            continue
        if any(
            fk.get("referred_table") == "users"
            and "id" in (fk.get("referred_columns") or [])
            for fk in fks
        ):
            out.append(table)
    return sorted(out)


def upgrade() -> None:
    """Idempotently migrate to the new identity-key contract."""
    bind = op.get_bind()

    # 1. Ensure the column is present (add nullable if missing).
    if not _column_exists(bind, "users", "local_user_sub"):
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(
                sa.Column("local_user_sub", sa.String(), nullable=True)
            )

    # 2. Backfill every row. WHERE clause skips rows that already carry
    #    a real value so we don't trample a future multi-tenant setup.
    bind.execute(
        sa.text(
            "UPDATE users SET local_user_sub = 'alex' "
            "WHERE local_user_sub IS NULL OR local_user_sub = ''"
        )
    )

    # 3. Scrub duplicates that the backfill would expose on the unique
    #    constraint. For each sub-keyed group with >1 row, keep MIN(id)
    #    as the survivor — move FKs from the others onto the survivor,
    #    then delete the others. Idempotent: no-op if no conflicts.
    conflicts = bind.execute(
        sa.text(
            """
            SELECT local_user_sub, MIN(id) AS survivor_id
            FROM users
            WHERE local_user_sub IS NOT NULL
            GROUP BY local_user_sub
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    # Collect every table that currently carries a user_id FK onto users.id;
    # queried dynamically so ADDED tables don't silently block the scrub.
    user_fk_tables = _tables_with_user_fk(bind)
    # Verify that every such table actually has a user_id column (defensive —
    # some FKs may name the local column differently, e.g. `owner_id`).
    insp = sa.inspect(bind)
    fk_assignments: list[tuple[str, str]] = []
    for table in user_fk_tables:
        cols = {c["name"] for c in insp.get_columns(table)}
        if "user_id" in cols:
            fk_assignments.append((table, "user_id"))
        else:
            # Fall back to whatever FK column references users.id.
            for fk in insp.get_foreign_keys(table):
                if (
                    fk.get("referred_table") == "users"
                    and fk.get("constrained_columns")
                ):
                    fk_assignments.append((table, fk["constrained_columns"][0]))
                    break

    for sub, survivor_id in conflicts:
        for table, fk_col in fk_assignments:
            bind.execute(
                sa.text(
                    f"UPDATE {table} SET {fk_col} = :sid "
                    f"WHERE {fk_col} IN ("
                    f"  SELECT id FROM users "
                    f"  WHERE local_user_sub = :sub AND id <> :sid"
                    f")"
                ),
                {"sid": survivor_id, "sub": sub},
            )
        bind.execute(
            sa.text(
                "DELETE FROM users "
                "WHERE local_user_sub = :sub AND id <> :sid"
            ),
            {"sid": survivor_id, "sub": sub},
        )

    # 4a. Convert the column to NOT NULL if it is still nullable.
    if _column_nullable(bind, "users", "local_user_sub"):
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column(
                "local_user_sub",
                existing_type=sa.String(),
                nullable=False,
            )

    # 4b. Add the unique index if it is not already present.
    if not _unique_index_exists(bind, "users", "local_user_sub"):
        with op.batch_alter_table("users") as batch_op:
            batch_op.create_index(
                batch_op.f("ix_users_local_user_sub"),
                ["local_user_sub"],
                unique=True,
            )


def downgrade() -> None:
    """Best-effort rollback: drop the unique index, then the column."""
    bind = op.get_bind()
    if _unique_index_exists(bind, "users", "local_user_sub"):
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_index(batch_op.f("ix_users_local_user_sub"))
    if _column_exists(bind, "users", "local_user_sub"):
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("local_user_sub")
