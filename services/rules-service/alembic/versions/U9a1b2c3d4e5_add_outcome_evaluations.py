"""Add append-only Phase 3 outcome evaluations.

Revision ID: U9a1b2c3d4e5
Revises: T8a1b2c3d4e5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "U9a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "T8a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outcome_evaluations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recommendation_id", sa.String(36), sa.ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("decision_journal_entry_id", sa.String(36), sa.ForeignKey("decision_journal_entries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("goal_id", sa.Integer(), sa.ForeignKey("goals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("lifecycle", sa.String(32), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("authoritative_evidence_reference", sa.String(512)),
        sa.Column("measurement_window_start", sa.DateTime(timezone=True)),
        sa.Column("measurement_window_end", sa.DateTime(timezone=True)),
        sa.Column("inputs_json", sa.Text()), sa.Column("result_json", sa.Text()),
        sa.Column("confidence", sa.String(16)), sa.Column("explanation", sa.String(2048)),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("user_id", "idempotency_key_hash", name="uq_outcome_evaluation_idempotency"),
        sa.CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_outcome_evaluation_id_shape"),
        sa.CheckConstraint("length(recommendation_id) = 36 AND recommendation_id = lower(recommendation_id)", name="ck_outcome_evaluation_recommendation_id_shape"),
        sa.CheckConstraint("length(decision_journal_entry_id) = 36 AND decision_journal_entry_id = lower(decision_journal_entry_id)", name="ck_outcome_evaluation_decision_id_shape"),
        sa.CheckConstraint("length(idempotency_key_hash) = 64 AND idempotency_key_hash = lower(idempotency_key_hash)", name="ck_outcome_evaluation_idempotency_hash"),
        sa.CheckConstraint("lifecycle IN ('pending', 'not_yet_measurable', 'measured')", name="ck_outcome_evaluation_lifecycle"),
        sa.CheckConstraint("currency = 'USD'", name="ck_outcome_evaluation_currency"),
        sa.CheckConstraint("measurement_window_start IS NULL OR measurement_window_end IS NULL OR measurement_window_start <= measurement_window_end", name="ck_outcome_evaluation_window_order"),
        sa.CheckConstraint("lifecycle != 'measured' OR (authoritative_evidence_reference IS NOT NULL AND measurement_window_start IS NOT NULL AND measurement_window_end IS NOT NULL AND inputs_json IS NOT NULL AND result_json IS NOT NULL AND confidence IS NOT NULL AND explanation IS NOT NULL)", name="ck_outcome_evaluation_measured_evidence"),
    )
    op.create_index("ix_outcome_evaluations_recommendation_id", "outcome_evaluations", ["recommendation_id"])
    op.create_index("ix_outcome_evaluations_decision_journal_entry_id", "outcome_evaluations", ["decision_journal_entry_id"])
    op.create_index("ix_outcome_evaluations_user_id", "outcome_evaluations", ["user_id"])
    op.create_index("ix_outcome_evaluations_goal_id", "outcome_evaluations", ["goal_id"])
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("CREATE TRIGGER outcome_evaluations_no_update BEFORE UPDATE ON outcome_evaluations BEGIN SELECT RAISE(ABORT, 'outcome_evaluations are immutable'); END")
        op.execute("CREATE TRIGGER outcome_evaluations_no_delete BEFORE DELETE ON outcome_evaluations BEGIN SELECT RAISE(ABORT, 'outcome_evaluations are immutable'); END")
        op.execute("""CREATE TRIGGER outcome_evaluations_accepted_owner_insert BEFORE INSERT ON outcome_evaluations
        WHEN NEW.user_id != (SELECT user_id FROM goals WHERE id = NEW.goal_id)
          OR NEW.user_id != (SELECT user_id FROM recommendations WHERE id = NEW.recommendation_id)
          OR NEW.recommendation_id != (SELECT recommendation_id FROM decision_journal_entries WHERE id = NEW.decision_journal_entry_id)
          OR NEW.user_id != (SELECT user_id FROM decision_journal_entries WHERE id = NEW.decision_journal_entry_id)
          OR NEW.goal_id != (SELECT goal_id FROM decision_journal_entries WHERE id = NEW.decision_journal_entry_id)
          OR 'accept' != (SELECT decision_action FROM decision_journal_entries WHERE id = NEW.decision_journal_entry_id)
        BEGIN SELECT RAISE(ABORT, 'outcome evaluation requires an accepted owned decision'); END""")
    elif bind.dialect.name == "postgresql":
        op.execute("CREATE FUNCTION reject_outcome_evaluation_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'outcome_evaluations are immutable'; END; $$ LANGUAGE plpgsql")
        op.execute("CREATE TRIGGER outcome_evaluations_no_update BEFORE UPDATE ON outcome_evaluations FOR EACH ROW EXECUTE FUNCTION reject_outcome_evaluation_mutation()")
        op.execute("CREATE TRIGGER outcome_evaluations_no_delete BEFORE DELETE ON outcome_evaluations FOR EACH ROW EXECUTE FUNCTION reject_outcome_evaluation_mutation()")
        op.execute("""CREATE FUNCTION enforce_outcome_evaluation_acceptance() RETURNS trigger AS $$
        BEGIN IF NEW.user_id != (SELECT user_id FROM goals WHERE id = NEW.goal_id)
           OR NEW.user_id != (SELECT user_id FROM recommendations WHERE id = NEW.recommendation_id)
           OR NEW.recommendation_id != (SELECT recommendation_id FROM decision_journal_entries WHERE id = NEW.decision_journal_entry_id)
           OR NEW.user_id != (SELECT user_id FROM decision_journal_entries WHERE id = NEW.decision_journal_entry_id)
           OR NEW.goal_id != (SELECT goal_id FROM decision_journal_entries WHERE id = NEW.decision_journal_entry_id)
           OR 'accept' != (SELECT decision_action FROM decision_journal_entries WHERE id = NEW.decision_journal_entry_id) THEN
           RAISE EXCEPTION 'outcome evaluation requires an accepted owned decision'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql""")
        op.execute("CREATE TRIGGER outcome_evaluations_accepted_owner BEFORE INSERT ON outcome_evaluations FOR EACH ROW EXECUTE FUNCTION enforce_outcome_evaluation_acceptance()")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM outcome_evaluations")).scalar_one():
        raise RuntimeError("outcome evaluation data exists; downgrade would destroy append-only history")
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER outcome_evaluations_accepted_owner_insert")
        op.execute("DROP TRIGGER outcome_evaluations_no_update")
        op.execute("DROP TRIGGER outcome_evaluations_no_delete")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER outcome_evaluations_accepted_owner ON outcome_evaluations")
        op.execute("DROP TRIGGER outcome_evaluations_no_update ON outcome_evaluations")
        op.execute("DROP TRIGGER outcome_evaluations_no_delete ON outcome_evaluations")
        op.execute("DROP FUNCTION reject_outcome_evaluation_mutation()")
        op.execute("DROP FUNCTION enforce_outcome_evaluation_acceptance()")
    op.drop_table("outcome_evaluations")
