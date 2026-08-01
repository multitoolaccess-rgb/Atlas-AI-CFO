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
# Phase 2 Slice 1 commit-3 added an additive migration on top of the
# Phase 1 cert chain (``S7a1b2c3d4e5`` → ``T8a1b2c3d4e5``). The
# baseline ``alembic_version.version_num`` constant tracks the new
# chain head so the round-trip assertions below stay aligned with
# the certified migration chain (Phase 1 cert was committed against
# ``S7a1b2c3d4e5``; commit-3 advances head to ``T8a1b2c3d4e5`` but
# does NOT alter the Phase 1 cert semantics).
REVISION = "T8a1b2c3d4e5"
ACCOUNT_CURRENCY_PARENT = "R6f1g2h3i4j5"


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
            conn.execute(text("INSERT INTO users (id, local_user_sub, email, hashed_password) VALUES (2, 'synthetic-user-2', 'user2@example.com', 'x')"))
            conn.execute(text("INSERT INTO goals (id, user_id, name, target_amount, priority, is_archived) VALUES (1, 1, 'Synthetic Goal', 10, 0, 0)"))
            with pytest.raises(Exception):
                conn.execute(text("INSERT INTO forecasts (id, user_id, goal_id) VALUES ('00000000-0000-4000-8000-000000000099', 2, 1)"))
            conn.execute(text("INSERT INTO forecasts (id, user_id, goal_id) VALUES ('00000000-0000-4000-8000-000000000001', 1, 1)"))
            conn.execute(text("""INSERT INTO forecast_versions (id, forecast_id, version_number, input_state_hash, idempotency_key_hash, snapshot_schema_version, hash_schema_version, model_version, calculation_version, calculated_at, data_as_of, max_data_age_days, data_age_days, input_snapshot_json, assumption_snapshot_json, output_snapshot_json, provenance_snapshot_json, ending_balance, target_gap)
                VALUES ('00000000-0000-4000-8000-000000000002', '00000000-0000-4000-8000-000000000001', 1, :h, :k, 'v1', 'v1', 'model-v1', 'calc-v1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, 0, '{}', '{}', '{}', '{}', '1.23', '0.00')"""), {"h": "a" * 64, "k": "b" * 64})
            with pytest.raises(Exception):
                conn.execute(text("UPDATE forecast_versions SET version_number = 2"))
            with pytest.raises(Exception):
                conn.execute(text("DELETE FROM forecast_versions"))
        with pytest.raises(RuntimeError, match="immutable forecast history"):
            command.downgrade(cfg, PARENT)


def test_forecast_downgrade_refuses_versionless_forecast_identity(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'forecast_identity.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _config(url)
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        register_sqlite_compat(engine)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (id, local_user_sub, email, hashed_password) VALUES (1, 'identity-user', 'identity@example.com', 'x')"))
            conn.execute(text("INSERT INTO goals (id, user_id, name, target_amount, priority, is_archived) VALUES (1, 1, 'Identity Goal', 1, 0, 0)"))
            conn.execute(text("INSERT INTO forecasts (id, user_id, goal_id) VALUES ('00000000-0000-4000-8000-000000000010', 1, 1)"))
        with pytest.raises(RuntimeError, match="immutable forecast history"):
            command.downgrade(cfg, PARENT)


def test_forecast_database_format_guards_reject_direct_invalid_values(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'forecast_formats.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        command.upgrade(_config(url), "head")
        engine = create_engine(url)
        register_sqlite_compat(engine)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (id, local_user_sub, email, hashed_password) VALUES (1, 'format-user', 'format@example.com', 'x')"))
            conn.execute(text("INSERT INTO goals (id, user_id, name, target_amount, priority, is_archived) VALUES (1, 1, 'Format Goal', 1, 0, 0)"))
            for bad_id in (
                "x",
                "00000000000040008000000000000001",
                "0000000-0000-4000-8000-0000000000010",
                "00000000-0000-4000-8000-00000000000Z",
                "00000000-0000-4000-8000-00000000000A",
                " 00000000-0000-4000-8000-000000000001",
                "00000000-0000-4000-8000-0000000000001",
            ):
                with pytest.raises(Exception):
                    conn.execute(text("INSERT INTO forecasts (id, user_id, goal_id) VALUES (:id, 1, 1)"), {"id": bad_id})
            conn.execute(text("INSERT INTO forecasts (id, user_id, goal_id) VALUES ('00000000-0000-4000-8000-000000000001', 1, 1)"))
            with pytest.raises(Exception):
                conn.execute(text("UPDATE forecasts SET id = '00000000-0000-4000-8000-00000000000A'"))
            base = {"id": "00000000-0000-4000-8000-000000000002", "forecast_id": "00000000-0000-4000-8000-000000000001", "version_number": 1, "h": "a" * 64, "k": "b" * 64, "snapshot": "v1", "hash": "v1", "model": "model-v1", "calc": "calc-v1"}
            statement = text("""INSERT INTO forecast_versions (id, forecast_id, version_number, input_state_hash, idempotency_key_hash, snapshot_schema_version, hash_schema_version, model_version, calculation_version, calculated_at, data_as_of, max_data_age_days, data_age_days, input_snapshot_json, assumption_snapshot_json, output_snapshot_json, provenance_snapshot_json, ending_balance, target_gap) VALUES (:id, :forecast_id, :version_number, :h, :k, :snapshot, :hash, :model, :calc, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, 0, '{}', '{}', '{}', '{}', '1.00', '0.00')""")
            for key, value in (
                ("id", "0000000-0000-4000-8000-0000000000020"),
                ("id", "00000000-0000-4000-8000-00000000000A"),
                ("id", "00000000-0000-4000-8000-00000000000Z"),
                ("h", "Z" * 64),
                ("h", "a" * 63),
                ("h", "a" * 65),
                ("h", "a" * 63 + " "),
                ("k", "B" * 64),
                ("k", "b" * 63),
                ("k", "sha256:" + "b" * 57),
                ("snapshot", ""),
                ("snapshot", "   "),
                ("snapshot", " v1"),
                ("hash", "\t"),
                ("hash", "v1 "),
                ("model", "m" * 129),
                ("model", " model-v1"),
                ("model", "\vmodel-v1"),
                ("model", "\u00a0model-v1"),
                ("calc", "\t"),
                ("calc", "calc-v1 "),
                ("calc", "calc-v1\f"),
            ):
                values = dict(base); values[key] = value
                try:
                    conn.execute(statement, values)
                except Exception:
                    continue
                pytest.fail(f"direct insert accepted invalid {key} value")
            conn.execute(statement, base)
            boundary = {
                **base,
                "id": "00000000-0000-4000-8000-000000000003",
                "version_number": 2,
                "h": "c" * 64,
                "k": "d" * 64,
                "snapshot": "s" * 64,
                "hash": "h" * 64,
                "model": "m" * 128,
                "calc": "c" * 128,
            }
            conn.execute(statement, boundary)


def test_account_currency_migration_preserves_unknown_rows_and_enforces_evidence(monkeypatch):
    """B0 adds nullable currency provenance without a historical backfill."""
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'account_currency.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _config(url)
        command.upgrade(cfg, ACCOUNT_CURRENCY_PARENT)
        engine = create_engine(url)
        register_sqlite_compat(engine)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (id, local_user_sub, email, hashed_password) VALUES (1, 'currency-user', 'currency@example.com', 'x')"))
            conn.execute(text("INSERT INTO family_members (id, user_id, name, color, is_archived, is_self) VALUES (1, 1, 'Self', '#000000', 0, 1)"))
            conn.execute(text("INSERT INTO institutions (id, name) VALUES (1, 'Currency Test Institution')"))
            conn.execute(text("INSERT INTO accounts (id, user_id, institution_id, family_member_id, account_name, account_type, current_balance, is_active) VALUES (1, 1, 1, 1, 'Currency Test Account', 'checking', 1, 1)"))
            conn.execute(text("INSERT INTO goals (id, user_id, name, target_amount, priority, is_archived) VALUES (1, 1, 'Currency Test Goal', 1, 0, 0)"))
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            row = conn.execute(text("SELECT currency_code, currency_source, currency_observed_at, currency_source_reference FROM accounts WHERE id = 1")).one()
            assert row == (None, None, None, None)
            for values in (
                {"code": "usd", "source": "provider_reported", "reference": "provider-1"},
                {"code": "USD", "source": "inferred", "reference": "provider-1"},
                {"code": "USD", "source": "provider_reported", "reference": "Account Name"},
            ):
                with pytest.raises(Exception):
                    conn.execute(text("UPDATE accounts SET currency_code=:code, currency_source=:source, currency_observed_at=CURRENT_TIMESTAMP, currency_source_reference=:reference WHERE id=1"), values)
            conn.execute(text("UPDATE accounts SET currency_code='USD', currency_source='provider_reported', currency_observed_at=CURRENT_TIMESTAMP, currency_source_reference='provider-account-1' WHERE id=1"))
            conn.execute(text("INSERT INTO goal_projection_configs (user_id, goal_id, projection_kind, currency_code, monthly_contribution, contribution_source_reference, contribution_observed_at) VALUES (1, 1, 'net_worth', 'USD', 1.23, 'plan-1', CURRENT_TIMESTAMP)"))
            with pytest.raises(Exception):
                conn.execute(text("UPDATE goal_projection_configs SET projection_kind='heuristic' WHERE goal_id=1"))
        with pytest.raises(RuntimeError, match="projection config data exists"):
            command.downgrade(cfg, ACCOUNT_CURRENCY_PARENT)


def test_account_currency_migration_clean_downgrade_and_reupgrade(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'account_currency_clean.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _config(url)
        command.upgrade(cfg, ACCOUNT_CURRENCY_PARENT)
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        assert "goal_projection_configs" in inspect(engine).get_table_names()
        command.downgrade(cfg, ACCOUNT_CURRENCY_PARENT)
        assert "goal_projection_configs" not in inspect(engine).get_table_names()
        command.upgrade(cfg, "head")
        assert engine.connect().execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REVISION


def test_postgresql_currency_constraint_explicitly_rejects_partial_null_provenance():
    """PostgreSQL CHECK treats NULL as passing unless the populated arm guards it."""
    migration = (ROOT / "alembic/versions/S7a1b2c3d4e5_add_account_currency_provenance.py").read_text(encoding="utf-8")
    assert "currency_code IS NOT NULL AND currency_source IS NOT NULL" in migration
    assert "currency_observed_at IS NOT NULL AND currency_source_reference IS NOT NULL" in migration
