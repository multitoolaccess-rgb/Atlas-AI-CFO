"""Add bounded market-brief delivery preference and immutable attempts.
Revision ID: N5a6b7c8d9e0
Revises: M5a6b7c8d9e0
"""
from alembic import op
import sqlalchemy as sa
revision = "N5a6b7c8d9e0"
down_revision = "M5a6b7c8d9e0"
branch_labels = None
depends_on = None
def upgrade() -> None:
    op.create_table("market_brief_delivery_preferences", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("email_authorized", sa.Boolean(), nullable=False, server_default=sa.text("false")), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.UniqueConstraint("user_id", name="uq_market_brief_delivery_preference_user"))
    op.create_table("market_brief_delivery_attempts", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("brief_id", sa.String(36), sa.ForeignKey("market_briefs.id", ondelete="RESTRICT"), nullable=False), sa.Column("idempotency_key", sa.String(128), nullable=False), sa.Column("status", sa.String(16), nullable=False), sa.Column("receipt", sa.String(160)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.UniqueConstraint("user_id", "brief_id", "idempotency_key", name="uq_market_brief_delivery_attempt_idempotency"), sa.CheckConstraint("status IN ('previewed', 'sent', 'failed')", name="ck_market_brief_delivery_status"))
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("CREATE TRIGGER market_brief_delivery_attempts_no_update BEFORE UPDATE ON market_brief_delivery_attempts BEGIN SELECT RAISE(ABORT, 'delivery attempts are immutable'); END")
        op.execute("CREATE TRIGGER market_brief_delivery_attempts_no_delete BEFORE DELETE ON market_brief_delivery_attempts BEGIN SELECT RAISE(ABORT, 'delivery attempts are immutable'); END")
    elif bind.dialect.name == "postgresql":
        op.execute("CREATE FUNCTION reject_market_brief_delivery_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'delivery attempts are immutable'; END; $$ LANGUAGE plpgsql")
        op.execute("CREATE TRIGGER market_brief_delivery_attempts_no_update BEFORE UPDATE ON market_brief_delivery_attempts FOR EACH ROW EXECUTE FUNCTION reject_market_brief_delivery_mutation()")
        op.execute("CREATE TRIGGER market_brief_delivery_attempts_no_delete BEFORE DELETE ON market_brief_delivery_attempts FOR EACH ROW EXECUTE FUNCTION reject_market_brief_delivery_mutation()")
def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM market_brief_delivery_attempts")).scalar_one() or bind.execute(sa.text("SELECT COUNT(*) FROM market_brief_delivery_preferences")).scalar_one():
        raise RuntimeError("cannot downgrade market brief delivery state while records exist")
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER market_brief_delivery_attempts_no_update")
        op.execute("DROP TRIGGER market_brief_delivery_attempts_no_delete")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER market_brief_delivery_attempts_no_update ON market_brief_delivery_attempts")
        op.execute("DROP TRIGGER market_brief_delivery_attempts_no_delete ON market_brief_delivery_attempts")
        op.execute("DROP FUNCTION reject_market_brief_delivery_mutation()")
    op.drop_table("market_brief_delivery_attempts"); op.drop_table("market_brief_delivery_preferences")
