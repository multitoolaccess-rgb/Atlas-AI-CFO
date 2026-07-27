"""Phase 54+ — add duplicate tracking columns to transactions.

Instead of SKIPPING duplicate rows during import (the Phase 54+ dedup
contract), every row is now INSERTED and flagged with ``is_duplicate=True``
and ``duplicate_of_id`` pointing to the earlier transaction it matches.
The Activity page renders a duplicate badge and the user can resolve
duplicates (keep this one, keep original, keep all) via a new endpoint.

Revision ID: M2a3b4c5d6e7
Revises: L1c2d3e4f5a6, e1f2a3b4c5d6
Create Date: 2026-07-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "M2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = ("L1c2d3e4f5a6", "e1f2a3b4c5d6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_duplicate and duplicate_of_id columns to transactions."""
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )
        batch_op.add_column(
            sa.Column("duplicate_of_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_transactions_duplicate_of",
            "transactions",
            ["duplicate_of_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_transactions_is_duplicate",
            ["is_duplicate"],
            unique=False,
        )


def downgrade() -> None:
    """Remove duplicate tracking columns."""
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.drop_index("ix_transactions_is_duplicate")
        batch_op.drop_constraint("fk_transactions_duplicate_of", type_="foreignkey")
        batch_op.drop_column("duplicate_of_id")
        batch_op.drop_column("is_duplicate")
