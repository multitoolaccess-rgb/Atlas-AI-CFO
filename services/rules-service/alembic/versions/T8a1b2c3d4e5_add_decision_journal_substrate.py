"""Add immutable, user-scoped recommendation and decision-journal substrate.

Revision ID: T8a1b2c3d4e5
Revises: S7a1b2c3d4e5

Phase 2 Slice 1. Per-user, append-only substrate for the deterministic
recommendation derivation ledger (``recommendations`` table) and the
user's append-only decision journal (``decision_journal_entries``
table). Both tables are immutable once written:

* ``BEFORE UPDATE`` and ``BEFORE DELETE`` triggers fail closed.
* Ownership triggers enforce ``recommendation.user_id == goal.user_id``
  and (for journal entries) ``journal_entry.user_id == recommendation.user_id``.
* Format triggers reject non-canonical UUIDs, uppercase SHA-256 hex,
  uppercase letters in ``recommendation_kind``, non-printable characters
  in version strings, and non-(accept/reject/defer) decision actions.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "T8a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "S7a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Immutability triggers: BEFORE UPDATE / DELETE must fail closed on both
# tables so the substrate is append-only.
# ---------------------------------------------------------------------------


def _create_immutability_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            """CREATE TRIGGER recommendations_no_update BEFORE UPDATE ON recommendations
            BEGIN SELECT RAISE(ABORT, 'recommendations are immutable'); END"""
        )
        op.execute(
            """CREATE TRIGGER recommendations_no_delete BEFORE DELETE ON recommendations
            BEGIN SELECT RAISE(ABORT, 'recommendations are immutable'); END"""
        )
        op.execute(
            """CREATE TRIGGER decision_journal_entries_no_update BEFORE UPDATE ON decision_journal_entries
            BEGIN SELECT RAISE(ABORT, 'decision_journal_entries are immutable'); END"""
        )
        op.execute(
            """CREATE TRIGGER decision_journal_entries_no_delete BEFORE DELETE ON decision_journal_entries
            BEGIN SELECT RAISE(ABORT, 'decision_journal_entries are immutable'); END"""
        )
    elif bind.dialect.name == "postgresql":
        op.execute(
            """CREATE FUNCTION reject_recommendation_mutation() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'recommendations are immutable'; END; $$ LANGUAGE plpgsql"""
        )
        op.execute(
            "CREATE TRIGGER recommendations_no_update BEFORE UPDATE ON recommendations "
            "FOR EACH ROW EXECUTE FUNCTION reject_recommendation_mutation()"
        )
        op.execute(
            "CREATE TRIGGER recommendations_no_delete BEFORE DELETE ON recommendations "
            "FOR EACH ROW EXECUTE FUNCTION reject_recommendation_mutation()"
        )
        op.execute(
            """CREATE FUNCTION reject_decision_journal_mutation() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'decision_journal_entries are immutable'; END; $$ LANGUAGE plpgsql"""
        )
        op.execute(
            "CREATE TRIGGER decision_journal_entries_no_update BEFORE UPDATE ON decision_journal_entries "
            "FOR EACH ROW EXECUTE FUNCTION reject_decision_journal_mutation()"
        )
        op.execute(
            "CREATE TRIGGER decision_journal_entries_no_delete BEFORE DELETE ON decision_journal_entries "
            "FOR EACH ROW EXECUTE FUNCTION reject_decision_journal_mutation()"
        )


def _drop_immutability_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER recommendations_no_update")
        op.execute("DROP TRIGGER recommendations_no_delete")
        op.execute("DROP TRIGGER decision_journal_entries_no_update")
        op.execute("DROP TRIGGER decision_journal_entries_no_delete")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER recommendations_no_update ON recommendations")
        op.execute("DROP TRIGGER recommendations_no_delete ON recommendations")
        op.execute("DROP TRIGGER decision_journal_entries_no_update ON decision_journal_entries")
        op.execute("DROP TRIGGER decision_journal_entries_no_delete ON decision_journal_entries")
        op.execute("DROP FUNCTION reject_recommendation_mutation()")
        op.execute("DROP FUNCTION reject_decision_journal_mutation()")


# ---------------------------------------------------------------------------
# Ownership triggers: a recommendation must belong to the user that owns
# its goal; a journal entry must belong to the user that owns both its
# goal AND its recommendation. Bypassing at the SQL layer is impossible
# even with raw INSERT because the BEFORE INSERT trigger fails closed.
# ---------------------------------------------------------------------------


def _create_ownership_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            """CREATE TRIGGER recommendations_goal_owner_insert BEFORE INSERT ON recommendations
                WHEN NEW.user_id != (SELECT user_id FROM goals WHERE id = NEW.goal_id)
                BEGIN SELECT RAISE(ABORT, 'recommendation user must own goal'); END"""
        )
        # UPDATE on recommendations is permanently blocked by the
        # immutability trigger above, so no UPDATE-form ownership trigger
        # is needed here.
        op.execute(
            """CREATE TRIGGER decision_journal_goal_owner_insert BEFORE INSERT ON decision_journal_entries
                WHEN NEW.user_id != (SELECT user_id FROM goals WHERE id = NEW.goal_id)
                   OR NEW.user_id != (SELECT user_id FROM recommendations WHERE id = NEW.recommendation_id)
                BEGIN SELECT RAISE(ABORT, 'decision journal user must own goal and recommendation'); END"""
        )
        # UPDATE blocked by immutability; no UPDATE-form trigger.
    elif bind.dialect.name == "postgresql":
        op.execute(
            """CREATE FUNCTION enforce_recommendation_goal_owner() RETURNS trigger AS $$
            BEGIN IF NEW.user_id != (SELECT user_id FROM goals WHERE id = NEW.goal_id) THEN
                RAISE EXCEPTION 'recommendation user must own goal'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql"""
        )
        op.execute(
            "CREATE TRIGGER recommendations_goal_owner BEFORE INSERT ON recommendations "
            "FOR EACH ROW EXECUTE FUNCTION enforce_recommendation_goal_owner()"
        )
        op.execute(
            """CREATE FUNCTION enforce_decision_journal_owners() RETURNS trigger AS $$
            BEGIN IF NEW.user_id != (SELECT user_id FROM goals WHERE id = NEW.goal_id)
                   OR NEW.user_id != (SELECT user_id FROM recommendations WHERE id = NEW.recommendation_id) THEN
                RAISE EXCEPTION 'decision journal user must own goal and recommendation'; END IF;
            RETURN NEW; END; $$ LANGUAGE plpgsql"""
        )
        op.execute(
            "CREATE TRIGGER decision_journal_owners BEFORE INSERT ON decision_journal_entries "
            "FOR EACH ROW EXECUTE FUNCTION enforce_decision_journal_owners()"
        )


def _drop_ownership_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER recommendations_goal_owner_insert")
        op.execute("DROP TRIGGER decision_journal_goal_owner_insert")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER recommendations_goal_owner ON recommendations")
        op.execute("DROP FUNCTION enforce_recommendation_goal_owner()")
        op.execute("DROP TRIGGER decision_journal_owners ON decision_journal_entries")
        op.execute("DROP FUNCTION enforce_decision_journal_owners()")


# ---------------------------------------------------------------------------
# Format guards: canonical UUID, lowercase SHA-256 hex, snake_case
# recommendation_kind, ASCII-printable version strings, decision_action
# enum, currency = USD.
# ---------------------------------------------------------------------------


def _create_format_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            """CREATE TRIGGER recommendations_id_format_insert BEFORE INSERT ON recommendations
              WHEN length(NEW.id) != 36 OR NEW.id != lower(NEW.id)
                OR NEW.id NOT GLOB '????????-????-????-????-????????????'
                OR substr(NEW.id, 1, 8) GLOB '*[^0-9a-f]*'
                OR substr(NEW.id, 10, 4) GLOB '*[^0-9a-f]*'
                OR substr(NEW.id, 15, 4) GLOB '*[^0-9a-f]*'
                OR substr(NEW.id, 20, 4) GLOB '*[^0-9a-f]*'
                OR substr(NEW.id, 25, 12) GLOB '*[^0-9a-f]*'
                OR length(NEW.forecast_version_id) != 36 OR NEW.forecast_version_id != lower(NEW.forecast_version_id)
                OR NEW.forecast_version_id NOT GLOB '????????-????-????-????-????????????'
                OR NEW.forecast_input_state_hash GLOB '*[^0-9a-f]*'
                OR NEW.recommendation_kind NOT GLOB '[a-z][a-z_]*'
                OR length(NEW.recommendation_kind) < 2
                OR length(NEW.recommendation_kind) > 64
                OR length(NEW.rule_version) < 1 OR length(NEW.rule_version) > 64
                OR NEW.rule_version GLOB '*[^!-~]*'
                OR length(NEW.derivation_schema_version) < 1
                OR length(NEW.derivation_schema_version) > 64
                OR NEW.derivation_schema_version GLOB '*[^!-~]*'
                OR NEW.currency != 'USD'
              BEGIN SELECT RAISE(ABORT, 'recommendation values must be canonical'); END"""
        )
        op.execute(
            """CREATE TRIGGER decision_journal_entries_format_insert BEFORE INSERT ON decision_journal_entries
              WHEN length(NEW.id) != 36 OR NEW.id != lower(NEW.id)
                OR NEW.id NOT GLOB '????????-????-????-????-????????????'
                OR substr(NEW.id, 1, 8) GLOB '*[^0-9a-f]*'
                OR substr(NEW.id, 10, 4) GLOB '*[^0-9a-f]*'
                OR substr(NEW.id, 15, 4) GLOB '*[^0-9a-f]*'
                OR substr(NEW.id, 20, 4) GLOB '*[^0-9a-f]*'
                OR substr(NEW.id, 25, 12) GLOB '*[^0-9a-f]*'
                OR length(NEW.recommendation_id) != 36 OR NEW.recommendation_id != lower(NEW.recommendation_id)
                OR NEW.recommendation_id NOT GLOB '????????-????-????-????-????????????'
                OR NEW.decision_action NOT IN ('accept', 'reject', 'defer')
                OR length(NEW.idempotency_key_hash) != 64
                OR NEW.idempotency_key_hash GLOB '*[^0-9a-f]*'
                OR length(NEW.schema_version) < 1 OR length(NEW.schema_version) > 64
                OR NEW.schema_version GLOB '*[^!-~]*'
                OR (NEW.note IS NOT NULL AND length(NEW.note) > 2048)
                OR NEW.currency != 'USD'
              BEGIN SELECT RAISE(ABORT, 'decision journal values must be canonical'); END"""
        )
    elif bind.dialect.name == "postgresql":
        # Postgres enforces the same canonical-shape invariants via regular
        # expressions on ADD CONSTRAINT CHECK. The cross-dialect length
        # + lowercase constraints are already declared inline in the
        # table's CREATE TABLE block.
        op.execute(
            "ALTER TABLE recommendations "
            "ADD CONSTRAINT ck_recommendations_id_format "
            "CHECK (id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')"
        )
        op.execute(
            "ALTER TABLE recommendations "
            "ADD CONSTRAINT ck_recommendations_fvid_format "
            "CHECK (forecast_version_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')"
        )
        op.execute(
            "ALTER TABLE recommendations "
            "ADD CONSTRAINT ck_recommendations_input_state_hash_format "
            "CHECK (forecast_input_state_hash ~ '^[0-9a-f]{64}$')"
        )
        op.execute(
            "ALTER TABLE recommendations "
            "ADD CONSTRAINT ck_recommendations_recommendation_kind_format "
            "CHECK (recommendation_kind ~ '^[a-z][a-z_]{1,63}$')"
        )
        op.execute(
            "ALTER TABLE recommendations "
            "ADD CONSTRAINT ck_recommendations_rule_version_format "
            "CHECK (rule_version ~ '^[!-~]{1,64}$')"
        )
        op.execute(
            "ALTER TABLE recommendations "
            "ADD CONSTRAINT ck_recommendations_schema_version_format "
            "CHECK (derivation_schema_version ~ '^[!-~]{1,64}$')"
        )
        op.execute(
            "ALTER TABLE decision_journal_entries "
            "ADD CONSTRAINT ck_decision_journal_id_format "
            "CHECK (id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')"
        )
        op.execute(
            "ALTER TABLE decision_journal_entries "
            "ADD CONSTRAINT ck_decision_journal_recommendation_id_format "
            "CHECK (recommendation_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')"
        )
        op.execute(
            "ALTER TABLE decision_journal_entries "
            "ADD CONSTRAINT ck_decision_journal_idempotency_hash_format "
            "CHECK (idempotency_key_hash ~ '^[0-9a-f]{64}$')"
        )
        op.execute(
            "ALTER TABLE decision_journal_entries "
            "ADD CONSTRAINT ck_decision_journal_action_enum "
            "CHECK (decision_action IN ('accept', 'reject', 'defer'))"
        )
        op.execute(
            "ALTER TABLE decision_journal_entries "
            "ADD CONSTRAINT ck_decision_journal_schema_version_format "
            "CHECK (schema_version ~ '^[!-~]{1,64}$')"
        )


def _drop_format_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER recommendations_id_format_insert")
        op.execute("DROP TRIGGER decision_journal_entries_format_insert")
    elif bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE recommendations DROP CONSTRAINT ck_recommendations_id_format")
        op.execute("ALTER TABLE recommendations DROP CONSTRAINT ck_recommendations_fvid_format")
        op.execute("ALTER TABLE recommendations DROP CONSTRAINT ck_recommendations_input_state_hash_format")
        op.execute("ALTER TABLE recommendations DROP CONSTRAINT ck_recommendations_recommendation_kind_format")
        op.execute("ALTER TABLE recommendations DROP CONSTRAINT ck_recommendations_rule_version_format")
        op.execute("ALTER TABLE recommendations DROP CONSTRAINT ck_recommendations_schema_version_format")
        op.execute("ALTER TABLE decision_journal_entries DROP CONSTRAINT ck_decision_journal_id_format")
        op.execute("ALTER TABLE decision_journal_entries DROP CONSTRAINT ck_decision_journal_recommendation_id_format")
        op.execute("ALTER TABLE decision_journal_entries DROP CONSTRAINT ck_decision_journal_idempotency_hash_format")
        op.execute("ALTER TABLE decision_journal_entries DROP CONSTRAINT ck_decision_journal_action_enum")
        op.execute("ALTER TABLE decision_journal_entries DROP CONSTRAINT ck_decision_journal_schema_version_format")


# ---------------------------------------------------------------------------
# upgrade / downgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("goal_id", sa.Integer(), sa.ForeignKey("goals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "forecast_version_id",
            sa.String(36),
            sa.ForeignKey("forecast_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("forecast_input_state_hash", sa.String(64), nullable=False),
        sa.Column("recommendation_kind", sa.String(64), nullable=False),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column("derivation_schema_version", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("reason", sa.String(1024), nullable=False),
        sa.Column("expected_impact_min_decimal", sa.Numeric(38, 12), nullable=False),
        sa.Column("expected_impact_max_decimal", sa.Numeric(38, 12), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("assumptions_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("risks_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("freshness_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("derived_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "user_id", "goal_id", "forecast_version_id", "recommendation_kind", "rule_version",
            name="uq_recommendations_identity",
        ),
        sa.CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_recommendations_id_shape"),
        sa.CheckConstraint(
            "length(forecast_version_id) = 36 AND forecast_version_id = lower(forecast_version_id)",
            name="ck_recommendations_forecast_version_id_shape",
        ),
        sa.CheckConstraint(
            "length(forecast_input_state_hash) = 64",
            name="ck_recommendations_input_state_hash_length",
        ),
        sa.CheckConstraint(
            "forecast_input_state_hash = lower(forecast_input_state_hash)",
            name="ck_recommendations_input_state_hash_lower",
        ),
        sa.CheckConstraint(
            "length(recommendation_kind) BETWEEN 2 AND 64",
            name="ck_recommendations_recommendation_kind_length",
        ),
        sa.CheckConstraint(
            "length(rule_version) BETWEEN 1 AND 64",
            name="ck_recommendations_rule_version_length",
        ),
        sa.CheckConstraint(
            "length(derivation_schema_version) BETWEEN 1 AND 64",
            name="ck_recommendations_schema_version_length",
        ),
        sa.CheckConstraint("currency = 'USD'", name="ck_recommendations_currency"),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_recommendations_confidence_range",
        ),
        sa.CheckConstraint(
            "expected_impact_min_decimal <= expected_impact_max_decimal",
            name="ck_recommendations_impact_ordering",
        ),
        sa.CheckConstraint(
            "length(reason) BETWEEN 1 AND 1024",
            name="ck_recommendations_reason_length",
        ),
    )
    op.create_index("ix_recommendations_user_id", "recommendations", ["user_id"])
    op.create_index("ix_recommendations_goal_id", "recommendations", ["goal_id"])
    op.create_index("ix_recommendations_forecast_version_id", "recommendations", ["forecast_version_id"])

    op.create_table(
        "decision_journal_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "recommendation_id",
            sa.String(36),
            sa.ForeignKey("recommendations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("goal_id", sa.Integer(), sa.ForeignKey("goals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("decision_action", sa.String(16), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("note", sa.String(2048), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "user_id", "goal_id", "recommendation_id", "idempotency_key_hash",
            name="uq_decision_journal_idempotency",
        ),
        sa.CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_decision_journal_id_shape"),
        sa.CheckConstraint(
            "length(recommendation_id) = 36 AND recommendation_id = lower(recommendation_id)",
            name="ck_decision_journal_recommendation_id_shape",
        ),
        sa.CheckConstraint(
            "length(idempotency_key_hash) = 64",
            name="ck_decision_journal_idempotency_hash_length",
        ),
        sa.CheckConstraint(
            "idempotency_key_hash = lower(idempotency_key_hash)",
            name="ck_decision_journal_idempotency_hash_lower",
        ),
        sa.CheckConstraint(
            "decision_action IN ('accept', 'reject', 'defer')",
            name="ck_decision_journal_action_enum",
        ),
        sa.CheckConstraint(
            "length(schema_version) BETWEEN 1 AND 64",
            name="ck_decision_journal_schema_version_length",
        ),
        sa.CheckConstraint("currency = 'USD'", name="ck_decision_journal_currency"),
        sa.CheckConstraint(
            "note IS NULL OR length(note) <= 2048",
            "ck_decision_journal_note_length",
        ),
    )
    op.create_index("ix_decision_journal_recommendation_id", "decision_journal_entries", ["recommendation_id"])
    op.create_index("ix_decision_journal_user_id", "decision_journal_entries", ["user_id"])
    op.create_index("ix_decision_journal_goal_id", "decision_journal_entries", ["goal_id"])

    _create_ownership_guards()
    _create_immutability_guards()
    if bind.dialect.name == "postgresql":
        # Postgres CHECK constraints must be added BEFORE any data so the
        # ordering of format guards is correct. SQLite uses triggers
        # which are added below.
        _create_format_guards()
    if bind.dialect.name == "sqlite":
        _create_format_guards()


def downgrade() -> None:
    bind = op.get_bind()
    rec_count = bind.execute(sa.text("SELECT COUNT(*) FROM recommendations")).scalar_one()
    journal_count = bind.execute(sa.text("SELECT COUNT(*) FROM decision_journal_entries")).scalar_one()
    if rec_count or journal_count:
        raise RuntimeError(
            "cannot downgrade immutable decision.journal substrate while "
            "recommendation or journal rows exist"
        )
    if bind.dialect.name == "postgresql":
        _drop_format_guards()
    _drop_immutability_guards()
    _drop_ownership_guards()
    if bind.dialect.name == "sqlite":
        _drop_format_guards()
    op.drop_index("ix_decision_journal_goal_id", table_name="decision_journal_entries")
    op.drop_index("ix_decision_journal_user_id", table_name="decision_journal_entries")
    op.drop_index("ix_decision_journal_recommendation_id", table_name="decision_journal_entries")
    op.drop_table("decision_journal_entries")
    op.drop_index("ix_recommendations_forecast_version_id", table_name="recommendations")
    op.drop_index("ix_recommendations_goal_id", table_name="recommendations")
    op.drop_index("ix_recommendations_user_id", table_name="recommendations")
    op.drop_table("recommendations")
