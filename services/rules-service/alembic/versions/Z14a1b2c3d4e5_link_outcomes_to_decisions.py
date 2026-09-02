"""Link investment outcomes to optional human investment decisions.

Revision ID: Z14a1b2c3d4e5
Revises: Y13a1b2c3d4e5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "Z14a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "Y13a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("investment_outcome_records", sa.Column("decision_id", sa.String(160), nullable=True))
    op.create_index("ix_investment_outcome_records_decision_id", "investment_outcome_records", ["decision_id"])


def downgrade() -> None:
    op.drop_index("ix_investment_outcome_records_decision_id", table_name="investment_outcome_records")
    op.drop_column("investment_outcome_records", "decision_id")
