"""add merchant_aliases table — categorizer v2 alias learning

Revision ID: g2b3c4d5e6f7
Revises: f0a1b2c3d4e5
Create Date: 2026-07-03 22:00:00.000000

Phase 18 — categorizer v2 alias learning layer.

Adds the ``merchant_aliases`` table that owns the per-user learned
alias → category map. The categorizer's Pass 1 SELECTs from this
table on every bulk run; Pass 2 (substring MERCHANT_RULES) writes
to this table on every successful match so future imports of the
same merchant text hit Pass 1 (cheaper, deterministic, exact lookup).

Schema:

- ``alias_key``: canonical text (uppercase, non-alphanumeric collapsed
  to single space). Used for exact-match lookups.
- ``source_text``: the original (non-normalized) merchant text the
  alias was learned FROM (audit-only; not used in matching).
- ``category_id``: FK to ``categories.id``. NO CASCADE: a category
  rename shouldn't silently wipe years of per-user aliases (a future
  migration can re-attach by name).
- ``user_id``: FK to ``users.id``. Per-user scoping prevents the
  categorizer from leaking one household's habits to another when
  multi-user auth lands.
- ``UNIQUE(user_id, alias_key)``: the upsert helper in
  categorizer.py relies on this for INSERT-or-INCREMENT without a
  race.

Indexes:

- ``ix_merchant_aliases_id``: PK alignment with the rest of the schema.
- ``ix_merchant_aliases_user_id``: speeds up the categorizer's bulk
  SELECT ``WHERE user_id = :user AND alias_key IN (...)``.
- ``ix_merchant_aliases_alias_key``: speeds up the (latent) reverse
  lookup ``WHERE alias_key = :key`` for the audit/debug surface.

Down-grade drops the table; no FK from another table references
``merchant_aliases.id`` today (the categorizer SELECTs by
``alias_key`` not by id), so the down-grade is reversible without
scrub-then-drop.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g2b3c4d5e6f7"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "merchant_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("alias_key", sa.String(), nullable=False),
        sa.Column("source_text", sa.String(), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "alias_key",
            name="uq_merchant_aliases_user_alias",
        ),
    )
    op.create_index(
        op.f("ix_merchant_aliases_id"),
        "merchant_aliases",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_merchant_aliases_user_id"),
        "merchant_aliases",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_merchant_aliases_alias_key"),
        "merchant_aliases",
        ["alias_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_merchant_aliases_alias_key"),
        table_name="merchant_aliases",
    )
    op.drop_index(
        op.f("ix_merchant_aliases_user_id"),
        table_name="merchant_aliases",
    )
    op.drop_index(
        op.f("ix_merchant_aliases_id"),
        table_name="merchant_aliases",
    )
    op.drop_table("merchant_aliases")
