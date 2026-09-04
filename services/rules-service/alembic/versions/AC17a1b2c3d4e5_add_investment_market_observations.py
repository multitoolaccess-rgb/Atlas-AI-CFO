"""Add the immutable durable INV-12 market-observation store.

Revision ID: AC17a1b2c3d4e5
Revises: AB16a1b2c3d4e5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "AC17a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "AB16a1b2c3d4e5"
branch_labels = None
depends_on = None

TABLE = "investment_market_observations"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("observation_id", sa.String(160), nullable=False),
        sa.Column("security_id", sa.String(128), nullable=False),
        sa.Column("observed_value", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("adjustment_basis", sa.String(32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(160), nullable=False),
        sa.Column("source_identifier", sa.String(160), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("quality", sa.String(16), nullable=False),
        sa.Column("freshness", sa.String(16), nullable=False),
        sa.Column("observation_hash", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("observation_id", name="uq_investment_market_observations_id"),
        sa.CheckConstraint("length(observation_id) BETWEEN 1 AND 160", name="ck_investment_market_observations_id"),
        sa.CheckConstraint("length(observation_hash) = 64 AND observation_hash = lower(observation_hash)", name="ck_investment_market_observations_hash"),
        sa.CheckConstraint("length(security_id) BETWEEN 1 AND 128", name="ck_investment_market_observations_security"),
        sa.CheckConstraint("currency = upper(currency) AND length(currency) = 3", name="ck_investment_market_observations_currency"),
        sa.CheckConstraint("state IN ('unknown', 'missing', 'stale', 'estimated', 'observed')", name="ck_investment_market_observations_state"),
        sa.CheckConstraint("freshness IN ('unknown', 'missing', 'stale', 'estimated', 'observed')", name="ck_investment_market_observations_freshness"),
        sa.CheckConstraint("quality IN ('validated', 'partial', 'invalid')", name="ck_investment_market_observations_quality"),
        sa.CheckConstraint("adjustment_basis IN ('unadjusted', 'split_adjusted', 'total_return_adjusted', 'unknown')", name="ck_investment_market_observations_basis"),
    )
    op.create_index("ix_investment_market_observations_security_id", TABLE, ["security_id"])
    op.create_index("ix_investment_market_observations_observed_at", TABLE, ["observed_at"])
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
    op.drop_index("ix_investment_market_observations_observed_at", table_name=TABLE)
    op.drop_index("ix_investment_market_observations_security_id", table_name=TABLE)
    op.drop_table(TABLE)
