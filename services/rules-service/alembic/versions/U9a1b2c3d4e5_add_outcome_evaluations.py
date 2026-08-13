"""Add immutable outcome evaluation records for accepted decisions.

Revision ID: U9a1b2c3d4e5
Revises: T8a1b2c3d4e5

Phase 3 Slice 1. Append-only outcome evaluation substrate linked to
accepted recommendations and decisions. Privacy-safe evidence contract:
allowlisted ``evidence_source_kind`` enum + hash-only
``evidence_reference_hash`` (no raw URLs, filenames, or identifiers).

* ``BEFORE UPDATE`` and ``BEFORE DELETE`` triggers fail closed.
* Ownership triggers enforce ``evaluation.user_id == goal.user_id``,
  ``evaluation.user_id == recommendation.user_id``, and
  ``evaluation.user_id == decision_journal_entry.user_id``.
* Format triggers reject non-canonical UUIDs, uppercase SHA-256 hex,
  non-allowlisted evidence_source_kind, lifecycle states, and confidence.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "U9a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "T8a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Immutability triggers: BEFORE UPDATE / DELETE must fail closed so the
# outcome evaluation substrate is append-only.
# ---------------------------------------------------------------------------


def _create_immutability_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            """CREATE TRIGGER outcome_evaluations_no_update BEFORE UPDATE ON outcome_evaluations
            BEGIN SELECT RAISE(ABORT, 'outcome_evaluations are immutable'); END"""
        )
        op.execute(
            """CREATE TRIGGER outcome_evaluations_no_delete BEFORE DELETE ON outcome_evaluations
            BEGIN SELECT RAISE(ABORT, 'outcome_evaluations are immutable'); END"""
        )
    elif bind.dialect.name == "postgresql":
        op.execute(
            """CREATE FUNCTION reject_outcome_evaluation_mutation() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'outcome_evaluations are immutable'; END; $$ LANGUAGE plpgsql"""
        )
        op.execute(
            "CREATE TRIGGER outcome_evaluations_no_update BEFORE UPDATE ON outcome_evaluations "
            "FOR EACH ROW EXECUTE FUNCTION reject_outcome_evaluation_mutation()"
        )
        op.execute(
            "CREATE TRIGGER outcome_evaluations_no_delete BEFORE DELETE ON outcome_evaluations "
            "FOR EACH ROW EXECUTE FUNCTION reject_outcome_evaluation_mutation()"
        )


def _drop_immutability_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS outcome_evaluations_no_update")
        op.execute("DROP TRIGGER IF EXISTS outcome_evaluations_no_delete")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS outcome_evaluations_no_update ON outcome_evaluations")
        op.execute("DROP TRIGGER IF EXISTS outcome_evaluations_no_delete ON outcome_evaluations")
        op.execute("DROP FUNCTION IF EXISTS reject_outcome_evaluation_mutation()")


# ---------------------------------------------------------------------------
# Ownership triggers: an outcome evaluation must belong to the user that
# owns its goal, recommendation, and decision journal entry.
# ---------------------------------------------------------------------------


def _create_ownership_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            """CREATE TRIGGER outcome_evaluations_owner_insert BEFORE INSERT ON outcome_evaluations
                WHEN NEW.user_id != (SELECT user_id FROM goals WHERE id = NEW.goal_id)
                   OR NEW.user_id != (SELECT user_id FROM recommendations WHERE id = NEW.recommendation_id)
                   OR NEW.user_id != (SELECT user_id FROM decision_journal_entries WHERE id = NEW.decision_journal_entry_id)
                BEGIN SELECT RAISE(ABORT, 'outcome evaluation user must own goal, recommendation, and decision'); END"""
        )
    elif bind.dialect.name == "postgresql":
        op.execute(
            """CREATE FUNCTION enforce_outcome_evaluation_owners() RETURNS trigger AS $$
            BEGIN IF NEW.user_id != (SELECT user_id FROM goals WHERE id = NEW.goal_id)
                   OR NEW.user_id != (SELECT user_id FROM recommendations WHERE id = NEW.recommendation_id)
                   OR NEW.user_id != (SELECT user_id FROM decision_journal_entries WHERE id = NEW.decision_journal_entry_id) THEN
                RAISE EXCEPTION 'outcome evaluation user must own goal, recommendation, and decision'; END IF;
            RETURN NEW; END; $$ LANGUAGE plpgsql"""
        )
        op.execute(
            "CREATE TRIGGER outcome_evaluations_owners BEFORE INSERT ON outcome_evaluations "
            "FOR EACH ROW EXECUTE FUNCTION enforce_outcome_evaluation_owners()"
        )


def _drop_ownership_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS outcome_evaluations_owner_insert")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS outcome_evaluations_owners ON outcome_evaluations")
        op.execute("DROP FUNCTION IF EXISTS enforce_outcome_evaluation_owners()")


# ---------------------------------------------------------------------------
# Format guards: canonical UUID, lowercase SHA-256 hex, allowlisted enums.
# ---------------------------------------------------------------------------


def _create_format_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            """CREATE TRIGGER outcome_evaluations_format_insert BEFORE INSERT ON outcome_evaluations
              WHEN length(NEW.id) != 36 OR NEW.id != lower(NEW.id)
                OR NEW.id NOT GLOB '????????-????-????-????-????????????'
                OR substr(NEW.id, 1, 8) GLOB '*[^0-9a-f]*'
                OR substr(NEW.id, 10, 4) GLOB '*[^0-9a-f]*'
                OR substr(NEW.id, 15, 4) GLOB '*[^0-9a-f]*'
                OR substr(NEW.id, 20, 4) GLOB '*[^0-9a-f]*'
                OR substr(NEW.id, 25, 12) GLOB '*[^0-9a-f]*'
                OR length(NEW.recommendation_id) != 36 OR NEW.recommendation_id != lower(NEW.recommendation_id)
                OR length(NEW.decision_journal_entry_id) != 36 OR NEW.decision_journal_entry_id != lower(NEW.decision_journal_entry_id)
                OR NEW.idempotency_key_hash GLOB '*[^0-9a-f]*'
                OR length(NEW.idempotency_key_hash) != 64
                OR NEW.lifecycle NOT IN ('pending', 'not_yet_measurable', 'measured')
                OR (NEW.evidence_source_kind IS NOT NULL AND NEW.evidence_source_kind NOT IN ('forecast_projection', 'account_balance_delta', 'transaction_pattern'))
                OR (NEW.evidence_reference_hash IS NOT NULL AND (length(NEW.evidence_reference_hash) != 64 OR NEW.evidence_reference_hash GLOB '*[^0-9a-f]*'))
                OR (NEW.confidence IS NOT NULL AND NEW.confidence NOT IN ('high', 'medium', 'low'))
                OR NEW.currency != 'USD'
                OR length(NEW.schema_version) < 1 OR length(NEW.schema_version) > 64
              BEGIN SELECT RAISE(ABORT, 'outcome evaluation values must be canonical'); END"""
        )
    elif bind.dialect.name == "postgresql":
        op.execute(
            """CREATE FUNCTION enforce_outcome_evaluation_format() RETURNS trigger AS $$
            BEGIN
                IF length(NEW.id) != 36 OR NEW.id != lower(NEW.id)
                    OR NEW.id !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                    OR length(NEW.recommendation_id) != 36 OR NEW.recommendation_id != lower(NEW.recommendation_id)
                    OR length(NEW.decision_journal_entry_id) != 36 OR NEW.decision_journal_entry_id != lower(NEW.decision_journal_entry_id)
                    OR NEW.idempotency_key_hash !~ '^[0-9a-f]{64}$'
                    OR NEW.lifecycle NOT IN ('pending', 'not_yet_measurable', 'measured')
                    OR (NEW.evidence_source_kind IS NOT NULL AND NEW.evidence_source_kind NOT IN ('forecast_projection', 'account_balance_delta', 'transaction_pattern'))
                    OR (NEW.evidence_reference_hash IS NOT NULL AND NEW.evidence_reference_hash !~ '^[0-9a-f]{64}$')
                    OR (NEW.confidence IS NOT NULL AND NEW.confidence NOT IN ('high', 'medium', 'low'))
                    OR NEW.currency != 'USD'
                    OR length(NEW.schema_version) < 1 OR length(NEW.schema_version) > 64
                THEN RAISE EXCEPTION 'outcome evaluation values must be canonical'; END IF;
            RETURN NEW; END; $$ LANGUAGE plpgsql"""
        )
        op.execute(
            "CREATE TRIGGER outcome_evaluations_format BEFORE INSERT ON outcome_evaluations "
            "FOR EACH ROW EXECUTE FUNCTION enforce_outcome_evaluation_format()"
        )


def _drop_format_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS outcome_evaluations_format_insert")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS outcome_evaluations_format ON outcome_evaluations")
        op.execute("DROP FUNCTION IF EXISTS enforce_outcome_evaluation_format()")


def upgrade() -> None:
    """Add outcome_evaluations table with append-only immutability."""
    op.create_table(
        "outcome_evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recommendation_id", sa.String(length=36), nullable=False),
        sa.Column("decision_journal_entry_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=False),
        sa.Column("lifecycle", sa.String(length=32), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("evidence_source_kind", sa.String(length=64), nullable=True),
        sa.Column("evidence_reference_hash", sa.String(length=64), nullable=True),
        sa.Column("measurement_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("measurement_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.Column("explanation", sa.String(length=2048), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_outcome_evaluation_id_shape"),
        sa.CheckConstraint(
            "length(recommendation_id) = 36 AND recommendation_id = lower(recommendation_id)",
            name="ck_outcome_evaluation_recommendation_id_shape",
        ),
        sa.CheckConstraint(
            "length(decision_journal_entry_id) = 36 AND decision_journal_entry_id = lower(decision_journal_entry_id)",
            name="ck_outcome_evaluation_decision_id_shape",
        ),
        sa.CheckConstraint(
            "length(idempotency_key_hash) = 64 AND idempotency_key_hash = lower(idempotency_key_hash)",
            name="ck_outcome_evaluation_idempotency_hash",
        ),
        sa.CheckConstraint(
            "lifecycle IN ('pending', 'not_yet_measurable', 'measured')",
            name="ck_outcome_evaluation_lifecycle",
        ),
        sa.CheckConstraint(
            "evidence_source_kind IS NULL OR evidence_source_kind IN ('forecast_projection', 'account_balance_delta', 'transaction_pattern')",
            name="ck_outcome_evaluation_evidence_source_kind",
        ),
        sa.CheckConstraint(
            "evidence_reference_hash IS NULL OR (length(evidence_reference_hash) = 64 AND evidence_reference_hash = lower(evidence_reference_hash))",
            name="ck_outcome_evaluation_evidence_reference_hash",
        ),
        sa.CheckConstraint("currency = 'USD'", name="ck_outcome_evaluation_currency"),
        sa.CheckConstraint(
            "length(schema_version) BETWEEN 1 AND 64",
            name="ck_outcome_evaluation_schema_version_length",
        ),
        sa.CheckConstraint(
            "measurement_window_start IS NULL OR measurement_window_end IS NULL OR measurement_window_start <= measurement_window_end",
            name="ck_outcome_evaluation_window_order",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence IN ('high', 'medium', 'low')",
            name="ck_outcome_evaluation_confidence_enum",
        ),
        sa.CheckConstraint(
            "explanation IS NULL OR length(explanation) <= 2048",
            name="ck_outcome_evaluation_explanation_length",
        ),
        sa.CheckConstraint(
            "(lifecycle = 'measured' AND evidence_source_kind IS NOT NULL AND evidence_reference_hash IS NOT NULL AND measurement_window_start IS NOT NULL AND measurement_window_end IS NOT NULL AND result_json IS NOT NULL AND confidence IS NOT NULL AND explanation IS NOT NULL) OR (lifecycle IN ('pending', 'not_yet_measurable') AND evidence_source_kind IS NULL AND evidence_reference_hash IS NULL AND measurement_window_start IS NULL AND measurement_window_end IS NULL AND result_json IS NULL AND confidence IS NULL AND explanation IS NULL)",
            name="ck_outcome_evaluation_lifecycle_evidence",
        ),
        sa.ForeignKeyConstraint(["decision_journal_entry_id"], ["decision_journal_entries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recommendation_id"], ["recommendations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "recommendation_id", "decision_journal_entry_id", "idempotency_key_hash",
            name="uq_outcome_evaluation_idempotency",
        ),
    )
    op.create_index(op.f("ix_outcome_evaluations_decision_journal_entry_id"), "outcome_evaluations", ["decision_journal_entry_id"], unique=False)
    op.create_index(op.f("ix_outcome_evaluations_goal_id"), "outcome_evaluations", ["goal_id"], unique=False)
    op.create_index(op.f("ix_outcome_evaluations_recommendation_id"), "outcome_evaluations", ["recommendation_id"], unique=False)
    op.create_index(op.f("ix_outcome_evaluations_user_id"), "outcome_evaluations", ["user_id"], unique=False)

    _create_immutability_guards()
    _create_ownership_guards()
    _create_format_guards()


def downgrade() -> None:
    """Drop the outcome_evaluations substrate, refusing once history exists.

    Mirrors the decision-journal substrate pattern: a clean downgrade is
    allowed only while the append-only audit table is empty.
    """
    bind = op.get_bind()
    eval_count = bind.execute(sa.text("SELECT COUNT(*) FROM outcome_evaluations")).scalar_one()
    if eval_count:
        raise RuntimeError(
            "Downgrade refused: outcome_evaluations contain immutable outcome evaluation "
            "history. Dropping this table would destroy audit records."
        )
    if bind.dialect.name == "postgresql":
        _drop_format_guards()
    _drop_immutability_guards()
    _drop_ownership_guards()
    if bind.dialect.name == "sqlite":
        _drop_format_guards()
    op.drop_index(op.f("ix_outcome_evaluations_decision_journal_entry_id"), table_name="outcome_evaluations")
    op.drop_index(op.f("ix_outcome_evaluations_goal_id"), table_name="outcome_evaluations")
    op.drop_index(op.f("ix_outcome_evaluations_recommendation_id"), table_name="outcome_evaluations")
    op.drop_index(op.f("ix_outcome_evaluations_user_id"), table_name="outcome_evaluations")
    op.drop_table("outcome_evaluations")
