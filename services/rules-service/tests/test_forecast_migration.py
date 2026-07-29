"""SQLite migration regression coverage for immutable forecast history."""
import os
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.database import register_sqlite_compat


ROOT = Path(__file__).parent.parent
PARENT = "Q5h1i2j3k4l5"
REVISION = "R6f1g2h3i4j5"


def _config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_forecast_migration_upgrade_downgrade_reupgrade_preserves_existing_data(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'forecast_migration.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _config(url)
        command.upgrade(cfg, PARENT)
        engine = create_engine(url)
        register_sqlite_compat(engine)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO categories (name, budget_group, \"group\") VALUES ('Migration Existing', 'flexible', 'Expenses')"))

        command.upgrade(cfg, "head")
        assert {"forecasts", "forecast_versions"} <= set(inspect(engine).get_table_names())
        assert engine.connect().execute(text("SELECT count(*) FROM categories WHERE name = 'Migration Existing' ")).scalar_one() == 1
        assert engine.connect().execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REVISION

        command.downgrade(cfg, PARENT)
        assert "forecasts" not in inspect(engine).get_table_names()
        assert engine.connect().execute(text("SELECT count(*) FROM categories WHERE name = 'Migration Existing' ")).scalar_one() == 1
        command.upgrade(cfg, "head")
        assert engine.connect().execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REVISION


def test_forecast_version_guards_and_downgrade_refusal(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'forecast_guards.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _config(url)
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        register_sqlite_compat(engine)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (id, local_user_sub, email, hashed_password) VALUES (1, 'synthetic-user', 'user@example.com', 'x')"))
            conn.execute(text("INSERT INTO goals (id, user_id, name, target_amount, priority, is_archived) VALUES (1, 1, 'Synthetic Goal', 10, 0, 0)"))
            conn.execute(text("INSERT INTO forecasts (id, user_id, goal_id) VALUES ('00000000-0000-4000-8000-000000000001', 1, 1)"))
            conn.execute(text("""INSERT INTO forecast_versions (id, forecast_id, version_number, input_state_hash, idempotency_key_hash, snapshot_schema_version, hash_schema_version, model_version, calculation_version, calculated_at, data_as_of, max_data_age_days, data_age_days, input_snapshot_json, assumption_snapshot_json, output_snapshot_json, provenance_snapshot_json, ending_balance, target_gap)
                VALUES ('00000000-0000-4000-8000-000000000002', '00000000-0000-4000-8000-000000000001', 1, :h, :k, 'v1', 'v1', 'model-v1', 'calc-v1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, 0, '{}', '{}', '{}', '{}', '1.23', '0.00')"""), {"h": "a" * 64, "k": "b" * 64})
            with pytest.raises(Exception):
                conn.execute(text("UPDATE forecast_versions SET version_number = 2"))
            with pytest.raises(Exception):
                conn.execute(text("DELETE FROM forecast_versions"))
        with pytest.raises(RuntimeError, match="immutable forecast history"):
            command.downgrade(cfg, PARENT)
