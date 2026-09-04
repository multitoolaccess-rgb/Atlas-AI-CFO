"""Add immutable owner-scoped UI-10 Scout runs.

Revision ID: AB16a1b2c3d4e5
Revises: AA15a1b2c3d4e5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "AB16a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "AA15a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investment_scout_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("run_id", sa.String(160), nullable=False),
        sa.Column("security_id", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("owner_id", "run_id", name="uq_investment_scout_runs_owner_run"),
        sa.CheckConstraint("length(run_id) BETWEEN 1 AND 160", name="ck_investment_scout_runs_run_id"),
        sa.CheckConstraint("length(result_hash) = 64 AND result_hash = lower(result_hash)", name="ck_investment_scout_runs_hash"),
        sa.CheckConstraint("length(security_id) BETWEEN 1 AND 128", name="ck_investment_scout_runs_security_id"),
        sa.CheckConstraint("length(symbol) BETWEEN 1 AND 32", name="ck_investment_scout_runs_symbol"),
    )
    op.create_index("ix_investment_scout_runs_owner_id", "investment_scout_runs", ["owner_id"])
    op.create_index("ix_investment_scout_runs_security_id", "investment_scout_runs", ["security_id"])
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("CREATE TRIGGER investment_scout_runs_no_update BEFORE UPDATE ON investment_scout_runs BEGIN SELECT RAISE(ABORT, 'investment_scout_runs are immutable'); END")
        op.execute("CREATE TRIGGER investment_scout_runs_no_delete BEFORE DELETE ON investment_scout_runs BEGIN SELECT RAISE(ABORT, 'investment_scout_runs are immutable'); END")
    elif bind.dialect.name == "postgresql":
        op.execute("CREATE FUNCTION reject_investment_scout_run_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'investment_scout_runs are immutable'; END; $$ LANGUAGE plpgsql")
        op.execute("CREATE TRIGGER investment_scout_runs_no_update BEFORE UPDATE ON investment_scout_runs FOR EACH ROW EXECUTE FUNCTION reject_investment_scout_run_mutation()")
        op.execute("CREATE TRIGGER investment_scout_runs_no_delete BEFORE DELETE ON investment_scout_runs FOR EACH ROW EXECUTE FUNCTION reject_investment_scout_run_mutation()")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM investment_scout_runs")).scalar_one():
        raise RuntimeError("cannot downgrade non-empty immutable Scout runs")
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS investment_scout_runs_no_update")
        op.execute("DROP TRIGGER IF EXISTS investment_scout_runs_no_delete")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS investment_scout_runs_no_update ON investment_scout_runs")
        op.execute("DROP TRIGGER IF EXISTS investment_scout_runs_no_delete ON investment_scout_runs")
        op.execute("DROP FUNCTION IF EXISTS reject_investment_scout_run_mutation()")
    op.drop_index("ix_investment_scout_runs_security_id", table_name="investment_scout_runs")
    op.drop_index("ix_investment_scout_runs_owner_id", table_name="investment_scout_runs")
    op.drop_table("investment_scout_runs")
