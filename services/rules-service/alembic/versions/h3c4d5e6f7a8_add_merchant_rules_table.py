"""add merchant_rules table — categorizer v3 db-backed substring rules

Revision ID: h3c4d5e6f7a8
Revises: g2b3c4d5e6f7
Create Date: 2026-07-04 18:00:00.000000

Phase 24 — DB-backed categorizer Pass 2 substring rules.

Background
----------
Pre-Phase-24 the categorizer's Pass 2 substring rules live as a
Python module-level ``MERCHANT_RULES`` dict (~117 keywords across 12
categories, declaration-ordered for greedy short-circuit). Adding a
new keyword required a code change + uvicorn restart. Phase 24 moves
the dict into a DB-backed table so the Settings UI can add/remove/
disable keywords without a redeploy.

Schema
------
- ``id`` PK — every other table has it; matcher parity.
- ``category_id`` FK ``categories.id`` (NOT NULL, ON DELETE CASCADE).
  ON DELETE CASCADE because a category deletion does NOT typically
  leave orphan rules behind — the user drops the WHOLE category they
  meant (e.g. "Other") and keeps the rest. Cascading the rules
  matches the intuitive migration semantics ("delete category, take
  its rules with you"); the user's ``merchant_aliases`` rows pointing
  at the deleted category keep integrity because the alias FK targets
  a row that no longer exists — ``merchant_aliases`` declares no
  cascade on its category FK so the aliases stay in place for the
  user to retag later.
- ``keyword`` String NOT NULL — the substring pattern, stored
  uppercased. Always uppercased at the write paths (the boot-time
  seed + ``routes/merchant_rules.py`` POST/PUT) so the categorizer's
  per-row scan can skip a per-call upper.
- ``priority`` Int NOT NULL default 100 — preserves the greedy
  short-circuit ordering of the old static dict. Seed assigns
  monotonically-increasing values (10, 20, 30, ...) across the
  dict's declaration order so existing test fixtures that walked
  dict-order keep working. User-added rules default to 100 so they
  fall to the END per category and don't silently displace system
  order unless the user explicitly re-prioritises via PUT.
- ``is_archived`` Bool NOT NULL default False — soft-delete flag.
  Hard-deleting a system rule would let the boot-time seed re-insert
  the same keyword on next uvicorn restart, undoing the user's
  delete. The seed helper checks for ``is_archived`` AND skips the
  row, so soft-deleting is the canonical way to remove a rule.
- ``created_at`` / ``updated_at`` DateTime.

Indexes
-------
- ``ix_merchant_rules_id`` — PK alignment with the rest of the schema.
- ``ix_merchant_rules_category_id`` — speeds up the seed helper's
  per-category SELECT ``WHERE category_id = :id``.
- ``uq_merchant_rules_category_keyword`` — uniqueness contract (see
  :class:`MerchantRule` docstring).
- ``ix_merchant_rules_archived_priority`` — composite, on
  (is_archived ASC, priority ASC). The categorizer's per-batch
  SELECT filters ``is_archived = false ORDER BY priority ASC``;
  the index keeps the scan O(log N) even with 500+ rows of user
  additions.

Down-grade
----------
Drops the table. No FK from another table references
``merchant_rules.id`` today (the categorizer SELECTs by
``category_id`` not by id), so the down-grade is reversible without
scrub-then-drop.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h3c4d5e6f7a8"
down_revision: Union[str, None] = "g2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "merchant_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("keyword", sa.String(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "category_id",
            "keyword",
            name="uq_merchant_rules_category_keyword",
        ),
    )
    op.create_index(
        op.f("ix_merchant_rules_id"),
        "merchant_rules",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_merchant_rules_category_id"),
        "merchant_rules",
        ["category_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_merchant_rules_archived_priority"),
        "merchant_rules",
        ["is_archived", "priority"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_merchant_rules_archived_priority"),
        table_name="merchant_rules",
    )
    op.drop_index(
        op.f("ix_merchant_rules_category_id"),
        table_name="merchant_rules",
    )
    op.drop_index(
        op.f("ix_merchant_rules_id"),
        table_name="merchant_rules",
    )
    op.drop_table("merchant_rules")
