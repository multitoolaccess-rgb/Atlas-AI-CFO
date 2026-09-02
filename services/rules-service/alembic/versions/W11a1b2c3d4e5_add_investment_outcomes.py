"""Add immutable investment outcome records.

Revision ID: W11a1b2c3d4e5
Revises: V10a1b2c3d4e5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "W11a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "V10a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investment_outcome_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("recommendation_record_id", sa.Integer(), sa.ForeignKey("investment_recommendation_records.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("outcome_id", sa.String(160), nullable=False),
        sa.Column("recommendation_id", sa.String(160), nullable=False),
        sa.Column("recommendation_hash", sa.String(64), nullable=False),
        sa.Column("evaluation_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome_hash", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("owner_id", "outcome_id", name="uq_investment_outcomes_owner_outcome"),
        sa.CheckConstraint("length(outcome_id) BETWEEN 1 AND 160", name="ck_investment_outcomes_id"),
        sa.CheckConstraint("length(outcome_hash) = 64 AND outcome_hash = lower(outcome_hash)", name="ck_investment_outcomes_hash"),
    )
    op.create_index("ix_investment_outcome_records_owner_id", "investment_outcome_records", ["owner_id"])
    op.create_index("ix_investment_outcome_records_recommendation_record_id", "investment_outcome_records", ["recommendation_record_id"])
    op.create_index("ix_investment_outcome_records_recommendation_id", "investment_outcome_records", ["recommendation_id"])
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("CREATE TRIGGER investment_outcome_records_no_update BEFORE UPDATE ON investment_outcome_records BEGIN SELECT RAISE(ABORT, 'investment_outcome_records are immutable'); END")
        op.execute("CREATE TRIGGER investment_outcome_records_no_delete BEFORE DELETE ON investment_outcome_records BEGIN SELECT RAISE(ABORT, 'investment_outcome_records are immutable'); END")
    elif bind.dialect.name == "postgresql":
        op.execute("CREATE FUNCTION reject_investment_outcome_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'investment_outcome_records are immutable'; END; $$ LANGUAGE plpgsql")
        op.execute("CREATE TRIGGER investment_outcome_records_no_update BEFORE UPDATE ON investment_outcome_records FOR EACH ROW EXECUTE FUNCTION reject_investment_outcome_mutation()")
        op.execute("CREATE TRIGGER investment_outcome_records_no_delete BEFORE DELETE ON investment_outcome_records FOR EACH ROW EXECUTE FUNCTION reject_investment_outcome_mutation()")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM investment_outcome_records")).scalar_one():
        raise RuntimeError("cannot downgrade non-empty immutable investment outcomes")
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS investment_outcome_records_no_update")
        op.execute("DROP TRIGGER IF EXISTS investment_outcome_records_no_delete")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS investment_outcome_records_no_update ON investment_outcome_records")
        op.execute("DROP TRIGGER IF EXISTS investment_outcome_records_no_delete ON investment_outcome_records")
        op.execute("DROP FUNCTION IF EXISTS reject_investment_outcome_mutation()")
    op.drop_index("ix_investment_outcome_records_recommendation_id", table_name="investment_outcome_records")
    op.drop_index("ix_investment_outcome_records_recommendation_record_id", table_name="investment_outcome_records")
    op.drop_index("ix_investment_outcome_records_owner_id", table_name="investment_outcome_records")
    op.drop_table("investment_outcome_records")
