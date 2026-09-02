"""Enforce investment evidence and outcome linkage foreign keys.

Revision ID: AA15a1b2c3d4e5
Revises: Z14a1b2c3d4e5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "AA15a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "Z14a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if bind.dialect.name == "sqlite":
        # SQLite cannot add/drop constraints without table recreation; the
        # application and link tables already enforce these relationships.
        return
    if "investment_committee_runs" in tables:
        op.create_foreign_key(
            "fk_investment_committee_runs_evidence_packet",
            "investment_committee_runs",
            "investment_evidence_packets",
            ["evidence_packet_id"],
            ["packet_id"],
            ondelete="RESTRICT",
        )
    if "investment_outcome_records" in tables:
        op.create_foreign_key(
            "fk_investment_outcomes_decision",
            "investment_outcome_records",
            "investment_decision_records",
            ["decision_id"],
            ["decision_id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    op.drop_constraint("fk_investment_outcomes_decision", "investment_outcome_records", type_="foreignkey")
    op.drop_constraint("fk_investment_committee_runs_evidence_packet", "investment_committee_runs", type_="foreignkey")
