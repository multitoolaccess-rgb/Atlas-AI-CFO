"""Migration coverage for the immutable UI-10 Scout run archive."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.database import register_sqlite_compat


ROOT = Path(__file__).resolve().parent.parent
SCOUT_REVISION = "AB16a1b2c3d4e5"
PARENT_REVISION = "AA15a1b2c3d4e5"


def _config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _upgrade(monkeypatch: pytest.MonkeyPatch, url: str, revision: str = "head") -> None:
    """Keep env.py's settings-backed URL aligned with the disposable DB."""
    monkeypatch.setattr("app.config.settings.database_url", url)
    command.upgrade(_config(url), revision)


def _seed_run(url: str) -> None:
    engine = create_engine(url)
    register_sqlite_compat(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, local_user_sub, email, hashed_password) "
                "VALUES (1, 'scout-migration-user', 'scout-migration@example.com', 'x')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO investment_scout_runs "
                "(owner_id, run_id, security_id, symbol, requested_at, as_of, "
                "result_hash, payload_json) VALUES "
                "(1, :run_id, 'sec:test', 'AAPL', CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP, :hash, '{}')"
            ),
            {"run_id": "scout-run:" + "a" * 32, "hash": "b" * 64},
        )
    engine.dispose()


def test_scout_migration_round_trip_is_additive(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'scout_round_trip.db')}"
        _upgrade(monkeypatch, url, "head")
        engine = create_engine(url)
        register_sqlite_compat(engine)
        assert "investment_scout_runs" in inspect(engine).get_table_names()
        assert engine.connect().execute(text("SELECT version_num FROM alembic_version")).scalar_one() == SCOUT_REVISION

        command.downgrade(_config(url), PARENT_REVISION)
        assert "investment_scout_runs" not in inspect(engine).get_table_names()

        _upgrade(monkeypatch, url, "head")
        assert "investment_scout_runs" in inspect(engine).get_table_names()
        assert engine.connect().execute(text("SELECT version_num FROM alembic_version")).scalar_one() == SCOUT_REVISION
        engine.dispose()


def test_scout_migration_blocks_update_delete_and_nonempty_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'scout_immutable.db')}"
        _upgrade(monkeypatch, url, "head")
        _seed_run(url)
        engine = create_engine(url)
        register_sqlite_compat(engine)
        with engine.begin() as conn:
            with pytest.raises(IntegrityError, match="immutable"):
                conn.execute(
                    text("UPDATE investment_scout_runs SET symbol = 'MSFT' WHERE id = 1")
                )
            with pytest.raises(IntegrityError, match="immutable"):
                conn.execute(text("DELETE FROM investment_scout_runs WHERE id = 1"))
        with pytest.raises(RuntimeError, match="non-empty immutable Scout runs"):
            command.downgrade(_config(url), PARENT_REVISION)
        engine.dispose()


def test_scout_migration_declares_postgres_immutability_branch() -> None:
    migration = (
        ROOT / "alembic/versions/AB16a1b2c3d4e5_add_investment_scout_runs.py"
    ).read_text(encoding="utf-8")
    assert 'dialect.name == "postgresql"' in migration
    assert "reject_investment_scout_run_mutation" in migration
    assert "LANGUAGE plpgsql" in migration
    assert "investment_scout_runs_no_update" in migration
    assert "investment_scout_runs_no_delete" in migration
