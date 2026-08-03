"""Migration and dialect-guard regression coverage for Phase 3 outcomes."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.database import register_sqlite_compat
from tests.test_decision_journal_parity import _plant_world


ROOT = Path(__file__).parent.parent
PARENT = "T8a1b2c3d4e5"
REVISION = "U9a1b2c3d4e5"


def _config(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_outcome_migration_clean_downgrade_and_reupgrade(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'outcomes.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        config = _config(url)
        command.upgrade(config, REVISION)
        engine = create_engine(url)
        assert "outcome_evaluations" in inspect(engine).get_table_names()
        command.downgrade(config, PARENT)
        assert "outcome_evaluations" not in inspect(engine).get_table_names()
        command.upgrade(config, REVISION)
        assert engine.connect().execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REVISION


def test_outcome_downgrade_refuses_recorded_history(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'outcomes-history.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        config = _config(url)
        command.upgrade(config, REVISION)
        engine = create_engine(url)
        register_sqlite_compat(engine)
        ids = _plant_world(engine)
        with engine.begin() as conn:
            conn.execute(text("""INSERT INTO outcome_evaluations
                (id, recommendation_id, decision_journal_entry_id, user_id, goal_id, lifecycle,
                 schema_version, idempotency_key_hash, currency, recorded_at)
                VALUES ('00000000-0000-4000-8000-000000000030', :rec, :journal, 1, 1,
                        'pending', 'atlas-outcome-evaluation/v1', :key, 'USD', CURRENT_TIMESTAMP)"""),
                {"rec": ids["rec"], "journal": ids["journal"], "key": "c" * 64})
        with pytest.raises(RuntimeError, match="outcome evaluation data exists"):
            command.downgrade(config, PARENT)


def test_postgresql_counterpart_guards_are_present():
    migration = (ROOT / "alembic/versions/U9a1b2c3d4e5_add_outcome_evaluations.py").read_text(encoding="utf-8")
    assert "bind.dialect.name == \"postgresql\"" in migration
    assert "enforce_outcome_evaluation_acceptance" in migration
    assert "reject_outcome_evaluation_mutation" in migration


def test_sqlite_acceptance_and_lifecycle_guards_fail_closed(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'outcomes-guards.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        config = _config(url)
        command.upgrade(config, REVISION)
        engine = create_engine(url)
        register_sqlite_compat(engine)
        with engine.begin() as conn:
            with pytest.raises(Exception):
                conn.execute(text("""INSERT INTO outcome_evaluations
                    (id, recommendation_id, decision_journal_entry_id, user_id, goal_id, lifecycle,
                     schema_version, idempotency_key_hash, currency, recorded_at)
                    VALUES ('00000000-0000-4000-8000-000000000031',
                            '00000000-0000-4000-8000-000000000032',
                            '00000000-0000-4000-8000-000000000033', 1, 1, 'pending',
                            'atlas-outcome-evaluation/v1', :key, 'USD', CURRENT_TIMESTAMP)"""), {"key": "d" * 64})
        ids = _plant_world(engine)
        with engine.begin() as conn:
            with pytest.raises(Exception):
                conn.execute(text("""INSERT INTO outcome_evaluations
                    (id, recommendation_id, decision_journal_entry_id, user_id, goal_id, lifecycle,
                     schema_version, idempotency_key_hash, currency, authoritative_evidence_reference, recorded_at)
                    VALUES ('00000000-0000-4000-8000-000000000034', :rec, :journal, 1, 1, 'pending',
                            'atlas-outcome-evaluation/v1', :key, 'USD', 'must-not-appear', CURRENT_TIMESTAMP)"""),
                    {"rec": ids["rec"], "journal": ids["journal"], "key": "e" * 64})
