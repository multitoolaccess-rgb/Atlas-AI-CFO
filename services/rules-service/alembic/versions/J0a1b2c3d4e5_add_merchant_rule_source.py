"""add source column to merchant_rules — Phase 27 provenance tracking

Revision ID: J0a1b2c3d4e5
Revises: h3c4d5e6f7a8
Create Date: 2026-07-08 12:00:00.000000

Phase 27 — Surface WHERE-WAS-THIS-RULE-FROM on every merchant rule.

Background
----------
Pre-Phase-27 the ``merchant_rules`` table had no notion of how a
rule was added. The user could only distinguish seeded system rows
from user additions by inspection (priority: 10/20/30 vs 100) and
the audit timestamp. Phase 27 adds a ``source`` enum column that
explicitly labels each row so the user can ask "did this rule come
from the seed, from a Tag Rule, or from a CSV import?".

Schema change
-------------
Adds ``source VARCHAR(20) NOT NULL DEFAULT 'system'`` on the
``merchant_rules`` table.

Back-fill strategy
------------------
1. ``server_default='system'`` so any pre-existing rows (Phase 24
   seed rows; min ~117 on a populated DB) get the right value at
   ALTER time without a separate UPDATE statement. This matches
   reality: the existing rows were 100% seeded by the boot-time
   ``seed_default_merchant_rules`` helper.
2. Model-level Python ``default='manual'`` so any NEW ORM-row
   construction goes through the route layer's explicit ``source``
   assignment (the user form / import path always sets it).
   The ``server_default`` from migration + ``default`` from model
   diverge deliberately — the migration's ``server_default``
   covers the ALTER-time back-fill; the model's ``default`` covers
   the runtime ORM-row default. The routes never rely on either
   because they always pass ``source`` explicitly.

Down-grade
----------
Drops the column. The route layer's POST default already covers
the empty column (``source`` absent → route maps to ``'manual'``)
so test rollback is safe.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "J0a1b2c3d4e5"
down_revision: Union[str, None] = "h3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "merchant_rules",
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'system'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("merchant_rules", "source")
