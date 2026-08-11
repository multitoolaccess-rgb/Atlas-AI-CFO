"""Add immutable owner-scoped market brief records.

Revision ID: M5a6b7c8d9e0
Revises: V0a1b2c3d4e5
"""
from alembic import op
import sqlalchemy as sa

revision = "M5a6b7c8d9e0"
down_revision = "V0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("market_briefs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("portfolio_state_hash", sa.String(64), nullable=False),
        sa.Column("universe_hash", sa.String(64), nullable=False),
        sa.Column("report_window", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("calculation_version", sa.String(64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "portfolio_state_hash", "universe_hash", "report_window", "schema_version", "calculation_version", name="uq_market_briefs_idempotency"),
        sa.CheckConstraint("length(portfolio_state_hash) = 64", name="ck_market_brief_state_hash"),
        sa.CheckConstraint("length(universe_hash) = 64", name="ck_market_brief_universe_hash"),
    )
    op.create_index("ix_market_briefs_user_id", "market_briefs", ["user_id"])
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("CREATE TRIGGER market_briefs_no_update BEFORE UPDATE ON market_briefs BEGIN SELECT RAISE(ABORT, 'market briefs are immutable'); END")
        op.execute("CREATE TRIGGER market_briefs_no_delete BEFORE DELETE ON market_briefs BEGIN SELECT RAISE(ABORT, 'market briefs are immutable'); END")
    elif bind.dialect.name == "postgresql":
        op.execute("CREATE FUNCTION reject_market_brief_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'market briefs are immutable'; END; $$ LANGUAGE plpgsql")
        op.execute("CREATE TRIGGER market_briefs_no_update BEFORE UPDATE ON market_briefs FOR EACH ROW EXECUTE FUNCTION reject_market_brief_mutation()")
        op.execute("CREATE TRIGGER market_briefs_no_delete BEFORE DELETE ON market_briefs FOR EACH ROW EXECUTE FUNCTION reject_market_brief_mutation()")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM market_briefs")).scalar_one():
        raise RuntimeError("cannot downgrade immutable market brief records while rows exist")
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER market_briefs_no_update")
        op.execute("DROP TRIGGER market_briefs_no_delete")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER market_briefs_no_update ON market_briefs")
        op.execute("DROP TRIGGER market_briefs_no_delete ON market_briefs")
        op.execute("DROP FUNCTION reject_market_brief_mutation()")
    op.drop_index("ix_market_briefs_user_id", table_name="market_briefs")
    op.drop_table("market_briefs")
