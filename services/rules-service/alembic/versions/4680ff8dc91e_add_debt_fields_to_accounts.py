"""add debt fields to accounts

Revision ID: 4680ff8dc91e
Revises:
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "4680ff8dc91e"
down_revision = "M2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("interest_rate", sa.Float(), nullable=True))
    op.add_column("accounts", sa.Column("credit_limit", sa.Float(), nullable=True))
    op.add_column("accounts", sa.Column("minimum_payment", sa.Float(), nullable=True))
    op.add_column("accounts", sa.Column("term_months", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("accounts", "term_months")
    op.drop_column("accounts", "minimum_payment")
    op.drop_column("accounts", "credit_limit")
    op.drop_column("accounts", "interest_rate")
