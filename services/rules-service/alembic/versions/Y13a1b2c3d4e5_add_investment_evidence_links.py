"""Add explicit investment evidence relationships.

Revision ID: Y13a1b2c3d4e5
Revises: X12a1b2c3d4e5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "Y13a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "X12a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investment_recommendation_evidence_links",
        sa.Column("recommendation_record_id", sa.Integer(), sa.ForeignKey("investment_recommendation_records.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("evidence_packet_id", sa.Integer(), sa.ForeignKey("investment_evidence_packets.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("recommendation_record_id", "evidence_packet_id", name="uq_investment_recommendation_evidence"),
    )
    op.create_index("ix_investment_recommendation_evidence_links_owner_id", "investment_recommendation_evidence_links", ["owner_id"])
    op.create_table(
        "investment_committee_evidence_links",
        sa.Column("finding_record_id", sa.Integer(), sa.ForeignKey("investment_committee_findings.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("evidence_packet_id", sa.Integer(), sa.ForeignKey("investment_evidence_packets.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("finding_record_id", "evidence_packet_id", name="uq_investment_committee_evidence"),
    )
    op.create_index("ix_investment_committee_evidence_links_owner_id", "investment_committee_evidence_links", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_investment_committee_evidence_links_owner_id", table_name="investment_committee_evidence_links")
    op.drop_table("investment_committee_evidence_links")
    op.drop_index("ix_investment_recommendation_evidence_links_owner_id", table_name="investment_recommendation_evidence_links")
    op.drop_table("investment_recommendation_evidence_links")
