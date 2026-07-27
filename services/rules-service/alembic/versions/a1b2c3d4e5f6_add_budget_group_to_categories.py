"""add budget_group to categories

Revision ID: a1b2c3d4e5f6
Revises: 4680ff8dc91e
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "4680ff8dc91e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "categories",
        sa.Column("budget_group", sa.Text(), nullable=False, server_default="flexible"),
    )


def downgrade() -> None:
    op.drop_column("categories", "budget_group")
