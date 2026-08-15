"""Wave 2A migration tests use disposable synthetic SQLite only."""
import os
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.database import register_sqlite_compat

ROOT = Path(__file__).parent.parent
PARENT = "W6a1b2c3d4e5"
HEAD = "X7a1b2c3d4e5"


def _cfg(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _url(tmp_path: str) -> str:
    return f"sqlite:///{os.path.join(tmp_path, 'currency-evidence.db')}"


def _seed_account(conn):
    conn.execute(text("INSERT INTO users (id, local_user_sub, email, hashed_password) VALUES (1, 'synthetic-currency', 'currency@example.com', 'x')"))
    conn.execute(text("INSERT INTO family_members (id, user_id, name, color, is_archived, is_self) VALUES (1, 1, 'Self', '#000000', 0, 1)"))
    conn.execute(text("INSERT INTO institutions (id, name) VALUES (1, 'Synthetic Institution')"))
    conn.execute(text("INSERT INTO accounts (id, user_id, institution_id, family_member_id, account_name, account_type, current_balance, is_active) VALUES (1, 1, 1, 1, 'Synthetic Account', 'checking', 0, 1)"))


def test_upgrade_adds_empty_evidence_table_without_backfill_and_clean_round_trip(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = _url(tmp)
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _cfg(url)
        command.upgrade(cfg, PARENT)
        engine = create_engine(url); register_sqlite_compat(engine)
        with engine.begin() as conn:
            _seed_account(conn)
        command.upgrade(cfg, HEAD)
        assert "account_currency_evidence" in inspect(engine).get_table_names()
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM account_currency_evidence")).scalar_one() == 0
            assert conn.execute(text("SELECT currency_code FROM accounts WHERE id=1")).scalar_one() is None
        command.downgrade(cfg, PARENT)
        assert "account_currency_evidence" not in inspect(engine).get_table_names()
        command.upgrade(cfg, HEAD)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM account_currency_evidence")).scalar_one() == 0


def test_upgrade_adopts_compatible_table_created_before_alembic(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = _url(tmp)
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _cfg(url)
        command.upgrade(cfg, PARENT)
        from app.models.account_currency_evidence import AccountCurrencyEvidence
        from app.database import Base
        engine = create_engine(url); register_sqlite_compat(engine)
        Base.metadata.create_all(engine, tables=[AccountCurrencyEvidence.__table__])
        command.upgrade(cfg, HEAD)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM account_currency_evidence")).scalar_one() == 0
            trigger_names = {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='trigger'"))}
            assert {
                "account_currency_evidence_owner_insert",
                "account_currency_evidence_no_update",
                "account_currency_evidence_no_delete",
            } <= trigger_names


def test_sqlite_evidence_guards_enforce_owner_immutability_and_shape(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = _url(tmp)
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _cfg(url)
        command.upgrade(cfg, HEAD)
        engine = create_engine(url); register_sqlite_compat(engine)
        with engine.begin() as conn:
            _seed_account(conn)
            values = {
                "id": "00000000-0000-4000-8000-000000000001", "user_id": 1, "account_id": 1,
                "event_type": "assertion", "source_kind": "structured_provider", "currency_code": "USD",
                "observed_at": "2026-08-01 12:00:00", "actor_category": "synthetic_test",
                "source_reference_hash": "a" * 64, "idempotency_key_hash": "b" * 64,
            }
            conn.execute(text("""INSERT INTO account_currency_evidence
                (id,user_id,account_id,event_type,source_kind,currency_code,observed_at,actor_category,source_reference_hash,idempotency_key_hash)
                VALUES (:id,:user_id,:account_id,:event_type,:source_kind,:currency_code,:observed_at,:actor_category,:source_reference_hash,:idempotency_key_hash)"""), values)
            with pytest.raises(Exception):
                conn.execute(text("UPDATE account_currency_evidence SET currency_code='EUR' WHERE id=:id"), {"id": values["id"]})
            with pytest.raises(Exception):
                conn.execute(text("DELETE FROM account_currency_evidence WHERE id=:id"), {"id": values["id"]})
            with pytest.raises(Exception):
                conn.execute(text("INSERT INTO account_currency_evidence (id,user_id,account_id,event_type,source_kind,currency_code,observed_at,actor_category,source_reference_hash,idempotency_key_hash) VALUES ('00000000-0000-4000-8000-000000000002',2,1,'assertion','structured_provider','USD',CURRENT_TIMESTAMP,'synthetic_test',:source,:key)"), {"source": "c" * 64, "key": "d" * 64})
            with pytest.raises(Exception):
                conn.execute(text("INSERT INTO account_currency_evidence (id,user_id,account_id,event_type,source_kind,currency_code,observed_at,actor_category,source_reference_hash,idempotency_key_hash) VALUES ('00000000-0000-4000-8000-000000000003',1,1,'assertion','structured_provider','usd',CURRENT_TIMESTAMP,'synthetic_test',:source,:key)"), {"source": "e" * 64, "key": "f" * 64})


def test_downgrade_refuses_to_discard_evidence_history(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        url = _url(tmp)
        monkeypatch.setattr("app.config.settings.database_url", url)
        cfg = _cfg(url)
        command.upgrade(cfg, HEAD)
        engine = create_engine(url); register_sqlite_compat(engine)
        with engine.begin() as conn:
            _seed_account(conn)
            conn.execute(text("""INSERT INTO account_currency_evidence
                (id,user_id,account_id,event_type,source_kind,currency_code,observed_at,actor_category,source_reference_hash,idempotency_key_hash)
                VALUES ('00000000-0000-4000-8000-000000000004',1,1,'assertion','structured_provider','USD',CURRENT_TIMESTAMP,'synthetic_test',:source,:key)"""), {"source": "a" * 64, "key": "b" * 64})
        with pytest.raises(RuntimeError, match="evidence history"):
            command.downgrade(cfg, PARENT)
