"""Migration coverage for the INV-12 immutable durable stores.

Covers ``investment_market_observations`` (AC17), ``investment_portfolio_snapshots``
(AD18), and ``investment_evaluation_records`` (AE19): additive round trip to the
new single head, UPDATE/DELETE trigger rejection on each table, non-empty
downgrade refusal, and the PostgreSQL immutability branch declarations.
"""
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
HEAD_REVISION = "AE19a1b2c3d4e5"
PRE_STORES_REVISION = "AB16a1b2c3d4e5"

TABLES = (
    "investment_market_observations",
    "investment_portfolio_snapshots",
    "investment_evaluation_records",
)


def _config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _upgrade(monkeypatch: pytest.MonkeyPatch, url: str, revision: str = "head") -> None:
    monkeypatch.setattr("app.config.settings.database_url", url)
    command.upgrade(_config(url), revision)


def _seed_user(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, local_user_sub, email, hashed_password) "
                "VALUES (1, 'inv12-migration-user', 'inv12-migration@example.com', 'x')"
            )
        )


def _seed_observation(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO investment_market_observations "
                "(observation_id, security_id, observed_value, currency, adjustment_basis, "
                "observed_at, as_known_at, retrieved_at, source, source_identifier, state, "
                "quality, freshness, observation_hash, payload_json) VALUES "
                "(:oid, 'sec:test', '100.00', 'USD', 'unadjusted', CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'fixture', NULL, 'observed', 'validated', "
                "'observed', :hash, '{}')"
            ),
            {"oid": "market-observation:" + "a" * 64, "hash": "b" * 64},
        )


def _seed_snapshot(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO investment_portfolio_snapshots "
                "(owner_id, snapshot_id, snapshot_hash, as_of, payload_json) VALUES "
                "(1, :sid, :hash, CURRENT_TIMESTAMP, '{}')"
            ),
            {"sid": "portfolio-snapshot:" + "c" * 32, "hash": "d" * 64},
        )


def _seed_recommendation(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO investment_recommendation_records "
                "(owner_id, recommendation_id, security_id, recommendation_type, status, "
                "recommendation_as_of, review_after, recommendation_hash, committee_finding_id, "
                "committee_run_id, portfolio_snapshot_hash, created_at, payload_json) VALUES "
                "(1, 'investment-recommendation:rec', 'sec:test', 'HOLD', 'active', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :rhash, 'committee:finding', 'run:run', "
                ":phash, CURRENT_TIMESTAMP, '{}')"
            ),
            {"rhash": "e" * 64, "phash": "f" * 64},
        )


def _seed_evaluation(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO investment_evaluation_records "
                "(owner_id, evaluation_id, recommendation_record_id, recommendation_id, "
                "recommendation_hash, outcome_id, outcome_hash, security_id, "
                "evaluation_window_start, evaluation_as_of, horizon, benchmark_security_id, "
                "evaluation_state, result_state, methodology_version, vintage_bound, replay_state, "
                "input_hash, evaluation_hash, payload_json) VALUES "
                "(1, 'investment-evaluation:' || :eid, 1, 'investment-recommendation:rec', "
                ":rhash, NULL, NULL, 'sec:test', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, '1M', NULL, "
                "'blocked', NULL, 'investment-evaluation/v1', CURRENT_TIMESTAMP, 'match', "
                ":ihash, :ehash, '{}')"
            ),
            {"eid": "g" * 64, "rhash": "e" * 64, "ihash": "h" * 64, "ehash": "i" * 64},
        )


def test_evaluation_stores_round_trip_is_additive(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'inv12_round_trip.db')}"
        _upgrade(monkeypatch, url, "head")
        engine = create_engine(url)
        register_sqlite_compat(engine)
        names = set(inspect(engine).get_table_names())
        for table in TABLES:
            assert table in names
        assert engine.connect().execute(text("SELECT version_num FROM alembic_version")).scalar_one() == HEAD_REVISION
        engine.dispose()

        command.downgrade(_config(url), PRE_STORES_REVISION)
        engine = create_engine(url)
        register_sqlite_compat(engine)
        names = set(inspect(engine).get_table_names())
        for table in TABLES:
            assert table not in names
        engine.dispose()

        _upgrade(monkeypatch, url, "head")
        engine = create_engine(url)
        register_sqlite_compat(engine)
        assert "investment_evaluation_records" in inspect(engine).get_table_names()
        assert engine.connect().execute(text("SELECT version_num FROM alembic_version")).scalar_one() == HEAD_REVISION
        engine.dispose()


def test_evaluation_stores_block_update_delete_and_nonempty_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{os.path.join(tmp, 'inv12_immutable.db')}"
        _upgrade(monkeypatch, url, "head")
        engine = create_engine(url)
        register_sqlite_compat(engine)
        _seed_user(engine)
        _seed_observation(engine)
        _seed_snapshot(engine)
        _seed_recommendation(engine)
        _seed_evaluation(engine)

        with engine.begin() as conn:
            with pytest.raises(IntegrityError, match="immutable"):
                conn.execute(text("UPDATE investment_market_observations SET observed_value = '1' WHERE id = 1"))
            with pytest.raises(IntegrityError, match="immutable"):
                conn.execute(text("DELETE FROM investment_market_observations WHERE id = 1"))
            with pytest.raises(IntegrityError, match="immutable"):
                conn.execute(text("UPDATE investment_portfolio_snapshots SET payload_json = '{}' WHERE id = 1"))
            with pytest.raises(IntegrityError, match="immutable"):
                conn.execute(text("DELETE FROM investment_portfolio_snapshots WHERE id = 1"))
            with pytest.raises(IntegrityError, match="immutable"):
                conn.execute(text("UPDATE investment_evaluation_records SET result_state = 'available' WHERE id = 1"))
            with pytest.raises(IntegrityError, match="immutable"):
                conn.execute(text("DELETE FROM investment_evaluation_records WHERE id = 1"))

        with pytest.raises(RuntimeError, match="non-empty immutable investment_evaluation_records"):
            command.downgrade(_config(url), "AD18a1b2c3d4e5")
        engine.dispose()

        # A database whose observation store is non-empty (but whose later
        # evaluation/snapshot stores are empty) must fail at the observation
        # table when downgrading past all three stores.
        url2 = f"sqlite:///{os.path.join(tmp, 'inv12_observations_immutable.db')}"
        _upgrade(monkeypatch, url2, "head")
        engine2 = create_engine(url2)
        register_sqlite_compat(engine2)
        _seed_observation(engine2)
        with pytest.raises(RuntimeError, match="non-empty immutable investment_market_observations"):
            command.downgrade(_config(url2), "AB16a1b2c3d4e5")
        engine2.dispose()


def test_evaluation_stores_declare_postgres_immutability_branch() -> None:
    for filename in (
        "AC17a1b2c3d4e5_add_investment_market_observations.py",
        "AD18a1b2c3d4e5_add_investment_portfolio_snapshots.py",
        "AE19a1b2c3d4e5_add_investment_evaluation_records.py",
    ):
        migration = (ROOT / "alembic/versions" / filename).read_text(encoding="utf-8")
        assert 'dialect.name == "postgresql"' in migration
        assert "reject_{TABLE}_mutation" in migration
        assert "LANGUAGE plpgsql" in migration
        assert "{TABLE}_no_update" in migration
        assert "{TABLE}_no_delete" in migration
