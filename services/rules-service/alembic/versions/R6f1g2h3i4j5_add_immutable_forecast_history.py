"""Add immutable, user-scoped forecast identity and version history.

Revision ID: R6f1g2h3i4j5
Revises: Q5h1i2j3k4l5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "R6f1g2h3i4j5"
down_revision: Union[str, Sequence[str], None] = "Q5h1i2j3k4l5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_immutability_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("""CREATE TRIGGER forecast_versions_no_update BEFORE UPDATE ON forecast_versions
            BEGIN SELECT RAISE(ABORT, 'forecast_versions are immutable'); END""")
        op.execute("""CREATE TRIGGER forecast_versions_no_delete BEFORE DELETE ON forecast_versions
            BEGIN SELECT RAISE(ABORT, 'forecast_versions are immutable'); END""")
    elif bind.dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION reject_forecast_version_mutation() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'forecast_versions are immutable'; END; $$ LANGUAGE plpgsql""")
        op.execute("CREATE TRIGGER forecast_versions_no_update BEFORE UPDATE ON forecast_versions FOR EACH ROW EXECUTE FUNCTION reject_forecast_version_mutation()")
        op.execute("CREATE TRIGGER forecast_versions_no_delete BEFORE DELETE ON forecast_versions FOR EACH ROW EXECUTE FUNCTION reject_forecast_version_mutation()")


def _drop_immutability_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER forecast_versions_no_update")
        op.execute("DROP TRIGGER forecast_versions_no_delete")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER forecast_versions_no_update ON forecast_versions")
        op.execute("DROP TRIGGER forecast_versions_no_delete ON forecast_versions")
        op.execute("DROP FUNCTION reject_forecast_version_mutation()")


def _create_ownership_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        for event in ("INSERT", "UPDATE"):
            op.execute(f"""CREATE TRIGGER forecasts_goal_owner_{event.lower()} BEFORE {event} ON forecasts
                WHEN NEW.user_id != (SELECT user_id FROM goals WHERE id = NEW.goal_id)
                BEGIN SELECT RAISE(ABORT, 'forecast user must own goal'); END""")
    elif bind.dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION enforce_forecast_goal_owner() RETURNS trigger AS $$
            BEGIN IF NEW.user_id != (SELECT user_id FROM goals WHERE id = NEW.goal_id) THEN
                RAISE EXCEPTION 'forecast user must own goal'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql""")
        op.execute("CREATE TRIGGER forecasts_goal_owner_insert BEFORE INSERT ON forecasts FOR EACH ROW EXECUTE FUNCTION enforce_forecast_goal_owner()")
        op.execute("CREATE TRIGGER forecasts_goal_owner_update BEFORE UPDATE ON forecasts FOR EACH ROW EXECUTE FUNCTION enforce_forecast_goal_owner()")


def _drop_ownership_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER forecasts_goal_owner_insert")
        op.execute("DROP TRIGGER forecasts_goal_owner_update")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER forecasts_goal_owner_insert ON forecasts")
        op.execute("DROP TRIGGER forecasts_goal_owner_update ON forecasts")
        op.execute("DROP FUNCTION enforce_forecast_goal_owner()")


def upgrade() -> None:
    op.create_table(
        "forecasts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("goal_id", sa.Integer(), sa.ForeignKey("goals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("forecast_kind", sa.String(32), nullable=False, server_default="goal_projection"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("lifecycle_state", sa.String(16), nullable=False, server_default="active"),
        sa.Column("latest_version_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "goal_id", "forecast_kind", "currency", name="uq_forecasts_identity"),
        sa.CheckConstraint("forecast_kind = 'goal_projection'", name="ck_forecasts_kind"),
        sa.CheckConstraint("currency = 'USD'", name="ck_forecasts_currency"),
        sa.CheckConstraint("lifecycle_state = 'active'", name="ck_forecasts_lifecycle"),
        sa.CheckConstraint("latest_version_number >= 0", name="ck_forecasts_latest_version"),
    )
    op.create_index("ix_forecasts_user_id", "forecasts", ["user_id"])
    op.create_index("ix_forecasts_goal_id", "forecasts", ["goal_id"])
    _create_ownership_guards()
    op.create_table(
        "forecast_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("forecast_id", sa.String(36), sa.ForeignKey("forecasts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("input_state_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_schema_version", sa.String(64), nullable=False),
        sa.Column("hash_schema_version", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("calculation_version", sa.String(128), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_data_age_days", sa.Integer(), nullable=False),
        sa.Column("data_age_days", sa.Integer(), nullable=False),
        sa.Column("input_snapshot_json", sa.Text(), nullable=False),
        sa.Column("assumption_snapshot_json", sa.Text(), nullable=False),
        sa.Column("output_snapshot_json", sa.Text(), nullable=False),
        sa.Column("provenance_snapshot_json", sa.Text(), nullable=False),
        sa.Column("ending_balance", sa.Numeric(38, 2), nullable=False),
        sa.Column("target_gap", sa.Numeric(38, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("forecast_id", "version_number", name="uq_forecast_versions_number"),
        sa.UniqueConstraint("forecast_id", "input_state_hash", "model_version", "calculation_version", name="uq_forecast_versions_input"),
        sa.UniqueConstraint("forecast_id", "idempotency_key_hash", name="uq_forecast_versions_idempotency"),
        sa.CheckConstraint("version_number > 0", name="ck_forecast_versions_positive_number"),
        sa.CheckConstraint("currency = 'USD'", name="ck_forecast_versions_currency"),
        sa.CheckConstraint("length(input_state_hash) = 64", name="ck_forecast_versions_input_hash_length"),
        sa.CheckConstraint("length(idempotency_key_hash) = 64", name="ck_forecast_versions_idempotency_hash_length"),
        sa.CheckConstraint("length(snapshot_schema_version) <= 64", name="ck_forecast_versions_snapshot_version_length"),
        sa.CheckConstraint("length(hash_schema_version) <= 64", name="ck_forecast_versions_hash_version_length"),
        sa.CheckConstraint("length(model_version) <= 128", name="ck_forecast_versions_model_version_length"),
        sa.CheckConstraint("length(calculation_version) <= 128", name="ck_forecast_versions_calculation_version_length"),
        sa.CheckConstraint("max_data_age_days >= 0", name="ck_forecast_versions_max_data_age"),
        sa.CheckConstraint("data_age_days >= 0", name="ck_forecast_versions_data_age"),
    )
    op.create_index("ix_forecast_versions_forecast_id", "forecast_versions", ["forecast_id"])
    _create_immutability_guards()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM forecast_versions")).scalar_one():
        raise RuntimeError("cannot downgrade immutable forecast history while versions exist")
    _drop_immutability_guards()
    _drop_ownership_guards()
    op.drop_index("ix_forecast_versions_forecast_id", table_name="forecast_versions")
    op.drop_table("forecast_versions")
    op.drop_index("ix_forecasts_goal_id", table_name="forecasts")
    op.drop_index("ix_forecasts_user_id", table_name="forecasts")
    op.drop_table("forecasts")
