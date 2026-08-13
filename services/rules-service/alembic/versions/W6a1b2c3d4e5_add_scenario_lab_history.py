"""Add additive immutable Scenario Lab identity and version history.

Revision ID: W6a1b2c3d4e5
Revises: N5a6b7c8d9e0
"""
from alembic import op
import sqlalchemy as sa

revision = "W6a1b2c3d4e5"
down_revision = "N5a6b7c8d9e0"
branch_labels = None
depends_on = None


def _sqlite_triggers() -> None:
    op.execute("""CREATE TRIGGER scenarios_owner_insert BEFORE INSERT ON scenarios BEGIN
      SELECT CASE WHEN (SELECT user_id FROM goals WHERE id = NEW.goal_id) IS NULL OR
        (SELECT user_id FROM goals WHERE id = NEW.goal_id) != NEW.user_id OR
        (SELECT user_id FROM forecasts WHERE id = NEW.baseline_forecast_id) != NEW.user_id OR
        (SELECT goal_id FROM forecasts WHERE id = NEW.baseline_forecast_id) != NEW.goal_id
      THEN RAISE(ABORT, 'scenario ownership mismatch') END;
    END""")
    op.execute("""CREATE TRIGGER scenarios_identity_no_update BEFORE UPDATE ON scenarios BEGIN
      SELECT CASE WHEN NEW.user_id != OLD.user_id OR NEW.goal_id != OLD.goal_id OR NEW.baseline_forecast_id != OLD.baseline_forecast_id
      THEN RAISE(ABORT, 'scenario identity ownership is immutable') END;
    END""")
    op.execute("""CREATE TRIGGER scenarios_owner_update BEFORE UPDATE ON scenarios BEGIN
      SELECT CASE WHEN (SELECT user_id FROM goals WHERE id = NEW.goal_id) != NEW.user_id OR
        (SELECT user_id FROM forecasts WHERE id = NEW.baseline_forecast_id) != NEW.user_id OR
        (SELECT goal_id FROM forecasts WHERE id = NEW.baseline_forecast_id) != NEW.goal_id
      THEN RAISE(ABORT, 'scenario ownership mismatch') END;
    END""")
    op.execute("""CREATE TRIGGER scenario_versions_owner_insert BEFORE INSERT ON scenario_versions BEGIN
      SELECT CASE WHEN (SELECT user_id FROM scenarios WHERE id = NEW.scenario_id) IS NULL OR
        (SELECT user_id FROM scenarios WHERE id = NEW.scenario_id) != (SELECT user_id FROM forecasts WHERE id = NEW.baseline_forecast_id) OR
        (SELECT goal_id FROM scenarios WHERE id = NEW.scenario_id) != (SELECT goal_id FROM forecasts WHERE id = NEW.baseline_forecast_id) OR
        (SELECT baseline_forecast_id FROM scenarios WHERE id = NEW.scenario_id) != NEW.baseline_forecast_id
      THEN RAISE(ABORT, 'scenario version ownership mismatch') END;
    END""")
    op.execute("""CREATE TRIGGER scenario_versions_no_update BEFORE UPDATE ON scenario_versions BEGIN
      SELECT RAISE(ABORT, 'scenario_versions are immutable');
    END""")
    op.execute("""CREATE TRIGGER scenario_versions_no_delete BEFORE DELETE ON scenario_versions BEGIN
      SELECT RAISE(ABORT, 'scenario_versions are immutable');
    END""")


def _postgres_triggers() -> None:
    op.execute("""CREATE FUNCTION enforce_scenario_ownership() RETURNS trigger AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM goals g JOIN forecasts f ON f.user_id = g.user_id AND f.goal_id = g.id
        WHERE g.id = NEW.goal_id AND g.user_id = NEW.user_id AND f.id = NEW.baseline_forecast_id) THEN
        RAISE EXCEPTION 'scenario ownership mismatch';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    op.execute("CREATE TRIGGER scenarios_owner BEFORE INSERT OR UPDATE ON scenarios FOR EACH ROW EXECUTE FUNCTION enforce_scenario_ownership()")
    op.execute("""CREATE FUNCTION enforce_scenario_identity_immutability() RETURNS trigger AS $$
    BEGIN
      IF NEW.user_id <> OLD.user_id OR NEW.goal_id <> OLD.goal_id OR NEW.baseline_forecast_id <> OLD.baseline_forecast_id THEN
        RAISE EXCEPTION 'scenario identity ownership is immutable';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    op.execute("CREATE TRIGGER scenarios_identity_no_update BEFORE UPDATE ON scenarios FOR EACH ROW EXECUTE FUNCTION enforce_scenario_identity_immutability()")
    op.execute("""CREATE FUNCTION enforce_scenario_version_ownership() RETURNS trigger AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM scenarios s JOIN forecasts f ON f.id = NEW.baseline_forecast_id
        WHERE s.id = NEW.scenario_id AND s.user_id = f.user_id AND s.goal_id = f.goal_id AND s.baseline_forecast_id = NEW.baseline_forecast_id) THEN
        RAISE EXCEPTION 'scenario version ownership mismatch';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    op.execute("CREATE TRIGGER scenario_versions_owner BEFORE INSERT ON scenario_versions FOR EACH ROW EXECUTE FUNCTION enforce_scenario_version_ownership()")
    op.execute("""CREATE FUNCTION reject_scenario_version_mutation() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'scenario_versions are immutable'; END; $$ LANGUAGE plpgsql""")
    op.execute("CREATE TRIGGER scenario_versions_no_update BEFORE UPDATE ON scenario_versions FOR EACH ROW EXECUTE FUNCTION reject_scenario_version_mutation()")
    op.execute("CREATE TRIGGER scenario_versions_no_delete BEFORE DELETE ON scenario_versions FOR EACH ROW EXECUTE FUNCTION reject_scenario_version_mutation()")


def upgrade() -> None:
    op.create_table(
        "scenarios",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("goal_id", sa.Integer(), sa.ForeignKey("goals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("baseline_forecast_id", sa.String(36), sa.ForeignKey("forecasts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("lifecycle_state", sa.String(16), nullable=False, server_default="active"),
        sa.Column("latest_version_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archive_idempotency_key_hash", sa.String(64), nullable=True),
        sa.CheckConstraint("lifecycle_state IN ('active', 'archived')", name="ck_scenarios_lifecycle"),
        sa.CheckConstraint("currency = 'USD'", name="ck_scenarios_currency"),
        sa.CheckConstraint("latest_version_number >= 0", name="ck_scenarios_latest_version"),
        sa.CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_scenarios_id_shape"),
        sa.CheckConstraint("archive_idempotency_key_hash IS NULL OR (length(archive_idempotency_key_hash) = 64 AND archive_idempotency_key_hash = lower(archive_idempotency_key_hash))", name="ck_scenarios_archive_idempotency_hash"),
        sa.UniqueConstraint("user_id", "goal_id", "id", name="uq_scenarios_owner_goal_id"),
    )
    op.create_index("ix_scenarios_user_id", "scenarios", ["user_id"])
    op.create_index("ix_scenarios_goal_id", "scenarios", ["goal_id"])
    op.create_index("ix_scenarios_baseline_forecast_id", "scenarios", ["baseline_forecast_id"])
    op.create_table(
        "scenario_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36), sa.ForeignKey("scenarios.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("baseline_forecast_id", sa.String(36), sa.ForeignKey("forecasts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("baseline_version_number", sa.Integer(), nullable=False),
        sa.Column("baseline_input_state_hash", sa.String(64), nullable=False),
        sa.Column("scenario_input_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("calculation_version", sa.String(128), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_data_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_data_age_days", sa.Integer(), nullable=False),
        sa.Column("data_age_days", sa.Integer(), nullable=False),
        sa.Column("input_snapshot_json", sa.Text(), nullable=False),
        sa.Column("result_snapshot_json", sa.Text(), nullable=False),
        sa.Column("comparison_snapshot_json", sa.Text(), nullable=False),
        sa.Column("recommendation_reference", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("scenario_id", "version_number", name="uq_scenario_versions_number"),
        sa.UniqueConstraint("scenario_id", "scenario_input_hash", "model_version", "calculation_version", name="uq_scenario_versions_input"),
        sa.UniqueConstraint("scenario_id", "idempotency_key_hash", name="uq_scenario_versions_idempotency"),
        sa.CheckConstraint("version_number > 0", name="ck_scenario_versions_positive_number"),
        sa.CheckConstraint("length(id) = 36 AND id = lower(id)", name="ck_scenario_versions_id_shape"),
        sa.CheckConstraint("currency = 'USD'", name="ck_scenario_versions_currency"),
        sa.CheckConstraint("length(baseline_forecast_id) = 36 AND baseline_forecast_id = lower(baseline_forecast_id)", name="ck_scenario_versions_baseline_id_shape"),
        sa.CheckConstraint("length(baseline_input_state_hash) = 64 AND baseline_input_state_hash = lower(baseline_input_state_hash)", name="ck_scenario_versions_baseline_hash"),
        sa.CheckConstraint("length(scenario_input_hash) = 64 AND scenario_input_hash = lower(scenario_input_hash)", name="ck_scenario_versions_input_hash"),
        sa.CheckConstraint("length(idempotency_key_hash) = 64 AND idempotency_key_hash = lower(idempotency_key_hash)", name="ck_scenario_versions_idempotency_hash"),
        sa.CheckConstraint("max_data_age_days >= 0 AND data_age_days >= 0", name="ck_scenario_versions_freshness"),
    )
    op.create_index("ix_scenario_versions_scenario_id", "scenario_versions", ["scenario_id"])
    op.create_index("ix_scenario_versions_baseline_forecast_id", "scenario_versions", ["baseline_forecast_id"])
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        _sqlite_triggers()
    elif bind.dialect.name == "postgresql":
        _postgres_triggers()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM scenario_versions")).scalar_one() or bind.execute(sa.text("SELECT COUNT(*) FROM scenarios")).scalar_one():
        raise RuntimeError("cannot downgrade Scenario Lab history while immutable records exist")
    if bind.dialect.name == "sqlite":
        for name in ("scenarios_owner_insert", "scenarios_identity_no_update", "scenarios_owner_update", "scenario_versions_owner_insert", "scenario_versions_no_update", "scenario_versions_no_delete"):
            op.execute(f"DROP TRIGGER IF EXISTS {name}")
    elif bind.dialect.name == "postgresql":
        for trigger in ("scenarios_owner", "scenarios_identity_no_update"):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON scenarios")
        for trigger in ("scenario_versions_owner", "scenario_versions_no_update", "scenario_versions_no_delete"):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON scenario_versions")
        for function in ("enforce_scenario_ownership", "enforce_scenario_identity_immutability", "enforce_scenario_version_ownership", "reject_scenario_version_mutation"):
            op.execute(f"DROP FUNCTION IF EXISTS {function}()")
    op.drop_index("ix_scenario_versions_baseline_forecast_id", table_name="scenario_versions")
    op.drop_index("ix_scenario_versions_scenario_id", table_name="scenario_versions")
    op.drop_table("scenario_versions")
    op.drop_index("ix_scenarios_baseline_forecast_id", table_name="scenarios")
    op.drop_index("ix_scenarios_goal_id", table_name="scenarios")
    op.drop_index("ix_scenarios_user_id", table_name="scenarios")
    op.drop_table("scenarios")
