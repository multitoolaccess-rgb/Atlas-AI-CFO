"""Phase 30h — add parent_id to categories for sub-category hierarchy.

The taxonomy is currently FLAT: every category is a top-level name
inside a ``group`` (Income / Expenses / Debt / Investments / Transfer).
``parent_id`` (a self-FK) lets a category become a SUB-CATEGORY of
another one (e.g. ``Coffee Shops`` under ``Food & Dining``), so the
LLM Pass-4 proposal flow can create specific children on demand
without flattening the existing 28 canonical names.

Mirror of the Phase 30g transfer-pairing migration: nullable self-FK
+ index, additive, no data back-fill (existing rows are all parents;
new sub-categories are created lazily by the accept-proposal flow).

Revision ID: U3e4f5a6b7c8
Revises: T2f3a4b5c6d7
Create Date: 2026-08-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "U3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "T2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add parent_id column + self-FK + index to categories."""
    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("parent_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_categories_parent",
            "categories",
            ["parent_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_categories_parent_id",
            ["parent_id"],
            unique=False,
        )


def downgrade() -> None:
    """Remove the hierarchy column."""
    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.drop_index("ix_categories_parent_id")
        batch_op.drop_constraint("fk_categories_parent", type_="foreignkey")
        batch_op.drop_column("parent_id")
