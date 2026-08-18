"""Phase 30g — add transfer_pair_id to transactions.

An internal transfer appears as TWO rows: an outflow on account A and
an inflow on account B (same amount, near date). ``transfer_pair_id``
links each half to the other so cash-flow reports can treat the pair
as ONE neutral movement instead of an expense + income. Mirror of the
Phase 54+ duplicate tracking columns (``is_duplicate`` /
``duplicate_of_id``): nullable self-FK + index, additive, no data
back-fill (detection runs lazily from the transfer classifier).

Revision ID: T2f3a4b5c6d7
Revises: Z9a1b2c3d4e5
Create Date: 2026-08-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "T2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "Z9a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add transfer_pair_id column + self-FK + index to transactions."""
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("transfer_pair_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_transactions_transfer_pair",
            "transactions",
            ["transfer_pair_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_transactions_transfer_pair_id",
            ["transfer_pair_id"],
            unique=False,
        )


def downgrade() -> None:
    """Remove transfer pairing columns."""
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.drop_index("ix_transactions_transfer_pair_id")
        batch_op.drop_constraint("fk_transactions_transfer_pair", type_="foreignkey")
        batch_op.drop_column("transfer_pair_id")
