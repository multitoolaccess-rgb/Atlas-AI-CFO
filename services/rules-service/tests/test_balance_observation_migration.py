"""Synthetic SQLite migration tests for balance-observation provenance."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.database import register_sqlite_compat

ROOT = Path(__file__).parent.parent
PARENT = "X7a1b2c3d4e5"
HEAD = "Y8a1b2c3d4e5"


def _config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _seed_account(conn) -> None:
    conn.execute(text("INSERT INTO users (id, local_user_sub, email, hashed_password) VALUES (1, 'observation-migration-user', 'observation@example.com', 'x')"))
    conn.execute(text("INSERT INTO family_members (id, user_id, name, color, is_archived, is_self) VALUES (1, 1, 'Self', '#000000', 0, 1)"))
    conn.execute(text("INSERT INTO institutions (id, name) VALUES (1, 'Synthetic Institution')"))
    conn.execute(text("INSERT INTO accounts (id, user_id, institution_id, family_member_id, account_name, account_type, current_balance, is_active) VALUES (1, 1, 1, 1, 'Synthetic Account', 'checking', 100.25, 1)"))


def _event_values(**overrides):
    values = {
        "id": "00000000-0000-4000-8000-000000000001",
        "user_id": 1,
        "account_id": 1,
        "source_kind": "operator_confirmed",
        "actor_category": "local_operator",
        "observed_at": "2026-08-15 12:00:00+00:00",
        "precondition_hash": "a" * 64,
        "observation_intent_hash": "b" * 64,
        "idempotency_key_hash": "c" * 64,
    }
    values.update(overrides)
    return values


def _insert_event(conn, values):
    conn.execute(text("""INSERT INTO account_balance_observations
        (id,user_id,account_id,source_kind,actor_category,observed_at,precondition_hash,observation_intent_hash,idempotency_key_hash)
        VALUES (:id,:user_id,:account_id,:source_kind,:actor_category,:observed_at,:precondition_hash,:observation_intent_hash,:idempotency_key_hash)"""), values)


def test_upgrade_is_additive_empty_and_clean_downgrade_round_trip(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        url = f"sqlite:///{os.path.join(directory, 'observation.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _config(url)
        command.upgrade(cfg, PARENT)
        engine = create_engine(url); register_sqlite_compat(engine)
        with engine.begin() as conn:
            _seed_account(conn)
            assert conn.execute(text("SELECT last_sync FROM accounts WHERE id=1")).scalar_one() is None
        command.upgrade(cfg, HEAD)
        assert "account_balance_observations" in inspect(engine).get_table_names()
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM account_balance_observations")).scalar_one() == 0
            assert conn.execute(text("SELECT last_sync FROM accounts WHERE id=1")).scalar_one() is None
        command.downgrade(cfg, PARENT)
        assert "account_balance_observations" not in inspect(engine).get_table_names()
        command.upgrade(cfg, HEAD)


def test_sqlite_guards_enforce_owner_shape_and_immutability(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        url = f"sqlite:///{os.path.join(directory, 'observation-guards.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _config(url)
        command.upgrade(cfg, HEAD)
        engine = create_engine(url); register_sqlite_compat(engine)
        with engine.begin() as conn:
            _seed_account(conn)
            values = _event_values()
            _insert_event(conn, values)
            with pytest.raises(Exception):
                conn.execute(text("UPDATE account_balance_observations SET actor_category='other' WHERE id=:id"), {"id": values["id"]})
            with pytest.raises(Exception):
                conn.execute(text("DELETE FROM account_balance_observations WHERE id=:id"), {"id": values["id"]})
            with pytest.raises(Exception):
                _insert_event(conn, _event_values(id="00000000-0000-4000-8000-000000000002", user_id=2))
            with pytest.raises(Exception):
                _insert_event(conn, _event_values(id="00000000-0000-4000-8000-000000000003", precondition_hash="Z" * 64))


def test_downgrade_refuses_to_discard_observation_history(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        url = f"sqlite:///{os.path.join(directory, 'observation-refusal.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _config(url)
        command.upgrade(cfg, HEAD)
        engine = create_engine(url); register_sqlite_compat(engine)
        with engine.begin() as conn:
            _seed_account(conn)
            _insert_event(conn, _event_values())
        with pytest.raises(RuntimeError, match="balance observation history"):
            command.downgrade(cfg, PARENT)
