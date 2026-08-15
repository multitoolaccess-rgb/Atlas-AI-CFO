"""Synthetic migration tests for exact-cent authoritative balance evidence."""
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
PARENT = "Y8a1b2c3d4e5"
HEAD = "Z9a1b2c3d4e5"


def _config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _seed_account(conn) -> None:
    conn.execute(text("INSERT INTO users (id, local_user_sub, email, hashed_password) VALUES (1, 'evidence-migration-user', 'evidence@example.com', 'x')"))
    conn.execute(text("INSERT INTO family_members (id, user_id, name, color, is_archived, is_self) VALUES (1, 1, 'Self', '#000000', 0, 1)"))
    conn.execute(text("INSERT INTO institutions (id, name) VALUES (1, 'Synthetic Institution')"))
    conn.execute(text("INSERT INTO accounts (id, user_id, institution_id, family_member_id, account_name, account_type, current_balance, is_active) VALUES (1, 1, 1, 1, 'Synthetic Account', 'checking', 100.25, 1)"))


def _values(**overrides):
    values = {
        "id": "00000000-0000-4000-8000-000000000001", "user_id": 1, "account_id": 1,
        "event_type": "assertion", "source_kind": "operator_confirmed", "actor_category": "local_operator",
        "currency_code": "USD", "amount": "100.25", "observed_at": "2026-08-15 12:00:00+00:00",
        "supersedes_event_id": None, "precondition_hash": "a" * 64, "state_hash": "b" * 64,
        "observation_intent_hash": "c" * 64, "idempotency_key_hash": "d" * 64,
    }
    values.update(overrides)
    return values


def _insert(conn, values):
    conn.execute(text("""INSERT INTO account_balance_evidence
        (id,user_id,account_id,event_type,source_kind,actor_category,currency_code,amount,observed_at,
         supersedes_event_id,precondition_hash,state_hash,observation_intent_hash,idempotency_key_hash)
        VALUES (:id,:user_id,:account_id,:event_type,:source_kind,:actor_category,:currency_code,:amount,
                :observed_at,:supersedes_event_id,:precondition_hash,:state_hash,:observation_intent_hash,
                :idempotency_key_hash)"""), values)


def test_upgrade_is_additive_and_does_not_backfill_legacy_observations(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        url = f"sqlite:///{os.path.join(directory, 'evidence.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _config(url)
        command.upgrade(cfg, PARENT)
        engine = create_engine(url); register_sqlite_compat(engine)
        with engine.begin() as conn:
            _seed_account(conn)
            conn.execute(text("""INSERT INTO account_balance_observations
                (id,user_id,account_id,source_kind,actor_category,observed_at,precondition_hash,observation_intent_hash,idempotency_key_hash)
                VALUES ('00000000-0000-4000-8000-000000000099',1,1,'operator_confirmed','local_operator',
                        '2026-08-15 12:00:00+00:00',:p,:i,:k)"""), {"p": "a" * 64, "i": "b" * 64, "k": "c" * 64})
        command.upgrade(cfg, HEAD)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM account_balance_observations")).scalar_one() == 1
            assert conn.execute(text("SELECT COUNT(*) FROM account_balance_evidence")).scalar_one() == 0
            assert str(conn.execute(text("SELECT sql FROM sqlite_master WHERE name='account_balance_evidence'")).scalar_one()).find("NUMERIC(38, 2)") >= 0
        command.downgrade(cfg, PARENT)
        assert "account_balance_evidence" not in inspect(engine).get_table_names()


def test_guards_enforce_owner_shape_and_immutability(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        url = f"sqlite:///{os.path.join(directory, 'evidence-guards.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _config(url); command.upgrade(cfg, HEAD)
        engine = create_engine(url); register_sqlite_compat(engine)
        with engine.begin() as conn:
            _seed_account(conn); values = _values(); _insert(conn, values)
            with pytest.raises(Exception):
                conn.execute(text("UPDATE account_balance_evidence SET amount='101.25' WHERE id=:id"), {"id": values["id"]})
            with pytest.raises(Exception):
                conn.execute(text("DELETE FROM account_balance_evidence WHERE id=:id"), {"id": values["id"]})
            with pytest.raises(Exception):
                _insert(conn, _values(id="00000000-0000-4000-8000-000000000002", user_id=2))
            with pytest.raises(Exception):
                _insert(conn, _values(id="00000000-0000-4000-8000-000000000003", amount="100.255"))
            with pytest.raises(Exception):
                _insert(conn, _values(id="00000000-0000-4000-8000-000000000004", event_type="revocation", amount=None, supersedes_event_id="00000000-0000-4000-8000-000000000099"))


def test_downgrade_refuses_authoritative_history(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        url = f"sqlite:///{os.path.join(directory, 'evidence-refusal.db')}"
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _config(url); command.upgrade(cfg, HEAD)
        engine = create_engine(url); register_sqlite_compat(engine)
        with engine.begin() as conn:
            _seed_account(conn); _insert(conn, _values())
        with pytest.raises(RuntimeError, match="authoritative balance evidence"):
            command.downgrade(cfg, PARENT)
