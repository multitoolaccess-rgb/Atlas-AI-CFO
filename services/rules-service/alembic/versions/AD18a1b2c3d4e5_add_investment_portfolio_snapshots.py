"""Add the immutable owner-scoped INV-12 portfolio-snapshot store.

Revision ID: AD18a1b2c3d4e5
Revises: AC17a1b2c3d4e5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "AD18a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "AC17a1b2c3d4e5"
branch_labels = None
depends_on = None

TABLE = "investment_portfolio_snapshots"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("snapshot_id", sa.String(160), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("owner_id", "snapshot_hash", name="uq_investment_portfolio_snapshots_owner_hash"),
        sa.CheckConstraint("length(snapshot_id) BETWEEN 1 AND 160", name="ck_investment_portfolio_snapshots_id"),
        sa.CheckConstraint("length(snapshot_hash) = 64 AND snapshot_hash = lower(snapshot_hash)", name="ck_investment_portfolio_snapshots_hash"),
    )
    op.create_index("ix_investment_portfolio_snapshots_owner_id", TABLE, ["owner_id"])
    op.create_index("ix_investment_portfolio_snapshots_as_of", TABLE, ["as_of"])
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(f"CREATE TRIGGER {TABLE}_no_update BEFORE UPDATE ON {TABLE} BEGIN SELECT RAISE(ABORT, '{TABLE} are immutable'); END")
        op.execute(f"CREATE TRIGGER {TABLE}_no_delete BEFORE DELETE ON {TABLE} BEGIN SELECT RAISE(ABORT, '{TABLE} are immutable'); END")
    elif bind.dialect.name == "postgresql":
        op.execute(f"CREATE FUNCTION reject_{TABLE}_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION '{TABLE} are immutable'; END; $$ LANGUAGE plpgsql")
        op.execute(f"CREATE TRIGGER {TABLE}_no_update BEFORE UPDATE ON {TABLE} FOR EACH ROW EXECUTE FUNCTION reject_{TABLE}_mutation()")
        op.execute(f"CREATE TRIGGER {TABLE}_no_delete BEFORE DELETE ON {TABLE} FOR EACH ROW EXECUTE FUNCTION reject_{TABLE}_mutation()")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE}")).scalar_one():
        raise RuntimeError(f"cannot downgrade non-empty immutable {TABLE}")
    if bind.dialect.name == "sqlite":
        op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_no_update")
        op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_no_delete")
    elif bind.dialect.name == "postgresql":
        op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_no_update ON {TABLE}")
        op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_no_delete ON {TABLE}")
        op.execute(f"DROP FUNCTION IF EXISTS reject_{TABLE}_mutation()")
    op.drop_index("ix_investment_portfolio_snapshots_as_of", table_name=TABLE)
    op.drop_index("ix_investment_portfolio_snapshots_owner_id", table_name=TABLE)
    op.drop_table(TABLE)
