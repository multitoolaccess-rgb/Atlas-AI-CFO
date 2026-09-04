"""Add the immutable owner-scoped INV-12 evaluation artifact registry.

Revision ID: AE19a1b2c3d4e5
Revises: AD18a1b2c3d4e5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "AE19a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "AD18a1b2c3d4e5"
branch_labels = None
depends_on = None

TABLE = "investment_evaluation_records"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("evaluation_id", sa.String(160), nullable=False),
        sa.Column("recommendation_record_id", sa.Integer(), sa.ForeignKey("investment_recommendation_records.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("recommendation_id", sa.String(160), nullable=False),
        sa.Column("recommendation_hash", sa.String(64), nullable=False),
        sa.Column("decision_record_id", sa.Integer(), sa.ForeignKey("investment_decision_records.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("decision_id", sa.String(160), nullable=True),
        sa.Column("outcome_record_id", sa.Integer(), sa.ForeignKey("investment_outcome_records.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("outcome_id", sa.String(160), nullable=True),
        sa.Column("outcome_hash", sa.String(64), nullable=True),
        sa.Column("security_id", sa.String(128), nullable=False),
        sa.Column("evaluation_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluation_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon", sa.String(8), nullable=False),
        sa.Column("benchmark_security_id", sa.String(128), nullable=True),
        sa.Column("evaluation_state", sa.String(16), nullable=False),
        sa.Column("result_state", sa.String(32), nullable=True),
        sa.Column("methodology_version", sa.String(64), nullable=False),
        sa.Column("vintage_bound", sa.DateTime(timezone=True), nullable=False),
        sa.Column("replay_state", sa.String(32), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("evaluation_hash", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("owner_id", "evaluation_id", name="uq_investment_evaluations_owner_id"),
        sa.CheckConstraint("evaluation_id LIKE 'investment-evaluation:%'", name="ck_investment_evaluations_id"),
        sa.CheckConstraint("length(input_hash) = 64 AND input_hash = lower(input_hash)", name="ck_investment_evaluations_input_hash"),
        sa.CheckConstraint("length(evaluation_hash) = 64 AND evaluation_hash = lower(evaluation_hash)", name="ck_investment_evaluations_hash"),
        sa.CheckConstraint(
            "recommendation_hash IS NOT NULL AND length(recommendation_hash) = 64 AND recommendation_hash = lower(recommendation_hash)",
            name="ck_investment_evaluations_recommendation_hash",
        ),
        sa.CheckConstraint(
            "outcome_hash IS NULL OR (length(outcome_hash) = 64 AND outcome_hash = lower(outcome_hash))",
            name="ck_investment_evaluations_outcome_hash",
        ),
        sa.CheckConstraint("horizon IN ('1D', '1W', '1M', '3M', '6M', '1Y')", name="ck_investment_evaluations_horizon"),
        sa.CheckConstraint("evaluation_state IN ('pending', 'evaluable', 'evaluated', 'blocked')", name="ck_investment_evaluations_state"),
        sa.CheckConstraint(
            "result_state IS NULL OR result_state IN ('available', 'insufficient_history', 'unavailable', 'temporal_violation', 'not_comparable')",
            name="ck_investment_evaluations_result_state",
        ),
        sa.CheckConstraint("replay_state IN ('match', 'methodology_changed', 'inputs_unavailable', 'hash_mismatch')", name="ck_investment_evaluations_replay"),
        sa.CheckConstraint("evaluation_as_of >= evaluation_window_start", name="ck_investment_evaluations_window"),
    )
    op.create_index("ix_investment_evaluation_records_owner_id", TABLE, ["owner_id"])
    op.create_index("ix_investment_evaluation_records_recommendation_record_id", TABLE, ["recommendation_record_id"])
    op.create_index("ix_investment_evaluation_records_security_id", TABLE, ["security_id"])
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
    op.drop_index("ix_investment_evaluation_records_security_id", table_name=TABLE)
    op.drop_index("ix_investment_evaluation_records_recommendation_record_id", table_name=TABLE)
    op.drop_index("ix_investment_evaluation_records_owner_id", table_name=TABLE)
    op.drop_table(TABLE)
