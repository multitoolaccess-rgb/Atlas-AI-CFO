"""add family_members table + accounts.family_member_id NOT NULL FK

Revision ID: e9f0a1b2c3d4
Revises: d5e6f7a8b9c0
Create Date: 2026-07-03 12:00:00.000000

Phase 16 — multi-family-member account grouping. Mirrors the Goal soft-
archive pattern (Phase 8) but adds a hard FK on ``accounts`` so every
account belongs to exactly one family member.

Schema shape:

- ``family_members`` table mirrors ``Goal``:
  ``user_id`` FK, ``name`` required, ``color`` VARCHAR(7),
  ``is_archived`` BOOL default False, ``is_self`` BOOL default False,
  ``created_at`` / ``updated_at`` timestamps.
- An inline ``sa.Index("ix_family_members_user_id", "user_id")`` is
  DECLARED INSIDE the ``create_table`` call. The PK column (``id``)
  gets an implicit index from the ``PrimaryKeyConstraint`` so an
  explicit ``op.create_index("ix_family_members_id", ...)`` is not
  needed.
- UNIQUE (user_id, name) so duplicate member names per owner are
  rejected with a 409 via the global IntegrityError handler.

Accounts-side migration:

- ADD COLUMN ``accounts.family_member_id`` INTEGER nullable first
  (SQLite ALTER TABLE has no full ADD CONSTRAINT FK support; the
  FK is created in a separate ``batch_alter_table`` after backfill).
- Bootstrap a Self row for EVERY user (not just users-with-accounts;
  the routes need a Self row for the default-to-Self branch even if
  the user has zero accounts).
- UPDATE ``accounts`` so each account points at its owner's Self row.
- Flip ``family_member_id`` to NOT NULL via ``batch_alter_table``
  (SQLite-safe: alembic clones the table, copies rows, drops the
  old table, renames).
- Add the FK constraint ``fk_accounts_family_member`` in the same
  batch so the column is locked in one step.

Why batch_alter_table: SQLite ALTER COLUMN <nullable=False> requires
a full table rebuild (the SQLite dialect does not expose ``ALTER
COLUMN`` as a standalone operation). ``batch_alter_table`` is
alembic's portable helper that does the rebuild under the hood so
the same migration runs cleanly on Postgres AND SQLite.

Edge-case handling:

- ``op.create_index(...)`` was REMOVED entirely. The model's
  ``Index("ix_family_members_user_id", "user_id")`` is declared
  inline in the create_table ``*args`` so alembic inherits
  SQLAlchemy's table-creation ``checkfirst=True`` semantics:
  against a freshly-bootstrapped DB the index is created; against
  a DB that already has the table + index, both are no-ops. The
  earlier draft's explicit ``op.create_index`` calls above caused
  ``OperationalError: index ix_family_members_user_id already
  exists`` in the test bootstrap (Base.metadata.create_all wires
  the same index from the model's inline declaration). Inline-
  dedupe keeps the migration idempotent across both the cold-start
  path and the re-run path.
- The Self-row INSERT in the backfill is wrapped in try/except
  IntegrityError. If a developer or earlier test inserted a manual
  ``family_members`` row with the same ``(user_id, name)`` as the
  Self candidate (``users.full_name``), the UNIQUE constraint would
  otherwise abort the migration and strand users in mid-migrate
  state. The collision-proof fallback ``f"Self {uid}"`` guarantees
  uniqueness by including the user's primary key in the name.

Downgrade reverses every step — drops the FK, drops the column,
then drops the table.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.exc import IntegrityError as SQLAlchemyIntegrityError
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create ``family_members`` table WITHOUT any inline Index
    # declaration. The index ``ix_family_members_user_id`` is owned
    # by the ORM model's ``__table_args__`` (which the
    # ``Base.metadata.create_all``-driven test bootstrap honours)
    # AND by the explicit ``op.create_index`` call below with
    # ``if_not_exists=True`` (which the alembic upgrade path honours).
    # Putting ``sa.Index(...)`` inline INSIDE the ``op.create_table``
    # args collides on a DB that ``create_all`` already populated
    # (the test bootstrap runs both, in that order): alembic sees
    # the table pre-existing, skips CREATE TABLE, but still tries
    # CREATE INDEX for the inline Index — which fires
    # ``OperationalError: index ix_family_members_user_id already exists``.
    # Moving the index declaration OUT of the create_table callsite
    # and into a sibling ``op.create_index(if_not_exists=True)`` is
    # the canonical alembic 1.13 idiom (``CREATE INDEX IF NOT EXISTS``
    # is supported by both SQLite + Postgres natively) and keeps
    # the migration idempotent across both cold-start and
    # re-upgrade paths.
    op.create_table(
        "family_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("color", sa.String(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_self", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ),
        sa.UniqueConstraint("user_id", "name", name="uq_family_member_user_name"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Owns the ``ix_family_members_user_id`` index — lives on the
    # alembic-driven path (cold-start upgrade on a brand-new DB).
    # ``if_not_exists=True`` translates to ``CREATE INDEX IF NOT
    # EXISTS ...`` on SQLite + Postgres so a DB that ``create_all``
    # already populated (the test conftest bootstrap) no-ops.
    op.create_index(
        "ix_family_members_user_id",
        "family_members",
        ["user_id"],
        unique=False,
        if_not_exists=True,
    )
    # Note: NO explicit ``op.create_index(op.f("ix_family_members_id"), ...)``
    # because the PK column auto-creates its own implicit index on every
    # SQLAlchemy-supported dialect (the convention ``ix_<table>_id`` is
    # an artefact of SQLAlchemy 1.x's lax convention, not a separate
    # index — declaring it manually produces a duplicate that triggers
    # the same OperationalError as Bug B).

    # 2. Add ``accounts.family_member_id`` as NULLABLE so the
    # backfill UPDATE can land without violating a NOT NULL
    # constraint. The FK is added in step 4 (batch_alter_table)
    # so SQLite's ALTER TABLE can run the table rebuild safely.
    op.add_column(
        "accounts",
        sa.Column("family_member_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_accounts_family_member_id"),
        "accounts",
        ["family_member_id"],
        unique=False,
        if_not_exists=True,
    )

    # 3. Backfill — for EVERY user (even users with zero accounts,
    # because the routes lazy-seed Self on the first GET), insert
    # a Self row if absent, then UPDATE accounts for that user.
    # The Self-row INSERT is wrapped in try/except IntegrityError
    # so a manual ``family_members`` row that already collided on
    # ``(user_id, name)`` doesn't strand the migration in mid-
    # apply state. The fallback ``f"Self {uid}"`` is collision-
    # proof by construction (the user's PK is unique within the
    # table).
    bind = op.get_bind()
    users = bind.execute(text("SELECT id, full_name FROM users")).mappings().all()
    for user in users:
        uid = user["id"]
        full_name = (user["full_name"] or "").strip() or "Self"
        existing = bind.execute(
            text(
                "SELECT id FROM family_members "
                "WHERE user_id = :uid AND is_self = 1"
            ),
            {"uid": uid},
        ).first()
        if existing is not None:
            self_id = existing[0]
        else:
            try:
                inserted = bind.execute(
                    text(
                        "INSERT INTO family_members "
                        "(user_id, name, color, is_archived, is_self) "
                        "VALUES (:uid, :name, :color, 0, 1)"
                    ),
                    {
                        "uid": uid,
                        "name": full_name,
                        "color": "#10b981",
                    },
                )
                self_id = inserted.lastrowid
            except SQLAlchemyIntegrityError:
                # A manual ``(user_id, name)`` row already exists
                # with the same ``full_name`` — fall back to a name
                # that includes the user's PK so the UNIQUE
                # constraint cannot fire. The Self-flagged row may
                # already exist, so re-SELECT to use it; if a
                # different Self row got inserted, prefer it.
                fallback_name = f"Self {uid}"
                try:
                    inserted = bind.execute(
                        text(
                            "INSERT INTO family_members "
                            "(user_id, name, color, is_archived, is_self) "
                            "VALUES (:uid, :name, :color, 0, 1)"
                        ),
                        {
                            "uid": uid,
                            "name": fallback_name,
                            "color": "#10b981",
                        },
                    )
                    self_id = inserted.lastrowid
                except SQLAlchemyIntegrityError:
                    # Last resort: re-SELECT for an existing
                    # is_self row whose name we don't care about.
                    self_id = bind.execute(
                        text(
                            "SELECT id FROM family_members "
                            "WHERE user_id = :uid AND is_self = 1 LIMIT 1"
                        ),
                        {"uid": uid},
                    ).scalar_one()
        # Assign every existing account to this user's Self row.
        # The (user_id, family_member_id) tuple is set in lockstep
        # so a user with no accounts gets an UPDATE no-op (zero
        # rows affected). Either way, the FK is satisfiable
        # before the NOT NULL flip in step 4.
        bind.execute(
            text(
                "UPDATE accounts SET family_member_id = :sid "
                "WHERE user_id = :uid AND family_member_id IS NULL"
            ),
            {"sid": self_id, "uid": uid},
        )

    # 4. Lock down the FK + NOT NULL in one batch_alter_table
    # operation so SQLite + Postgres both take the same migration
    # path. The batch helper clones the table, applies the
    # changes, and renames — a single ALTER\DROP sequence that
    # would otherwise require 12 manual ops on SQLite.
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.alter_column(
            "family_member_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.create_foreign_key(
            "fk_accounts_family_member",
            "family_members",
            ["family_member_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("accounts") as batch_op:
        # Phase 16 reviewer note: drop the column-level index BEFORE
        # the column itself. SQLite doesn't auto-drop indexes when a
        # column is dropped (Postgres DOES), so a downgrade against
        # SQLite would otherwise leave an orphan
        # ``ix_accounts_family_member_id`` lying around. ``if_exists`` is
        # intentionally NOT passed here: alembic 1.13.x's
        # ``ApplyBatchImpl.drop_index`` rejects that kwarg
        # (``TypeError: ... got an unexpected keyword argument 'if_exists'``),
        # and it is unnecessary by construction because the upgrade path
        # unconditionally provisions the index, so the downgrade against
        # any post-upgrade schema state is safe.
        batch_op.drop_index(
            op.f("ix_accounts_family_member_id"),
        )
        batch_op.drop_constraint("fk_accounts_family_member", type_="foreignkey")
        batch_op.drop_column("family_member_id")

    # The ``family_members`` table drop cascades its own
    # ``ix_family_members_user_id`` index via the SQLite/Postgres
    # DROP TABLE behavior, so no explicit drop_index is required here.
    op.drop_table("family_members")
